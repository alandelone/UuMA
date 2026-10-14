"""Internal adapter context capabilities; no source or identity minting model tools."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .life_service import LifeService
from .life_store import LifeStore
from .reminder_runtime import ReminderRuntime, identity
from .store import HoncStore


def _clause_operations(text: str, known_habit_names: tuple[str, ...]) -> tuple[str, ...]:
    """Conservative admission of first-person effects; the agent still parses exact facts.

    Chat, queries, quoted reports, future plans and hypotheticals never grant a
    completed habit/body write. Ambiguous input stays read-only for clarification.
    """
    value = text.strip()
    if re.search(
        r"^(?:如果|假设|例如|比如|别人说|他说|她说|引用|明天|后天|不要|别|不想)|^(?:if |suppose |tomorrow |he said|she said|don't |do not )|^[「『\"]",
        value,
        re.IGNORECASE,
    ):
        return ()
    grants = []
    if re.search(
        r"(?:增加|新增|添加|建立|创建|修改|调整|暂停|停用|恢复|删除|移除|退役|改).{0,20}(?:习惯|提醒)|(?:习惯|提醒).{0,20}(?:增加|修改|暂停|恢复|删除)|暂停|停用|(?:add|create|update|change|modify|pause|resume|retire|delete).{0,20}(?:habit|reminder)",
        value,
        re.IGNORECASE,
    ):
        grants.append("configure_habit")
    if re.search(
        r"(?:改|调整|更新|设置).{0,16}(?:设置|起床|睡前|提醒|重要度)|起床.*改|睡前.*改|提醒.*次数|重要度.*改|改.*设置|(?:change|update|set).{0,20}(?:settings|wake|bedtime|reminder|importance)",
        value,
        re.IGNORECASE,
    ):
        grants.append("update_settings")
    if re.search(r"记错|改成|修正|更正|撤销.{0,12}(?:记录|日记)|删.{0,8}记录", value):
        grants.append("correct_record")
    if re.search(
        r"起床了|刚起床|醒了|开始.*(?:今天|一天|计划)|准备睡|要睡了|去睡|woke up|going to bed",
        value,
        re.IGNORECASE,
    ):
        grants.append("record_anchor")
    querying = bool(
        re.search(
            r"[？?]|有没有|是否|怎么|如何|查询|看看|查看|历史|统计|昨天.*记录|\b(?:history|show|query|how|whether)\b",
            value,
            re.IGNORECASE,
        )
    )
    planned = bool(
        re.search(
            r"打算|计划.{0,8}(?:喝水|运动|吃|泡脚|日记)|准备.{0,6}(?:喝水|运动|泡脚)|\b(?:plan to|intend to|will|tomorrow)\b",
            value,
            re.IGNORECASE,
        )
    )
    if not querying and not planned:
        named_report = any(
            name.casefold() in value.casefold() for name in known_habit_names
        ) and re.search(r"做了|练了|读了|记|完成|打卡|\bdone\b|\bcompleted\b", value, re.IGNORECASE)
        if named_report or re.search(
            r"打卡|完成|运动|跑步|走路|喝水|喝了|吃了|服药|泡脚|呼吸|锻炼|没.{0,4}(?:喝水|运动|吃|做)|\b(?:done|completed|drank|ate|exercised|walked|workout)\b",
            value,
            re.IGNORECASE,
        ):
            grants.append("record_habit")
        if re.search(
            r"鼻涕|鼻塞|累|疲劳|痛|酸|麻|胀|痒|晕|恶心|呕吐|腹泻|不舒服|精神|状态|感觉|身体|发热|咳嗽|睡得|心情|\b(?:tired|fatigue|pain|feeling|runny nose|well|energy|sore|unwell)\b",
            value,
            re.IGNORECASE,
        ):
            grants.append("record_body")
        if re.search(r"日记|日誌|diary|journal", value, re.IGNORECASE):
            grants.append("save_diary")
    if re.search(r"不要记录|别记录|不用记录|不需要记录", value):
        return ()
    return tuple(sorted(set(grants)))


def allowed_operations(text: str, known_habit_names: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Admit each actual-report clause without letting a future plan erase another domain.

    This boundary grants operations, not extracted facts. The existing Hermes model
    and strict source/quantity/version validation still decide the actual payload.
    """
    if re.search(
        r"^(?:如果|假设|例如|比如|别人说|他说|她说|有人说|引用|明天|后天)|^(?:if |suppose |tomorrow |he said|she said)|^[「『\"]",
        text.strip(),
        re.IGNORECASE,
    ):
        return ()
    if re.search(r"不要记录|别记录|不用记录|不需要记录", text):
        return ()
    grants = set(_clause_operations(text, known_habit_names))
    for clause in re.split(r"[，,。；;\n]", text):
        grants.update(_clause_operations(clause, known_habit_names))
    return tuple(sorted(grants))


