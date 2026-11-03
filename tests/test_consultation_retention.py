import unittest
from copy import deepcopy

from uuma.consultation_retention import retain_records, run_sync
from uuma.models import ResultContract


class ConsultationRetentionTest(unittest.TestCase):
    def test_sync_bridge_works_inside_and_outside_a_running_event_loop(self):
        import asyncio

        async def value():
            return "actual-loop-result"

        self.assertEqual(run_sync(value), "actual-loop-result")

        async def caller():
            return run_sync(value)

        self.assertEqual(asyncio.run(caller()), "actual-loop-result")

    def setUp(self):
        self.records = {}
        self.writes = 0
        self.task = {"assignee": "wisdom-oldman", "contract": {
            "source": "consultation", "output_schema": {"x-uuma-knowledge-consultation": {
                "version": "brainstormer-wisdom-v1", "request": {
                    "question": "What cycle is supported?", "purpose": "Calculate area",
                    "project_id": "project", "topic_id": "topic", "parent_run_id": "parent",
                },
            }},
        }}
        self.result = ResultContract(run_id="run", task_id="task", agent_id="wisdom-oldman",
                                     outcome="PARTIAL", summary="Existing knowledge is limited",
                                     partial_state={"consultation": {
                                         "status": "PARTIAL", "answer": "Saved fake_question",
                                         "remaining_questions": ["What is local survival?"],
                                         "research_refs": ["fake_question"],
                                     }})

    def call(self, name, arguments):
        if name == "knowledge_get":
            value = self.records.get(arguments["object_id"])
            return {"record": deepcopy(value)} if value else {"_missing": True}
        import json
        key = "question" if name == "knowledge_add_question" else "gap"
        record = json.loads(arguments[key + "_json"])
        self.records[record[key + "_id"]] = record
        self.writes += 1
        return {"record": record}

    def test_retains_actual_ids_readback_provenance_and_original_response(self):
        answer = retain_records(self.result, self.task, self.call)
        receipt = answer.partial_state["consultation_retention"]
        self.assertEqual(self.writes, 3)
        self.assertEqual(len(receipt["verified_record_ids"]), 3)
        self.assertIn("project project", self.records[receipt["question_id"]]["why_worth_knowing"])
        self.assertFalse(receipt["research_started"])
        self.assertFalse(receipt["canonical_knowledge_approved"])
        self.assertNotIn("fake_question", answer.partial_state["consultation"]["research_refs"])
        self.assertNotIn("fake_question", answer.partial_state["consultation"]["answer"])
        self.assertEqual(answer.partial_state["consultation_model_response"],
                         self.result.partial_state["consultation"])
        retain_records(self.result, self.task, self.call)
        self.assertEqual(self.writes, 3)

    def test_failed_write_or_inconsistent_existing_record_blocks_submission(self):
        def failure(name, arguments):
            if name == "knowledge_get":
                return {"_missing": True}
            raise RuntimeError("semantic owner unavailable")
        with self.assertRaisesRegex(RuntimeError, "semantic owner"):
            retain_records(self.result, self.task, failure)
        retain_records(self.result, self.task, self.call)
        next(iter(self.records.values()))["text"] = "Different question"
        with self.assertRaisesRegex(RuntimeError, "readback mismatch"):
            retain_records(self.result, self.task, self.call)

    def test_another_owner_cannot_retain_and_answered_reply_does_not_write(self):
        self.task["assignee"] = "brainstormer"
        with self.assertRaises(PermissionError):
            retain_records(self.result, self.task, self.call)
        self.task["assignee"] = "wisdom-oldman"
        self.result.partial_state["consultation"]["status"] = "ANSWERED"
        self.assertIs(retain_records(self.result, self.task, self.call), self.result)
        self.assertEqual(self.writes, 0)
