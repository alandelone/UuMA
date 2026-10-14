from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .models import (
    ActualKind,
    AssessmentResult,
    Round,
    TrustedInput,
)
from .service import HoncService


@dataclass
class InputOrigin:
    sender_id: str
    channel: str = "hermes_local"  # "hermes_local", "telegram"
    chat_type: str = "private"  # "private", "group", "supergroup", "channel"
    profile_target: str = "honc"
    message_id: str | None = None
    is_bot_or_agent: bool = False
    is_forward_or_quote: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    valid: bool
    can_authorize_completion: bool
    reason: str
    trusted_input: TrustedInput | None = None


@dataclass
class CandidateResolution:
    resolved_node_id: str | None
    is_ambiguous: bool
    candidates: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""


@dataclass
class ConversationResult:
    reply_text: str
    intent_kind: str
    trusted_input_id: str | None = None
    event_id: str | None = None
    round_id: str | None = None
    task_id: str | None = None
    assessment_result: str | None = None
    graph_update_status: str | None = None
    receipt_refs: dict[str, Any] = field(default_factory=dict)
    next_action: str = "NONE"


class HoncConversationEngine:
    """Manages conversational inputs, origin security validation, and completion gating."""

    def __init__(
        self,
        service: HoncService,
        bound_user_id: str = "default_user",
        bound_telegram_user_id: str | None = None,
    ) -> None:
        self.service = service
        self.bound_user_id = bound_user_id
        self.bound_telegram_user_id = bound_telegram_user_id

    # -------------------------------------------------------------------------
    # 1. Input Origin Validation
    # -------------------------------------------------------------------------

    def validate_origin(self, origin: InputOrigin, raw_content: str) -> ValidationResult:
        """Validate input authenticity and authorization for task completion decisions."""
        # 1. Bot or Agent messages cannot authorize completion
        if origin.is_bot_or_agent:
            return ValidationResult(
                valid=True,
                can_authorize_completion=False,
                reason="消息来源为机器人或其他 Agent，不能作为任务完成的有效授权。",
            )

        # 2. Forwarded or quoted messages cannot authorize completion
        if origin.is_forward_or_quote:
            return ValidationResult(
                valid=True,
                can_authorize_completion=False,
                reason="转述、转发或引用的消息不能作为用户本人的直接完成授权。",
            )

        # 3. Target profile check
        if origin.profile_target != "honc":
            return ValidationResult(
                valid=False,
                can_authorize_completion=False,
                reason=f"目标身份必须为 honc，收到 {origin.profile_target}。",
            )

        # 4. Telegram-specific constraints: strictly private chat and bound sender
        if origin.channel == "telegram":
            if origin.chat_type != "private":
                return ValidationResult(
                    valid=True,
                    can_authorize_completion=False,
                    reason="群聊或频道消息禁止触发任务完成回写，仅支持私聊。",
                )
            if self.bound_telegram_user_id and origin.sender_id != self.bound_telegram_user_id:
                return ValidationResult(
                    valid=False,
                    can_authorize_completion=False,
                    reason=f"未绑定的 Telegram 用户 {origin.sender_id}，拒绝执行。",
                )

        # 5. Local channel constraints
        elif origin.channel == "hermes_local":
            if origin.sender_id and origin.sender_id != self.bound_user_id:
                return ValidationResult(
                    valid=False,
                    can_authorize_completion=False,
                    reason=f"非绑定本地用户 {origin.sender_id}。",
                )

        # Valid trusted user input
        inp = self.service.store.record_trusted_input(
            TrustedInput(
                user_id=origin.sender_id or self.bound_user_id,
                entrypoint=origin.channel,
                profile=origin.profile_target,
                source_receipt_id=origin.message_id,
                raw_content=raw_content,
                metadata=origin.metadata,
            )
        )
        return ValidationResult(
            valid=True,
            can_authorize_completion=True,
            reason="用户直接输入，来源可信。",
            trusted_input=inp,
        )

    # -------------------------------------------------------------------------
    # 2. Intent Recognition
    # -------------------------------------------------------------------------

    def detect_intent(self, text: str) -> str:
        """Categorize user's natural language input into operational intent."""
        t = text.strip().lower()

        # Correction
        if re.search(r"弄错了|写错了|纠正|其实只|撤回|重新标记|不是完成", t):
            return "correction"

        # Inquiry
        if re.search(r"今天做(?:了|过)什么|查看进度|今天进度|执行日记|日报|当前状态|有什么坑", t):
            return "inquiry"

        # Habit
        if re.search(r"打卡|喝水|锻体|健身|背单词|深蹲|吃药", t):
            return "habit"

        # Round control
        if re.search(r"准备|开始(?:番茄|专注|回合)|暂停|继续|结束(?:番茄|回合)|放弃|取消回合", t):
            return "round_control"

        # Explicit completion
        if re.search(
            r"完成(?:了)?|搞定(?:了)?|做好(?:了)?|验收通过|做完(?:了)?|已经写好", t
        ) and not re.search(r"没完成|还没|只完成|尚未|未达标|但是没|差一点|初稿", t):
            return "complete"

        # Default to general progress / execution fact
        return "progress"

    # -------------------------------------------------------------------------
    # 3. Target Node Resolution
    # -------------------------------------------------------------------------

    def resolve_target_node(
        self,
        text: str,
        active_round: Round | None,
        available_nodes: list[dict[str, Any]] | None = None,
    ) -> CandidateResolution:
        """Resolve a specific Graph ACTION node referenced in the user's message."""
        nodes = available_nodes or []

        # 1. Direct ID match in text
        for node in nodes:
            nid = str(node.get("id") or "")
            if nid and nid.lower() in text.lower():
                return CandidateResolution(
                    resolved_node_id=nid, is_ambiguous=False, candidates=[node]
                )

        # 2. Title keyword match
        matched_nodes = []
        for node in nodes:
            title = str(node.get("title") or "")
            if not title:
                continue
            # A. Exact title substring in text
            if title.lower() in text.lower():
                matched_nodes.append(node)
                continue
            # B. English whitespace/punctuation tokens in text
            words = [w.lower() for w in re.split(r"[\s_\-/,]+", title) if len(w) > 2]
            if words and any(w in text.lower() for w in words):
                matched_nodes.append(node)
                continue
            # C. Subphrase tokens from user query in title
            phrases = [p for p in re.split(r"[\s,，。！!？?]+", text) if len(p) >= 2]
            matched_phrase = False
            for p in phrases:
                cleaned = re.sub(
                    r"完成(?:了)?|搞定(?:了)?|做好(?:了)?|做完(?:了)?|我已经|修好了", "", p
                ).strip()
                if len(cleaned) >= 2 and cleaned.lower() in title.lower():
                    matched_nodes.append(node)
                    matched_phrase = True
                    break
            if matched_phrase:
                continue

        if len(matched_nodes) == 1:
            return CandidateResolution(
                resolved_node_id=matched_nodes[0]["id"],
                is_ambiguous=False,
                candidates=matched_nodes,
            )
        elif len(matched_nodes) > 1:
            return CandidateResolution(
                resolved_node_id=None,
                is_ambiguous=True,
                candidates=matched_nodes,
                reason=f"匹配到多个候选任务: {', '.join(n.get('title', '') for n in matched_nodes)}",
            )

        # 3. Fallback to active round's task_id if present
        if active_round and active_round.task_id:
            return CandidateResolution(
                resolved_node_id=active_round.task_id,
                is_ambiguous=False,
                candidates=[{"id": active_round.task_id}],
                reason="使用当前活动回合关联的任务。",
            )

        # 4. If only one actionable node available in current Main/Support
        action_nodes = [
            n
            for n in nodes
            if n.get("work_type") == "ACTION" and n.get("status") in ("TODO", "DOING")
        ]
        if len(action_nodes) == 1:
            return CandidateResolution(
                resolved_node_id=action_nodes[0]["id"],
                is_ambiguous=False,
                candidates=action_nodes,
                reason="自动匹配当前唯一待执行的 ACTION 任务。",
            )
        elif len(action_nodes) > 1:
            return CandidateResolution(
                resolved_node_id=None,
                is_ambiguous=True,
                candidates=action_nodes,
                reason="未指明任务名称，当前存在多个待完成候选任务。",
            )

        return CandidateResolution(
            resolved_node_id=None, is_ambiguous=False, reason="未找到可匹配的待执行任务。"
        )

    # -------------------------------------------------------------------------
    # 4. Process Message End-to-End
    # -------------------------------------------------------------------------

    def process_message(
        self,
        origin: InputOrigin,
        raw_text: str,
        available_nodes: list[dict[str, Any]] | None = None,
        duration_seconds: int | None = None,
        occurred_at: str | None = None,
    ) -> ConversationResult:
        """Full end-to-end processing pipeline for honc conversational turns."""
        # Step A: Validate origin
        v_res = self.validate_origin(origin, raw_text)
        if not v_res.valid:
            return ConversationResult(
                reply_text=f"拒绝处理：{v_res.reason}",
                intent_kind="rejected",
                receipt_refs={"validation_error": v_res.reason},
            )

        inp_id = v_res.trusted_input.input_id if v_res.trusted_input else None
        active_round = self.service.store.get_active_round(self.bound_user_id)
        intent = self.detect_intent(raw_text)

        # Step B: Handle Correction
        if intent == "correction":
            recent_events = self.service.store.list_events(limit=1)
            orig_id = recent_events[0].event_id if recent_events else "unknown"
            corr = self.service.correct_record(
                original_event_id=orig_id,
                reason=raw_text,
                user_id=self.bound_user_id,
                compensating_action="reopen" if "撤回" in raw_text else None,
            )
            return ConversationResult(
                reply_text=f"已追加修正事实：{raw_text}。原始历史已保留；当前状态已更新。",
                intent_kind="correction",
                trusted_input_id=inp_id,
                event_id=corr["record_id"],
                assessment_result="CORRECTED",
                graph_update_status=corr["graph_update_status"],
                receipt_refs=corr["receipt_refs"],
            )

        # Step C: Handle Inquiries
        if intent == "inquiry":
            rep = self.service.get_report(user_id=self.bound_user_id)
            done_count = len(rep["done_items"])
            minutes = rep["active_minutes"]
            reply = (
                f"📊 今日执行概况 ({rep['date']})：\n"
                f"- 产生交付成果: {done_count} 项\n"
                f"- 累计投入时长: {minutes} 分钟 (计时 {round(rep['timed_seconds'] / 60, 1)}m)\n"
                f"- 当前 Next: {rep['next_items'][:2]}\n"
                f"- 当前 Blocker: {rep['blockers'][:2] or ['无卡点']}\n"
                f"- 待处理同步项: {rep['pending_outbox_count']} 个"
            )
            return ConversationResult(
                reply_text=reply,
                intent_kind="inquiry",
                trusted_input_id=inp_id,
            )

        # Step D: Handle Habit
        if intent == "habit":
            habit_id = "general_habit"
            for h in ("water", "stretch", "workout", "reading", "vocabulary"):
                if h in raw_text.lower() or h in raw_text:
                    habit_id = h
                    break
            tick = self.service.check_habit(
                habit_id=habit_id,
                user_id=self.bound_user_id,
                user_report=raw_text,
                occurred_at=occurred_at,
            )
            return ConversationResult(
                reply_text=f"打卡已记录：{raw_text}。已计入今日账本。",
                intent_kind="habit",
                trusted_input_id=inp_id,
                event_id=tick["record_id"],
                next_action="NONE",
            )

        # Step E: Handle Round Control
        if intent == "round_control":
            if "准备" in raw_text:
                ctrl = self.service.control_round(
                    action="prepare",
                    user_id=self.bound_user_id,
                    target_outcome=raw_text,
                    tiny_step="打开工作文件并写前两行",
                )
                return ConversationResult(
                    reply_text=f"🛸 回合已准备就绪！果象：{raw_text}。随时可以开始专注番茄钟。",
                    intent_kind="round_control",
                    trusted_input_id=inp_id,
                    round_id=ctrl["round_id"],
                    next_action="START_ROUND",
                )
            elif "开始" in raw_text:
                if not active_round:
                    # Auto-prepare and start
                    p = self.service.control_round(
                        action="prepare", target_outcome="专注工作", tiny_step="开始行动"
                    )
                    ctrl = self.service.control_round(action="start", round_id=p["round_id"])
                else:
                    ctrl = self.service.control_round(
                        action="start", round_id=active_round.round_id
                    )
                return ConversationResult(
                    reply_text=f"🍅 番茄钟已开跑！状态：{ctrl['status']}。专注开始，请全神贯注。",
                    intent_kind="round_control",
                    trusted_input_id=inp_id,
                    round_id=ctrl["round_id"],
                    next_action="FOCUS",
                )
            elif "暂停" in raw_text and active_round:
                ctrl = self.service.control_round(action="pause", round_id=active_round.round_id)
                return ConversationResult(
                    reply_text="⏸ 回合已暂停。暂停时间不计入工时，稍后可随时恢复。",
                    intent_kind="round_control",
                    trusted_input_id=inp_id,
                    round_id=ctrl["round_id"],
                    next_action="RESUME_OR_END",
                )
            elif ("结束" in raw_text or "完成回合" in raw_text) and active_round:
                ctrl = self.service.control_round(
                    action="end", round_id=active_round.round_id, outcome=raw_text
                )
                dur = ctrl.get("observed_duration_seconds", 0)
                return ConversationResult(
                    reply_text=f"🏁 回合已结束！本轮累计有效投入 {round(dur / 60, 1)} 分钟。请留下本轮产出成果、Next 与 Blocker。",
                    intent_kind="round_control",
                    trusted_input_id=inp_id,
                    round_id=ctrl["round_id"],
                    next_action="RECORD_OUTCOME",
                )

        # Step F: Handle Explicit Completion vs Progress
        res_cand = self.resolve_target_node(raw_text, active_round, available_nodes)
        target_task_id = res_cand.resolved_node_id

        # 1. If user asserts completion
        if intent == "complete":
            # Guard: Can this message authorize completion?
            if not v_res.can_authorize_completion:
                # Record fact only
                ev = self.service.record_execution(
                    raw_content=raw_text,
                    user_id=self.bound_user_id,
                    task_id=target_task_id,
                    outcome=raw_text,
                    actual_duration_seconds=duration_seconds,
                    occurred_at=occurred_at,
                )
                return ConversationResult(
                    reply_text=f"已记录事实，但因来源限制（{v_res.reason}），未自动标记任务完成。",
                    intent_kind="progress",
                    trusted_input_id=inp_id,
                    event_id=ev["record_id"],
                    task_id=target_task_id,
                )

            # Guard: Ambiguous candidates
            if res_cand.is_ambiguous:
                ev = self.service.record_execution(
                    raw_content=raw_text,
                    user_id=self.bound_user_id,
                    outcome=raw_text,
                    actual_duration_seconds=duration_seconds,
                    occurred_at=occurred_at,
                )
                cand_names = [n.get("title", n.get("id")) for n in res_cand.candidates[:3]]
                return ConversationResult(
                    reply_text=(
                        f"已记录你的完成报告，但目前存在多个候选任务（{', '.join(cand_names)}），"
                        "请指明具体是哪项任务，以免误更。"
                    ),
                    intent_kind="ambiguous_complete",
                    trusted_input_id=inp_id,
                    event_id=ev["record_id"],
                    next_action="CLARIFY_TARGET_TASK",
                )

            # Guard: No target task matched
            if not target_task_id:
                ev = self.service.record_execution(
                    raw_content=raw_text,
                    user_id=self.bound_user_id,
                    outcome=raw_text,
                    actual_duration_seconds=duration_seconds,
                    occurred_at=occurred_at,
                )
                return ConversationResult(
                    reply_text="已记录执行事实，但当前没有正在进行的任务或匹配对象。任务状态保持原样。",
                    intent_kind="unlinked_complete",
                    trusted_input_id=inp_id,
                    event_id=ev["record_id"],
                )

            # Check candidate node constraints (e.g. work_type must be ACTION)
            target_node = next(
                (n for n in (available_nodes or []) if n.get("id") == target_task_id), None
            )
            if target_node:
                work_type = target_node.get("work_type", "ACTION")
                if work_type != "ACTION":
                    ev = self.service.record_execution(
                        raw_content=raw_text,
                        user_id=self.bound_user_id,
                        task_id=target_task_id,
                        outcome=raw_text,
                    )
                    return ConversationResult(
                        reply_text=(
                            f"目标节点「{target_node.get('title')}」为 {work_type} 类型（非 ACTION），"
                            "日常执行管家仅能自动完成 ACTION 叶子节点，里程碑/项目须走 Yonc 评审流程。"
                        ),
                        intent_kind="blocked_non_action",
                        trusted_input_id=inp_id,
                        event_id=ev["record_id"],
                        task_id=target_task_id,
                    )
                if target_node.get("status") == "REVIEW":
                    ev = self.service.record_execution(
                        raw_content=raw_text,
                        user_id=self.bound_user_id,
                        task_id=target_task_id,
                        outcome=raw_text,
                    )
                    return ConversationResult(
                        reply_text=f"任务「{target_node.get('title')}」处于专门复核（REVIEW）阶段，需专门审核，已保留事实。",
                        intent_kind="blocked_review",
                        trusted_input_id=inp_id,
                        event_id=ev["record_id"],
                        task_id=target_task_id,
                    )

            # Perform done_when assessment
            criteria_from_node = target_node.get("done_when") if target_node else None
            ass = self.service.assess_completion(
                task_id=target_task_id,
                evidence=raw_text,
                criteria_override=criteria_from_node,
                trusted_input_id=inp_id,
            )

            # Record execution fact regardless
            ev = self.service.record_execution(
                raw_content=raw_text,
                user_id=self.bound_user_id,
                task_id=target_task_id,
                round_id=active_round.round_id if active_round else None,
                outcome=raw_text,
                actual_kind=ActualKind.TIMED if duration_seconds else ActualKind.UNKNOWN,
                actual_duration_seconds=duration_seconds,
                occurred_at=occurred_at,
            )

            if ass["result"] != AssessmentResult.SATISFIED:
                missing = ass.get("missing_items", [])
                return ConversationResult(
                    reply_text=(
                        f"已记录进展。但根据任务验收标准，仍有未满足项：{missing}。"
                        "任务保持未完成状态，待满足后再同步。"
                    ),
                    intent_kind="insufficient_criteria",
                    trusted_input_id=inp_id,
                    event_id=ev["record_id"],
                    task_id=target_task_id,
                    assessment_result=ass["result"],
                    receipt_refs={"assessment_id": ass["assessment_id"]},
                    next_action="SATISFY_REMAINING_CRITERIA",
                )

            # Criteria fully satisfied -> apply completion to Graph!
            app = self.service.apply_completion(
                task_id=target_task_id,
                trusted_input_id=inp_id,
                user_id=self.bound_user_id,
                assessment_id=ass["assessment_id"],
            )

            graph_st = app.get("graph_update_status", "UNKNOWN")
            reply_msg = (
                f"✅ 任务「{target_node.get('title') if target_node else target_task_id}」已判定达到验收标准并完成！\n"
                f"- Graph 更新状态: {graph_st}\n"
                f"- 执行回执 ID: {app.get('operation_id')}\n"
                f"- 执行账本记录: {ev['record_id']}"
            )
            return ConversationResult(
                reply_text=reply_msg,
                intent_kind="complete",
                trusted_input_id=inp_id,
                event_id=ev["record_id"],
                task_id=target_task_id,
                assessment_result="SATISFIED",
                graph_update_status=graph_st,
                receipt_refs=app.get("receipt_refs", {}),
                next_action="NONE",
            )

        # 2. General progress (did some work, but didn't claim done)
        ev = self.service.record_execution(
            raw_content=raw_text,
            user_id=self.bound_user_id,
            task_id=target_task_id,
            round_id=active_round.round_id if active_round else None,
            outcome=raw_text,
            actual_kind=ActualKind.TIMED if duration_seconds else ActualKind.UNKNOWN,
            actual_duration_seconds=duration_seconds,
            occurred_at=occurred_at,
        )
        return ConversationResult(
            reply_text=f"进展已记入账本。任务保持未完成，记录 ID: {ev['record_id']}。",
            intent_kind="progress",
            trusted_input_id=inp_id,
            event_id=ev["record_id"],
            task_id=target_task_id,
            next_action="CONTINUE_EXECUTION",
        )
