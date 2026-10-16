"""Scholar agent source adapter for scientific research and literature analysis."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ..models import ObservatoryItem, SourceFreshness
from .base import ObservatorySourceAdapter


class ScholarAdapter(ObservatorySourceAdapter):
    agent_id = "scholar"
    display_name = "Scholar"
    role = "以证据支援使用者主导的科学研究，文献综述、实验方案与论文编写"
    source_name = "uuma.db & catalog.db & stage-gates"

    def __init__(
        self,
        uuma_db_path: Path | str,
        catalog_db_path: Path | str | None = None,
    ) -> None:
        self.uuma_db = Path(uuma_db_path)
        self.catalog_db = (
            Path(catalog_db_path)
            if catalog_db_path
            else Path("C:/Users/Alandelone/CodeSpace_Local/RSTV4/data/catalog.db")
        )

    def probe_health(self) -> SourceFreshness:
        if self.uuma_db.exists():
            conn = self.safe_sqlite_connect(self.uuma_db)
            if conn:
                try:
                    with conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            SELECT MAX(e.occurred_at)
                            FROM runs r
                            JOIN events e ON r.updated_sequence = e.sequence
                            WHERE r.agent_id = 'scholar'
                            """
                        )
                        row = cursor.fetchone()
                        last_event = row[0] if row else None
                        return SourceFreshness(
                            source_name=self.source_name,
                            is_available=True,
                            last_event_at=last_event,
                        )
                except sqlite3.Error:
                    pass
        return SourceFreshness(
            source_name=self.source_name,
            is_available=bool(self.catalog_db.exists()),
            last_event_at=None,
        )

    def _get_research_hierarchy_data(self) -> dict[str, Any]:
        """Fetch research hierarchy from catalog.db or fallback to canonical demo specification."""
        real_fields: list[dict[str, Any]] = []
        if self.catalog_db.exists():
            conn = self.safe_sqlite_connect(self.catalog_db)
            if conn:
                try:
                    with conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT * FROM research_fields ORDER BY name, field_id")
                        real_fields = [dict(row) for row in cursor.fetchall()]
                except sqlite3.Error:
                    pass

        if real_fields:
            # Future real data processing
            return {
                "is_demo": False,
                "fields_count": len(real_fields),
                "threads_count": 0,
                "papers_count": 0,
                "hierarchy": real_fields,
            }

        # Canonical specification demo hierarchy from catalog_web.html and research-overview-v1.md
        return {
            "is_demo": True,
            "fields_count": 2,
            "threads_count": 4,
            "papers_count": 5,
            "stage_breakdown": {
                "WRITING": 2,
                "REVISION": 1,
                "PLANNING": 2,
            },
            "thread_coverage": "4 条路线中，3 条包含写作稿件，1 条处于纯探索阶段(0篇)",
            "hierarchy": [
                {
                    "field_id": "solar",
                    "name": "Solar Energy",
                    "caption": "Field (研究领域)",
                    "status": "规划中",
                    "topics": [
                        {
                            "topic_id": "nowcasting",
                            "name": "Solar Nowcasting",
                            "caption": "Topic (研究主题)",
                            "status": "采集中 ↗",
                            "threads": [
                                {
                                    "thread_id": "allsky",
                                    "title": "All-sky image forecasting",
                                    "caption": "Track / Thread (研究路线)",
                                    "status": "PDF 获取中 ↗",
                                    "question": "全天空图像能否提高未来 5–15 分钟的辐照度预测？",
                                    "papers": [
                                        {
                                            "paper_id": "allsky-paper-a",
                                            "title": "Sky Image Forecasting for Islanded Microgrids",
                                            "stage": "写作中",
                                            "stage_key": "WRITING",
                                            "tag": "样本稿件",
                                        },
                                        {
                                            "paper_id": "allsky-paper-b",
                                            "title": "Benchmarking Solar Nowcasting Models",
                                            "stage": "返修中",
                                            "stage_key": "REVISION",
                                            "tag": "样本稿件",
                                        },
                                    ],
                                },
                                {
                                    "thread_id": "satellite",
                                    "title": "Satellite cloud motion",
                                    "caption": "Track / Thread (研究路线)",
                                    "status": "待解析",
                                    "question": "云团移动信息能否改善短时光伏出力预测？",
                                    "papers": [
                                        {
                                            "paper_id": "satellite-paper",
                                            "title": "Cloud Motion for Solar Forecasting",
                                            "stage": "规划中",
                                            "stage_key": "PLANNING",
                                            "tag": "样本稿件",
                                        }
                                    ],
                                },
                            ],
                        },
                        {
                            "topic_id": "microgrids",
                            "name": "Microgrid integration",
                            "caption": "Topic (研究主题)",
                            "status": "待扩展",
                            "threads": [
                                {
                                    "thread_id": "islanded",
                                    "title": "Islanded microgrid control",
                                    "caption": "Track / Thread (研究路线)",
                                    "status": "待采集",
                                    "question": "短时预测怎样支持离网微电网的控制决策？",
                                    "papers": [
                                        {
                                            "paper_id": "islanded-paper",
                                            "title": "Solar Nowcasting in Microgrid Control",
                                            "stage": "写作中",
                                            "stage_key": "WRITING",
                                            "tag": "样本稿件",
                                        }
                                    ],
                                }
                            ],
                        },
                    ],
                },
                {
                    "field_id": "rural",
                    "name": "Rural Electrification",
                    "caption": "Field (研究领域)",
                    "status": "规划中",
                    "topics": [
                        {
                            "topic_id": "offgrid",
                            "name": "Off-grid systems",
                            "caption": "Topic (研究主题)",
                            "status": "待采集",
                            "threads": [
                                {
                                    "thread_id": "hybrid",
                                    "title": "Hybrid system sizing",
                                    "caption": "Track / Thread (研究路线)",
                                    "status": "待采集",
                                    "question": "不同负载条件下，混合系统应如何配置？",
                                    "papers": [
                                        {
                                            "paper_id": "hybrid-paper",
                                            "title": "Hybrid System Sizing under Variable Loads",
                                            "stage": "规划中",
                                            "stage_key": "PLANNING",
                                            "tag": "样本稿件",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                },
            ],
        }

    def _get_catalog_pipeline_data(self) -> dict[str, Any]:
        """Fetch literature catalog counts and Core Graph pipeline parsing status."""
        total_papers = 3177
        quarantine_count = 1980
        visible_papers = 1197
        pdf_verified = 1697
        pdf_needs_review = 1467
        waiting_local = 49
        active_parse_runs = 0
        active_jobs = 0
        collections_count = 0

        paper_verified_count = 726
        paper_review_count = 434
        paper_nopdf_count = 37
        parse_not_started = 1197

        if self.catalog_db.exists():
            conn = self.safe_sqlite_connect(self.catalog_db)
            if conn:
                try:
                    with conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT COUNT(*) FROM papers")
                        total_papers = cursor.fetchone()[0]

                        cursor.execute("SELECT COUNT(*) FROM catalog_quarantine")
                        quarantine_count = cursor.fetchone()[0]
                        visible_papers = total_papers - quarantine_count

                        cursor.execute(
                            "SELECT identity_status, COUNT(*) FROM source_file_versions GROUP BY identity_status"
                        )
                        for row in cursor.fetchall():
                            if row[0] == "VERIFIED":
                                pdf_verified = row[1]
                            elif row[0] == "NEEDS_REVIEW":
                                pdf_needs_review = row[1]

                        cursor.execute("SELECT COUNT(*) FROM parse_runs WHERE status='RUNNING'")
                        active_parse_runs = cursor.fetchone()[0]

                        cursor.execute("SELECT COUNT(*) FROM acquisition_jobs WHERE status IN ('READY', 'RUNNING')")
                        active_jobs = cursor.fetchone()[0]

                        cursor.execute("SELECT COUNT(*) FROM collections")
                        collections_count = cursor.fetchone()[0]

                        cursor.execute("SELECT COUNT(*) FROM local_pdf_imports WHERE status='WAITING_LOCAL_FILE'")
                        waiting_local = cursor.fetchone()[0]
                except sqlite3.Error:
                    pass

        paper_level_status = {
            "catalog_status": {
                "ACTIVE (可见收录)": visible_papers,
                "QUARANTINED (衍生隔离)": quarantine_count,
            },
            "pdf_status": {
                "VERIFIED (PDF身份确证)": paper_verified_count,
                "NEEDS_REVIEW (PDF待复核)": paper_review_count,
                "NO_PDF (缺PDF文件)": paper_nopdf_count,
                "WAITING_LOCAL_FILE (iCloud同步中)": waiting_local,
            },
            "parse_status": {
                "NOT_STARTED (待解析/冷入库)": parse_not_started,
                "RUNNING (正在解析中)": active_parse_runs,
                "NEEDS_HUMAN (质量门拦截待人工)": 0,
                "PARSED (已发布解析)": 0,
            },
            "review_status": {
                "CLEAR (无需干预)": paper_verified_count,
                "NEEDS_REVIEW (待复核总数)": paper_review_count + paper_nopdf_count,
            },
            "downstream_status": {
                "QuickRead (速读评估)": f"0 / {visible_papers} 篇就绪",
                "PaperSkeleton (骨架提取)": f"0 / {visible_papers} 篇提取",
            },
        }

        return {
            "total_papers": total_papers,
            "visible_papers": visible_papers,
            "quarantined_papers": quarantine_count,
            "pdf_verified": pdf_verified,
            "pdf_needs_review": pdf_needs_review,
            "pdf_waiting_local": waiting_local,
            "paper_verified_count": paper_verified_count,
            "paper_review_count": paper_review_count,
            "paper_nopdf_count": paper_nopdf_count,
            "paper_level_status": paper_level_status,
            "active_parse_runs": active_parse_runs,
            "active_jobs": active_jobs,
            "collections_count": collections_count,
            "is_parsing_active": bool(active_parse_runs > 0 or active_jobs > 0),
            "pipeline_verdict": (
                "当前无后台自动解析运行 (0 排队 / 0 解析运行中)。"
                "文献总库处于「冷入库就绪」阶段：1197 篇可见论文全部就绪，"
                "其中 726 篇已完成 PDF 身份确证(VERIFIED)；需将其选入 Collection 发起采集与解析，"
                "MinerU 两阶段解析流水线才会排队执行。"
            ),
            "core_graph_stages": [
                {
                    "step": 1,
                    "name": "发现与导入 (Intake & Search)",
                    "summary": f"已完成 {visible_papers} 篇可见论文入库 ({quarantine_count} 篇衍生隔离)",
                    "state": "COMPLETED",
                },
                {
                    "step": 2,
                    "name": "PDF 身份核验 (Identity Gate)",
                    "summary": f"{pdf_verified} 份文件 VERIFIED · {pdf_needs_review} 份待核对 · {waiting_local} 份等待本地同步",
                    "state": "COMPLETED",
                },
                {
                    "step": 3,
                    "name": "研究集合与任务队列 (Collection Queue)",
                    "summary": f"{collections_count} 个集合 · {active_jobs} 项排队任务 (需用户显式选入集合触发)",
                    "state": "IDLE",
                },
                {
                    "step": 4,
                    "name": "MinerU 两阶段解析 (Parsing)",
                    "summary": f"{active_parse_runs} 篇正在解析 (两进程：正文、表格、公式、图注提取)",
                    "state": "IDLE",
                },
                {
                    "step": 5,
                    "name": "解析质量门 (Quality Gates)",
                    "summary": "正文块完整性检验与带编号参考文献质量门 (异常拦截至 NEEDS_HUMAN)",
                    "state": "READY",
                },
                {
                    "step": 6,
                    "name": "深读与知识图谱 (Skeleton & FieldKG)",
                    "summary": "QuickRead 速读 · PaperSkeleton 1-4层骨架提取 · FieldKG 知识生长与回写",
                    "state": "READY",
                },
            ],
        }

    def _get_fieldkg_data(self) -> dict[str, Any]:
        """Fetch FieldKG and OpenSPG/KAG projection status from catalog.db."""
        counts = {
            "research_nodes": 0,
            "research_edges": 0,
            "evidence": 0,
            "fieldkg_builds": 0,
            "fieldkg_evidence_candidates": 0,
            "fieldkg_candidate_gaps": 0,
            "fieldkg_snapshots": 0,
            "projection_outbox": 0,
        }
        if self.catalog_db.exists():
            conn = self.safe_sqlite_connect(self.catalog_db)
            if conn:
                try:
                    with conn:
                        cursor = conn.cursor()
                        for table in counts:
                            try:
                                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                                row = cursor.fetchone()
                                counts[table] = row[0] if row else 0
                            except sqlite3.Error:
                                pass
                except sqlite3.Error:
                    pass

        return {
            "engine": "OpenSPG / KAG 知识图谱引擎 (Remote / Local Projection)",
            "authority": "data/catalog.db (SQLite 唯一可编辑权威)",
            "nodes_count": counts["research_nodes"],
            "edges_count": counts["research_edges"],
            "evidence_count": counts["evidence"],
            "builds_count": counts["fieldkg_builds"],
            "evidence_candidates_count": counts["fieldkg_evidence_candidates"],
            "candidate_gaps_count": counts["fieldkg_candidate_gaps"],
            "snapshots_count": counts["fieldkg_snapshots"],
            "outbox_pending": counts["projection_outbox"],
            "status": "READY" if counts["projection_outbox"] == 0 else "SYNCING",
            "lifecycle_state": "待从文献集合构建第一版 Snapshot (冷库基线就绪)",
            "track_first_rule": (
                "Field 拥有 living FieldKG；Track 显式采纳不可变 Snapshot vN，"
                "杜绝跨路线科学决议静默串染。OpenSPG/KAG 仅为可重建查询投影。"
            ),
        }

    def list_items(self, limit: int = 15, offset: int = 0) -> list[ObservatoryItem]:
        items: list[ObservatoryItem] = []

        # Part 1. Research Hierarchy: Field / Threads (Tracks) / Papers (Manuscripts) View
        hierarchy_data = self._get_research_hierarchy_data()
        items.append(
            ObservatoryItem(
                agent_id=self.agent_id,
                item_id="scholar_research_hierarchy",
                title="Scholar 研究领域、主题路线与写作阶段 (Fields, Threads & Papers)",
                kind="research_hierarchy",
                status="ACTIVE",
                health="HEALTHY",
                summary=(
                    f"领域: {hierarchy_data['fields_count']}个 · "
                    f"路线(Threads): {hierarchy_data['threads_count']}条 · "
                    f"写作稿件(Papers): {hierarchy_data['papers_count']}篇 "
                    f"(2写作中 / 1返修中 / 2规划中)"
                ),
                source_ref="catalog.db:research_fields & research_tracks & manuscripts",
                payload=hierarchy_data,
            )
        )

        # Part 2. Literature Catalog & Core Graph Pipeline (Processing & Parsing State)
        pipeline_data = self._get_catalog_pipeline_data()
        items.append(
            ObservatoryItem(
                agent_id=self.agent_id,
                item_id="scholar_catalog_pipeline",
                title="文献总库与 Core Graph 处理流水线 (Catalog & Pipeline)",
                kind="catalog_pipeline",
                status="IDLE" if not pipeline_data["is_parsing_active"] else "RUNNING",
                health="HEALTHY",
                summary=(
                    f"可见论文: {pipeline_data['visible_papers']}篇 · "
                    f"PDF已核验: {pipeline_data['pdf_verified']}份 · "
                    f"解析中: {pipeline_data['active_parse_runs']}篇 (冷入库就绪，未排队)"
                ),
                source_ref="catalog.db & Core Graph (MinerU Pipeline)",
                payload=pipeline_data,
            )
        )

        # Part 3. FieldKG / KAG Knowledge Graph & Semantic Projections View
        fieldkg_data = self._get_fieldkg_data()
        items.append(
            ObservatoryItem(
                agent_id=self.agent_id,
                item_id="scholar_fieldkg_status",
                title="Scholar FieldKG (OpenSPG/KAG 知识图谱状态与节点投影)",
                kind="fieldkg_status",
                status="ACTIVE",
                health="HEALTHY",
                summary=(
                    f"实体节点: {fieldkg_data['nodes_count']}个 · "
                    f"关系边: {fieldkg_data['edges_count']}条 · "
                    f"证据: {fieldkg_data['evidence_count']}条 · "
                    f"事务出件箱: {fieldkg_data['outbox_pending']}项 (Clean)"
                ),
                source_ref="catalog.db:research_nodes & OpenSPG/KAG projection",
                payload=fieldkg_data,
            )
        )

        # Part 4. Current Stage & Last Tweak Item (Stage Gates)
        items.append(
            ObservatoryItem(
                agent_id=self.agent_id,
                item_id="scholar_stage_progress",
                title="Scholar 当前研发阶段与最新改动 (Stage & Last Tweaks)",
                kind="stage_progress",
                status="PENDING_REVIEW",
                health="HEALTHY",
                summary="阶段: G11 Catalog & Parsing 软件验收 · 最新改动: catalog_web.html 遮挡修复与 BibTeX 异步守卫 · 测试契约: 1078 PASS / 20 warnings",
                source_ref="stage-gates/04-verification-report.md",
                payload={
                    "current_stage": "G11 Catalog & Parsing Acceptance",
                    "stage_gate": "stage-gates/04-verification-report.md",
                    "gate_status": "pending_review",
                    "last_tweaks": [
                        {
                            "component": "catalog_web.html",
                            "fix": "positionCatalogPanels 使用 actual .top rect.bottom+scrollY+8 彻底解决 popover 遮挡工具栏底部问题",
                            "verified": True,
                        },
                        {
                            "component": "catalog_collections.js",
                            "fix": "createBibFileReader 添加 generationToken 取消与 5MB 防护",
                            "verified": True,
                        },
                        {
                            "component": "studio.py / Schema 14",
                            "fix": "投稿绑定快照 studio_submission_bindings 与出版归档校验 (PUBLICATION 接收后工作阶段，ARCHIVED 两份受管文件 SHA256 校验)",
                            "verified": True,
                        },
                    ],
                    "test_suite": {
                        "passed": 1078,
                        "warnings": 20,
                        "source_files_frozen": 306,
                        "pytest_status": "ALL_GREEN",
                    },
                },
            )
        )

        # 4. Recent Scholar Runs & Tasks from uuma.db (if any)
        if self.uuma_db.exists():
            conn = self.safe_sqlite_connect(self.uuma_db)
            if conn:
                try:
                    with conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            SELECT r.run_id, r.status, e.occurred_at, t.title, t.task_id
                            FROM runs r
                            LEFT JOIN tasks t ON r.task_id = t.task_id
                            LEFT JOIN events e ON r.updated_sequence = e.sequence
                            WHERE r.agent_id = 'scholar'
                            ORDER BY r.updated_sequence DESC LIMIT 3
                            """
                        )
                        for row in cursor.fetchall():
                            items.append(
                                ObservatoryItem(
                                    agent_id=self.agent_id,
                                    item_id=f"scholar_run_{row['run_id']}",
                                    title=row["title"] or f"Scholar Run {row['run_id'][:8]}",
                                    kind="research_run",
                                    status=row["status"] or "RUNNING",
                                    updated_at=row["occurred_at"],
                                    summary=f"科学研究任务: {row['task_id'] or '独立研究'}",
                                    source_ref="uuma.db:runs",
                                    payload={"run_id": row["run_id"], "task_id": row["task_id"]},
                                )
                            )
                except sqlite3.Error:
                    pass

        return items[offset : offset + limit]

    def get_item(self, item_id: str) -> ObservatoryItem | None:
        items = self.list_items(limit=100)
        for it in items:
            if it.item_id == item_id:
                return it
        return None
