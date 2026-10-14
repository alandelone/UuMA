"""Source-linked role guidance and a read-only view of the registered Agent capabilities."""
from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from .service import ControlPlane

ROLE_GUIDANCE: dict[str, dict[str, Any]] = {
    "brainstormer": {
        "role": "釐清問題、挑戰假設、比較方案並形成可建造的設計。",
        "suitable_work": ["問題框定", "方案比較與決策分析", "PRD、架構與設計產物"],
        "inputs": ["目標與限制", "現有方案和來源", "需要釐清的決策"],
        "outputs": ["方案與取捨", "假設和未決問題", "有依據的設計或決策提案"],
        "restrictions": ["不代替專家證據", "不自行批准重要決策或指派其他 Agent"],
    },
    "scholar": {
        "role": "以證據支援使用者主導的科學研究。",
        "suitable_work": ["文獻整理與證據綜合", "研究缺口、方法及實驗方案", "科學寫作與審閱"],
        "inputs": ["研究問題與 Track", "文獻或可用證據", "科學審批和實驗限制"],
        "outputs": ["有來源的證據整理", "候選研究缺口或 Blueprint", "研究或稿件產物與限制"],
        "restrictions": [
            "研究問題、核心主張、方法和發表由使用者審閱",
            "需要自己的 ScholarFieldKG；實驗只透過已批准的 RSTV4 計畫",
            "各研究流程的部署與驗收須由 Orchestrator 再確認",
        ],
    },
    "wisdom-oldman": {
        "role": "調查機制與證據，形成、維護並取回可追溯的長期知識。",
        "suitable_work": ["機制、條件與衝突調查", "最佳現有知識回答", "值得追查的知識缺口"],
        "inputs": ["具體問題和用途", "條件與範圍", "來源與已有知識"],
        "outputs": ["有來源、條件及不確定性的回答", "知識候選與缺口", "持久主題文件"],
        "restrictions": [
            "需要自己的知識圖譜", "新主題研究需要相應使用者批准",
            "不能自行批准知識 patch 或增加研究預算",
        ],
    },
    "forge-lab-bot": {
        "role": "把設計與實物連接，管理實驗室庫存、採購證據、構建及工程紀錄。",
        "suitable_work": ["庫存與購買紀錄查詢", "BOM 和構建評估", "採購建議", "工作日誌與故障分析"],
        "inputs": ["物件和規格", "設計版本、訂單或觀察紀錄", "地點與實物狀態"],
        "outputs": ["庫存或訂單證據", "構建與 as-built 分析", "工作日誌及候選工程教訓"],
        "restrictions": [
            "購買紀錄不等於實物庫存", "不購買、不付款、不驅動硬體",
            "工程教訓仍需審閱；eSchematic 保留設計權威",
        ],
    },
    "honc": {
        "role": "日常執行與追蹤管家，管理回合、習慣、執行事實、完成依據及進度對賬。",
        "suitable_work": ["執行事實與成果補記", "回合生命週期與計時", "習慣打卡", "普通 ACTION 完成核對與回寫", "執行日報"],
        "inputs": ["已接受的候選下一步（來自 Graph）", "用戶報告或執行回執", "Done 標準"],
        "outputs": ["執行事實与成果", "Done/Next/Blocker 摘要", "投入工時與習慣進度", "更新回執"],
        "restrictions": [
            "不調整專案樹、里程碑與優先順序",
            "不自動替未達標或缺少標準的任務打 Done",
            "項目決策交給 Yonc，工作任務以 Graph 為權威",
        ],
    },
    "yonc": {
        "role": "管理專案圖、拆解工作、提出分工並審閱進度。",
        "suitable_work": ["專案規劃與拆解", "跨專案優先順序建議", "分工建議與成果審閱"],
        "inputs": ["專案目標和現有圖", "限制、來源及決策", "同事能力資料"],
        "outputs": ["持久拆分草稿", "有依據的分工建議", "進度及待審事項"],
        "restrictions": ["圖提交需要精確版本的可信 UI 授權", "不自行啟動其他 Agent"],
    },
    "orchestrator": {
        "role": "建立與路由任務、執行指派、監控 Agent 工作並執行控制政策。",
        "suitable_work": ["獲批工作的任務指派", "跨 Agent 協調", "執行監控與恢復", "受控電腦操作"],
        "inputs": ["獲批範圍", "任務輸入、交付物與驗收條件", "所需權限和預算"],
        "outputs": ["任務與 Run 收據", "執行狀態和結果", "獨立驗收或阻塞紀錄"],
        "restrictions": ["仍受任務政策和使用者審閱約束", "登記能力不證明當下服務健康"],
    },
}

