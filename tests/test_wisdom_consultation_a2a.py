from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import httpx

    from uuma.a2a_node import DispatchCoordinator, create_app
    from uuma.api import create_app as control_app
    from uuma.auth import TokenRegistry
    from uuma.node_journal import NodeJournal
except ImportError:
    DISTRIBUTED_DEPENDENCIES = False
else:
    DISTRIBUTED_DEPENDENCIES = True

from uuma.models import TaskContract
from uuma.service import ControlPlane
from uuma.settings import Settings
from uuma.wisdom_consultation import KnowledgeConsultationBroker, KnowledgeConsultationRequest


class FakeWisdomRuntime:
    def __init__(self):
        self.starts = []
        self.fail = False

    async def start(self, key, task):
        self.starts.append((key, task))
        if self.fail:
            raise OSError("Simulated uncertain delivery")
        return "runtime:consultation"

    async def get(self, reference):
        return {"status": "completed"}

    async def cancel(self, reference):
        raise AssertionError("Consultations do not authorize cancellation")


@unittest.skipUnless(DISTRIBUTED_DEPENDENCIES, "Distributed dependencies required")
class WisdomConsultationA2ATest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.settings = Settings(root, root / "uuma.db", root / "artifacts", root / "spool",
                                 root / "hermes.exe")
        self.control = ControlPlane(self.settings)
        self.control.bootstrap()
        self.parent = self.control.register_direct_run("brainstormer", TaskContract(
            title="Discussion", objective="Need grounded facts.", source="direct",
            required_capabilities={"brainstorming"}, external_project_ref="project-coffee",
        ))
        self.request = KnowledgeConsultationRequest(
            parent_run_id=self.parent.run_id, parent_execution_epoch=self.parent.execution_epoch,
            project_id="project-coffee", topic_id="topic-demand", question="What is known?",
            purpose="Ground a discussion.", source_refs=["conversation:test:source"],
            idempotency_key="consultation-1",
        )
        self.broker = KnowledgeConsultationBroker(self.control)
        self.receipt = self.broker.register(self.request, actor_id="brainstormer")
        self.runtime = FakeWisdomRuntime()
        self.journal = NodeJournal(root / "a2a-journal.db")
        self.coordinator = DispatchCoordinator(
            self.control, self.journal, {"wisdom-oldman": self.runtime},
        )
        self.registry = TokenRegistry(self.settings.token_file())
        self.tokens = self.registry.initialize()

    def tearDown(self):
        self.directory.cleanup()

    def headers(self, identity):
        return {"Authorization": "Bearer " + self.tokens[identity], "X-Uuma-Identity": identity}

    async def test_direct_a2a_dispatch_is_bounded_and_idempotent(self):
        receipt = self.receipt
        first = await self.coordinator.dispatch(
            "wisdom-oldman", receipt["run_id"], receipt["execution_epoch"], "a2a:one",
            requester="brainstormer",
        )
        again = await self.coordinator.dispatch(
            "wisdom-oldman", receipt["run_id"], receipt["execution_epoch"], "a2a:one",
            requester="brainstormer",
        )
        self.assertEqual(first, again)
        self.assertEqual(len(self.runtime.starts), 1)
        self.assertEqual(self.runtime.starts[0][1]["contract"]["source"], "consultation")

    async def test_a2a_rejects_other_requesters_and_ordinary_tasks(self):
        for requester in ["yonc", "wisdom-oldman"]:
            with self.assertRaises(PermissionError):
                await self.coordinator.dispatch(
                    "wisdom-oldman", self.receipt["run_id"], 1, "a2a:denied",
                    requester=requester,
                )
        self.assertEqual(self.runtime.starts, [])

    async def test_uncertain_delivery_never_relaunches(self):
        self.runtime.fail = True
        with self.assertRaises(OSError):
            await self.coordinator.dispatch(
                "wisdom-oldman", self.receipt["run_id"], 1, "a2a:uncertain",
                requester="brainstormer",
            )
        with self.assertRaises(RuntimeError):
            await self.coordinator.dispatch(
                "wisdom-oldman", self.receipt["run_id"], 1, "a2a:uncertain",
                requester="brainstormer",
            )
        self.assertEqual(len(self.runtime.starts), 1)

    async def test_control_http_exposes_only_scoped_reply_and_registration(self):
        with patch.dict(os.environ, {"UUMA_KNOWLEDGE_REQUIRE_EXISTING": "1"}):
            app = control_app(self.settings)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as c:
            body = self.request.model_dump(mode="json")
            response = await c.post("/worker/consultations/wisdom", json=body,
                                    headers=self.headers("brainstormer"))
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["run_id"], self.receipt["run_id"])
            response = await c.post("/worker/consultations/wisdom", json=body,
                                    headers=self.headers("yonc"))
            self.assertEqual(response.status_code, 403)
            response = await c.get("/worker/runs/" + self.receipt["run_id"],
                                   headers=self.headers("brainstormer"))
            self.assertEqual(response.status_code, 403)
            response = await c.get("/worker/consultations/wisdom/" + self.receipt["run_id"],
                                   headers=self.headers("brainstormer"))
            self.assertEqual(response.status_code, 200)
            authorization_path = ("/control/consultations/wisdom/" + self.receipt["run_id"]
                                  + "/dispatch-authorization")
            response = await c.post(authorization_path, json={"execution_epoch": 1},
                                    headers=self.headers("brainstormer"))
            self.assertEqual(response.status_code, 403)
            response = await c.post(authorization_path, json={"execution_epoch": 1},
                                    headers=self.headers("orchestrator"))
            self.assertEqual(response.status_code, 200, response.text)

    async def test_a2a_http_does_not_expose_global_receipts_to_brainstormer(self):
        binding = {"wisdom-oldman": {"adapter": self.runtime,
                                     "endpoint": "http://127.0.0.1:8768/agents/wisdom-oldman"}}
        app = create_app(self.control, self.journal, self.registry, binding)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as c:
            self.assertEqual((await c.get("/receipts")).status_code, 403)
            response = await c.get("/receipts", headers=self.headers("brainstormer"))
            self.assertEqual(response.status_code, 403)
            response = await c.get("/receipts", headers=self.headers("orchestrator"))
            self.assertEqual(response.status_code, 200)
            response = await c.post("/agents/yonc/rpc", json={},
                                    headers=self.headers("brainstormer"))
            self.assertEqual(response.status_code, 403)

    async def test_real_sdk_send_message_wire_accepts_registered_consultation(self):
        from a2a.types.a2a_pb2 import Message, Part, Role, SendMessageRequest
        from google.protobuf.json_format import MessageToDict

        binding = {"wisdom-oldman": {"adapter": self.runtime,
                                     "endpoint": "http://127.0.0.1:8768/agents/wisdom-oldman"}}
        app = create_app(self.control, self.journal, self.registry, binding)
        request = SendMessageRequest(
            message=Message(message_id="consultation:wire", role=Role.ROLE_USER,
                            parts=[Part(text="Answer the registered knowledge question")]),
            metadata={"uuma_run_id": self.receipt["run_id"], "execution_epoch": 1},
        )
        request.configuration.return_immediately = True
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as c:
            response = await c.post("/agents/wisdom-oldman/rpc", json={
                "jsonrpc": "2.0", "id": "consultation:wire", "method": "SendMessage",
                "params": MessageToDict(request),
            }, headers={**self.headers("brainstormer"), "A2A-Version": "1.0"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertNotIn("error", response.json(), response.text)
            for _ in range(20):
                if self.runtime.starts:
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(len(self.runtime.starts), 1)


if __name__ == "__main__":
    unittest.main()