class LifeContextBroker:
    def __init__(self, config: dict[str, Any], *, clock=None) -> None:
        if config.get("profile") != "honc" or not config.get("owner_id"):
            raise ValueError("Explicit honc owner/profile binding required")
        self.config = config
        self.clock = clock or (lambda: datetime.now(UTC))
        self.store = LifeStore(HoncStore(Path(config["database_path"])))
        self.runtime = ReminderRuntime(
            self.store,
            owner_id=config["owner_id"],
            delivery_target_id=identity(
                config["profile"],
                config["owner_id"],
                json.dumps(config["delivery_binding"], sort_keys=True),
            ),
        )
        with self.store.transaction() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS life_context_bindings (
                token_digest TEXT PRIMARY KEY, source_ref TEXT NOT NULL REFERENCES life_sources(source_ref),
                session_id TEXT NOT NULL, turn_id TEXT NOT NULL, valid_until TEXT NOT NULL,
                revoked_at TEXT)""")

    def open_message(
        self,
        *,
        raw_content: str,
        transport_id: str,
        session_id: str,
        turn_id: str,
        received_at: datetime,
        actor_id: str,
    ) -> tuple[str, dict[str, Any]]:
        if actor_id != self.config["owner_id"] or not all((transport_id, session_id, turn_id)):
            raise PermissionError(
                "Authenticated owner and actual transport/session/turn are required"
            )
        base = LifeService(
            self.store,
            owner_id=actor_id,
            profile="honc",
            session_id=session_id,
            clock=self.clock,
            reminders=self.runtime,
        )
        with self.store.ledger.connect() as connection:
            rows = connection.execute(
                "SELECT r.payload_json FROM life_objects o JOIN life_revisions r "
                "ON o.object_id=r.object_id AND o.head_revision=r.revision "
                "WHERE o.owner_id=? AND o.kind='habit_definition'",
                (actor_id,),
            ).fetchall()
            names = []
            for row in rows:
                definition = json.loads(row[0])["definition"]
                names.extend([definition["name"], *definition.get("aliases", [])])
            grants = allowed_operations(raw_content, tuple(names))
            prior = connection.execute(
                "SELECT received_at FROM life_sources WHERE owner_id=? AND profile='honc' "
                "AND adapter_id=? AND source_event_id=?",
                (actor_id, "hermes-authenticated-inbound", transport_id),
            ).fetchone()
        receipt = base.receive_user_message(
            adapter_id="hermes-authenticated-inbound",
            source_event_id=transport_id,
            raw_content=raw_content,
            received_at=datetime.fromisoformat(prior[0]) if prior else received_at,
            granted_operations=grants,
        )
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.store.transaction() as connection:
            connection.execute(
                "UPDATE life_context_bindings SET revoked_at=? WHERE session_id=? AND revoked_at IS NULL",
                (self.clock().isoformat(), session_id),
            )
            connection.execute(
                "INSERT INTO life_context_bindings VALUES (?, ?, ?, ?, ?, NULL)",
                (
                    digest,
                    receipt["source_ref"],
                    session_id,
                    turn_id,
                    (self.clock() + timedelta(hours=2)).isoformat(),
                ),
            )
        return token, receipt

    def service(self, token: str | None) -> LifeService:
        if not token:
            raise PermissionError("A host-injected current-message context is required")
        with self.store.ledger.connect() as connection:
            row = connection.execute(
                "SELECT b.*, s.owner_id, s.profile FROM life_context_bindings b "
                "JOIN life_sources s ON s.source_ref=b.source_ref WHERE b.token_digest=?",
                (hashlib.sha256(token.encode()).hexdigest(),),
            ).fetchone()
        if (
            row is None
            or row["revoked_at"]
            or datetime.fromisoformat(row["valid_until"]) <= self.clock()
        ):
            raise PermissionError("The inbound context has expired or was not minted by the host")
        if row["owner_id"] != self.config["owner_id"] or row["profile"] != "honc":
            raise PermissionError("Context belongs to another configured profile/owner")
        return LifeService(
            self.store,
            owner_id=row["owner_id"],
            profile=row["profile"],
            session_id=row["session_id"],
            source_ref=row["source_ref"],
            clock=self.clock,
            reminders=self.runtime,
        )

    def close_turn(self, session_id: str, turn_id: str) -> None:
        with self.store.transaction() as connection:
            connection.execute(
                "UPDATE life_context_bindings SET revoked_at=? "
                "WHERE session_id=? AND turn_id=? AND revoked_at IS NULL",
                (self.clock().isoformat(), session_id, turn_id),
            )