ROLE_SOURCES = {
    **{agent: (f"docs/agents/{agent}.md", f"profiles/{agent}/SOUL.md")
       for agent in ROLE_GUIDANCE if agent != "orchestrator"},
    "orchestrator": ("docs/agents/README.md", "profiles/orchestrator/SOUL.addendum.md"),
}


def colleague_capabilities(
    control: ControlPlane, *, agent_id: str = "", capability: str = "",
    source_root: Path | None = None,
) -> dict[str, Any]:
    """Read registry state without bootstrapping, routing, assigning, or probing other services."""
    root = source_root or Path(__file__).resolve().parents[2]
    registered = control.list_agents()
    counts: dict[str, Counter[str]] = {}
    active = {"PENDING", "RUNNING", "PAUSED", "BLOCKED", "REVIEW", "CANCEL_REQUESTED"}
    for run in control.list_runs():
        if run["status"] in active:
            counts.setdefault(run["agent_id"], Counter())[run["status"]] += 1
    selected = [
        agent for agent in registered
        if (not agent_id or agent.agent_id == agent_id.strip())
        and (not capability or capability.strip() in agent.capabilities)
    ]
    records = []
    for agent in selected[:50]:
        definition = agent.model_dump(mode="json")
        definition["capabilities"] = sorted(agent.capabilities)
        definition["tools"] = sorted(agent.tools)
        sources = []
        for locator in ROLE_SOURCES.get(agent.agent_id, ()):
            path = root / locator
            sources.append({
                "locator": locator, "available": path.is_file(),
                "sha256": sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
            })
        records.append({
            "agent_id": agent.agent_id, "display_name": agent.display_name,
            "registered_definition": definition,
            "definition_sha256": sha256(json.dumps(
                definition, sort_keys=True, ensure_ascii=False,
            ).encode()).hexdigest(),
            "role_guidance": ROLE_GUIDANCE.get(agent.agent_id),
            "role_guidance_reviewed_on": "2026-09-30" if agent.agent_id in ROLE_GUIDANCE else None,
            "role_sources": sources,
            "active_run_counts": dict(counts.get(agent.agent_id, {})),
            "runtime_readiness": "NOT_CHECKED",
        })
    return {
        "observed_at": datetime.now(UTC).isoformat(),
        "registry_source": "UuMA Agent registry and Run projections",
        "agents": records, "total_count": len(selected), "has_more": len(selected) > 50,
        "unregistered_role_ids": sorted(set(ROLE_GUIDANCE) - {a.agent_id for a in registered}),
        "supporting_systems": [
            {"name": "eSchematic", "kind": "domain_system", "request_through": "forge-lab-bot",
             "scope": "元件、電路圖、設計 BOM 與版本；不是獨立 Worker。"},
            {"name": "CopyCat", "kind": "orchestrator_service", "request_through": "orchestrator",
             "scope": "Orchestrator 控制的電腦操作服務；不是獨立 Worker。"},
        ],
        "interpretation": (
            "Role guidance describes suitable proposals, not verified deployment of every workflow. "
            "Registered enabled state and active Run counts are not online or service-health checks. "
            "Orchestrator must validate current permissions and runtime readiness before dispatch. "
            "This lookup creates no tasks, approvals, or assignments."
        ),
    }
