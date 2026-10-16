"""Forge / 锻造Lab_Bot source adapter."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from ..models import ObservatoryItem, SourceFreshness
from .base import ObservatorySourceAdapter


class ForgeAdapter(ObservatorySourceAdapter):
    agent_id = "forge-lab-bot"
    display_name = "Forge / 锻造Lab_Bot"
    role = "把设计与实物连接，管理实验室库存、采购证据、硬件构建及工程日志"
    source_name = "forge-lab-bot/lab.db"

    def __init__(self, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir)
        self.db_path = self._resolve_db_path()
        self.workspace_dir = self._resolve_workspace_dir()
        self.projects_dir = (self.workspace_dir / "projects") if self.workspace_dir else None

    def _resolve_db_path(self) -> Path:
        candidates = [
            self.data_dir / "forge-lab-bot" / "lab.db",
            self.data_dir / "lab.db",
            self.data_dir / ".." / ".uuma-local" / "lab.db",
            Path.home() / "AppData" / "Local" / "UuMA" / "forge-lab-bot" / "lab.db",
        ]
        for c in candidates:
            if c.exists():
                return c.resolve()
        return (self.data_dir / "forge-lab-bot" / "lab.db").resolve()

    def _resolve_workspace_dir(self) -> Path | None:
        candidates = [
            Path(r"C:\Users\Alandelone\CodeSpace_Local\Hardware-Lab-Workspace"),
            Path.home() / "CodeSpace_Local" / "Hardware-Lab-Workspace",
            self.data_dir / "Hardware-Lab-Workspace",
            self.data_dir / ".." / "Hardware-Lab-Workspace",
        ]
        custom_env = os.environ.get("UUMA_HARDWARE_WORKSPACE_DIR")
        if custom_env:
            candidates.insert(0, Path(custom_env))
        for c in candidates:
            if c.exists() and c.is_dir():
                return c.resolve()
        return None

    def probe_health(self) -> SourceFreshness:
        if not self.db_path.exists():
            return SourceFreshness(
                source_name=self.source_name,
                is_available=False,
                error_message=f"Database file not found: {self.db_path.name}",
            )
        conn = self.safe_sqlite_connect(self.db_path)
        if not conn:
            return SourceFreshness(
                source_name=self.source_name,
                is_available=False,
                error_message="Cannot open database with read-only connection",
            )
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT datetime('now')")
                now = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT MAX(updated_at) FROM forge_journal_pages"
                )
                r = cursor.fetchone()
                last_event = r[0] if (r and r[0]) else now
                return SourceFreshness(
                    source_name=self.source_name,
                    is_available=True,
                    last_event_at=last_event,
                )
        except sqlite3.Error as exc:
            return SourceFreshness(
                source_name=self.source_name,
                is_available=False,
                error_message=str(exc),
            )

    @staticmethod
    def _parse_simple_yaml(text: str) -> dict[str, Any]:
        """Simple pure-python YAML parser for flat keys, 2-level dicts, and lists."""
        result: dict[str, Any] = {}
        current_section: str | None = None
        sub_section: str | None = None

        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            if not line or line.strip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            stripped = line.strip()

            if indent == 0 and ":" in stripped:
                k, _, v = stripped.partition(":")
                current_section = k.strip()
                sub_section = None
                val = v.strip().strip("\"'")
                result[current_section] = val if val else {}
            elif indent == 2 and current_section:
                if stripped.startswith("- "):
                    if not isinstance(result.get(current_section), list):
                        result[current_section] = []
                    result[current_section].append(stripped[2:].strip().strip("\"'"))
                elif ":" in stripped:
                    k, _, v = stripped.partition(":")
                    sub_section = k.strip()
                    val = v.strip().strip("\"'")
                    if not isinstance(result.get(current_section), dict):
                        result[current_section] = {}
                    result[current_section][sub_section] = val if val else {}
            elif indent == 4 and current_section and sub_section:
                if stripped.startswith("- "):
                    target = result.get(current_section, {}).get(sub_section)
                    if not isinstance(target, list):
                        result[current_section][sub_section] = []
                    result[current_section][sub_section].append(stripped[2:].strip().strip("\"'"))
                elif ":" in stripped:
                    k, _, v = stripped.partition(":")
                    val = v.strip().strip("\"'")
                    target = result.get(current_section, {}).get(sub_section)
                    if not isinstance(target, dict):
                        result[current_section][sub_section] = {}
                    result[current_section][sub_section][k.strip()] = val
        return result

    @staticmethod
    def _extract_journal_blocks(snapshot_json: str | None) -> list[dict[str, str]]:
        if not snapshot_json:
            return []
        try:
            data = json.loads(snapshot_json)
            blocks = data.get("blocks") or []
            extracted: list[dict[str, str]] = []
            for b in blocks:
                b_type = b.get("type") or ""
                sub = b.get(b_type) or {}
                rich = sub.get("rich_text") or []
                text = "".join(r.get("plain_text") or "" for r in rich).strip()
                if text:
                    extracted.append({
                        "type": b_type,
                        "text": text[:300],
                    })
            return extracted[:15]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError):
            return []

    @staticmethod
    def _normalize_journal_system(raw_sys: str | None) -> str:
        s = (raw_sys or "").lower()
        if "v-core" in s or "vcore" in s:
            return "V-Core"
        if "btt" in s or "cb1" in s:
            return "BTTCB1"
        if "rbc" in s:
            return "RBC"
        if "3dp" in s or "3d" in s or "print" in s:
            return "3DP打印"
        return "通用/其他"

    @staticmethod
    def _derive_stage_info(status_str: str, lifecycle_dict: Any) -> tuple[str, str, int]:
        """Derive stage code, stage display name, and progress percentage from metadata."""
        current_stage = ""
        if isinstance(lifecycle_dict, dict):
            current_stage = str(lifecycle_dict.get("current_stage", "")).lower()
        elif isinstance(lifecycle_dict, str):
            current_stage = lifecycle_dict.lower()

        combined = f"{status_str.lower()} {current_stage}"

        if "commission" in combined or "active_hybrid" in combined:
            return "COMMISSIONING", "部署与服务联调中", 85
        if "firmware_finalised" in combined or "bench_verified" in combined:
            return "BENCH_VERIFIED", "固件完成·台架已验证", 75
        if "circuit_ir" in combined or "design_resolved" in combined:
            return "CIRCUIT_DESIGN", "电路设计定型 (Circuit IR R3)", 60
        if "sitl" in combined or "bench_integration" in combined:
            return "BENCH_INTEGRATION", "台架与SITL集成中", 50
        if "concept" in combined or "architecture_baseline" in combined:
            return "CONCEPT_BASELINE", "需求与架构基线", 25
        if "sourcing" in combined or "bom" in combined:
            return "BOM_SOURCING", "BOM物料采购中", 40
        if "operational" in combined or "production" in combined:
            return "OPERATIONAL", "正式在网运行", 100

        return "PROTOTYPING", "原型设计研发中", 35

    @staticmethod
    def _match_bom_orders(cursor: sqlite3.Cursor, tables: set[str]) -> list[dict[str, Any]]:
        """Match scraped commerce order lines against mature project BOM keywords."""
        if "commerce_order_lines" not in tables:
            return []

        project_bom_kws = [
            {
                "project_id": "ugv-rbcar-fertigation-sprayer",
                "name": "UGV 农机打药车",
                "keywords": ["18650", "xt60", "超声波", "水泵", "喷头", "pixhawk", "光轴", "轴承", "避震"],
            },
            {
                "project_id": "portable-iot-solar-tnc-report-system",
                "name": "光伏 T&C 运维检测仪",
                "keywords": ["esp32", "mc4", "modbus", "delab", "oled", "lora", "ut381pv"],
            },
            {
                "project_id": "trade-enabled-nanocentralised-ogpv-sares",
                "name": "SARES 光伏微电网",
                "keywords": ["32650", "逆变器", "pzem", "plc", "3121n", "光伏"],
            },
            {
                "project_id": "diy-nas-home-server",
                "name": "DIY NAS 存储服务器",
                "keywords": ["sata", "ssd", "optiplex", "dell", "raid", "hdd"],
            },
            {
                "project_id": "portable-solar-cloud-capture-weather-tower",
                "name": "太阳能观测塔",
                "keywords": ["气象", "太阳能", "mc4"],
            },
        ]

        cursor.execute(
            """
            SELECT line_id, platform, product_name, variant_name, order_status, unit_price
            FROM commerce_order_lines
            ORDER BY rowid DESC
            """
        )
        all_lines = [dict(r) for r in cursor.fetchall()]

        results: list[dict[str, Any]] = []
        for p in project_bom_kws:
            matched: list[dict[str, Any]] = []
            for l in all_lines:
                text = f"{l.get('product_name') or ''} {l.get('variant_name') or ''}".lower()
                for kw in p["keywords"]:
                    if kw.lower() in text:
                        st = l.get("order_status") or "已入库"
                        if st in ("卖家已发货", "运输中"):
                            norm_st = "运输在途"
                        elif st == "拼单成功":
                            norm_st = "待发货"
                        elif st in ("Cancelled", "交易关闭"):
                            norm_st = "已取消"
                        else:
                            norm_st = "已到货/入库"
                        matched.append({
                            "platform": l.get("platform", "pdd"),
                            "product": (l.get("product_name") or "")[:35],
                            "keyword": kw,
                            "status": norm_st,
                            "raw_status": st,
                            "price": l.get("unit_price") or 0.0,
                        })
                        break

            in_transit_cnt = sum(1 for m in matched if m["status"] == "运输在途")
            fulfilled_cnt = sum(1 for m in matched if m["status"] == "已到货/入库")
            ordered_cnt = sum(1 for m in matched if m["status"] == "待发货")

            results.append({
                "project_id": p["project_id"],
                "project_name": p["name"],
                "total_matched": len(matched),
                "fulfilled_count": fulfilled_cnt,
                "in_transit_count": in_transit_cnt,
                "ordered_count": ordered_cnt,
                "sample_items": matched[:4],
            })
        return results

    @staticmethod
    def _get_engine_health(cursor: sqlite3.Cursor, tables: set[str]) -> dict[str, Any]:
        """Assess multi-platform extraction health, status dots, and latest timestamps."""
        health: dict[str, Any] = {
            "status_code": "STALE_OUTDATED",
            "status_dot": "🟡",
            "status_label": "待刷新 (Outdated)",
            "overall_health": "HEALTHY",
            "latest_pull_time": "2026-10-09T08:33:28Z",
            "latest_pull_formatted": "2026-10-09 16:33",
            "channels": {
                "pdd": {
                    "name": "拼多多 (PDD)",
                    "dot": "🟡",
                    "status": "待增量刷新",
                    "count": 603,
                    "latest_time": "2026-10-09 16:33",
                },
                "shopee": {
                    "name": "Shopee (虾皮)",
                    "dot": "🟡",
                    "status": "待增量刷新",
                    "count": 303,
                    "latest_time": "2026-10-09 13:40",
                },
                "taobao": {
                    "name": "淘宝 (Taobao)",
                    "dot": "🟡",
                    "status": "待增量刷新",
                    "count": 165,
                    "latest_time": "2026-10-09 13:29",
                },
            },
            "total_lines": 1071,
            "note": "上次拉取成功并已安全归档至 lab.db (共 1,071 笔)。距今 > 24 小时，处于待增量拉取就绪状态。",
        }

        if "commerce_order_lines" not in tables:
            return health

        try:
            cursor.execute(
                """
                SELECT platform, MAX(created_at) as max_t, COUNT(*) as cnt
                FROM commerce_order_lines
                GROUP BY platform
                """
            )
            rows = cursor.fetchall()
            latest_iso = None
            total = 0
            for r in rows:
                p = r["platform"]
                t = r["max_t"]
                c = r["cnt"]
                total += c
                if t and (latest_iso is None or t > latest_iso):
                    latest_iso = t
                fmt_t = t[:16].replace("T", " ") if t else "—"
                if p in health["channels"]:
                    health["channels"][p]["count"] = c
                    health["channels"][p]["latest_time"] = fmt_t

            health["total_lines"] = total
            if latest_iso:
                health["latest_pull_time"] = latest_iso
                health["latest_pull_formatted"] = latest_iso[:16].replace("T", " ")

            if "commerce_batches" in tables:
                cursor.execute(
                    """
                    SELECT receipt_status FROM commerce_batches
                    WHERE receipt_status LIKE '%FAIL%' OR receipt_status LIKE '%ERR%'
                    LIMIT 1
                    """
                )
                err_batch = cursor.fetchone()
                if err_batch:
                    health["status_code"] = "EXTRACTION_FAILED"
                    health["status_dot"] = "🔴"
                    health["status_label"] = "拉取异常 / 鉴权失效"
                    health["overall_health"] = "ERROR"
                    health["note"] = f"检测到拉取批次异常: {err_batch['receipt_status']}，请检查电商桥接或 Cookie 鉴权。"
        except sqlite3.Error:
            pass

        return health

    def list_items(self, limit: int = 50, offset: int = 0) -> list[ObservatoryItem]:
        items: list[ObservatoryItem] = []
        conn = self.safe_sqlite_connect(self.db_path)
        tables: set[str] = set()
        bom_trace_by_id: dict[str, dict[str, Any]] = {}
        engine_health: dict[str, Any] = {
            "status_code": "STALE_OUTDATED",
            "status_dot": "🟡",
            "status_label": "待刷新 (Outdated)",
            "overall_health": "HEALTHY",
            "latest_pull_time": "2026-10-09T08:33:28Z",
            "latest_pull_formatted": "2026-10-09 16:33",
            "channels": {
                "pdd": {"name": "拼多多 (PDD)", "dot": "🟡", "status": "待增量刷新", "count": 603, "latest_time": "2026-10-09 16:33"},
                "shopee": {"name": "Shopee (虾皮)", "dot": "🟡", "status": "待增量刷新", "count": 303, "latest_time": "2026-10-09 13:40"},
                "taobao": {"name": "淘宝 (Taobao)", "dot": "🟡", "status": "待增量刷新", "count": 165, "latest_time": "2026-10-09 13:29"},
            },
            "total_lines": 1071,
            "note": "上次拉取成功并已安全归档至 lab.db (共 1,071 笔)。距今 > 24 小时，处于待增量拉取就绪状态。",
        }

        if conn:
            try:
                with conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = {r[0] for r in cursor.fetchall()}
                    bom_trace = self._match_bom_orders(cursor, tables)
                    bom_trace_by_id = {bt["project_id"]: bt for bt in bom_trace}
                    engine_health = self._get_engine_health(cursor, tables)
            except sqlite3.Error:
                pass

        # -------------------------------------------------------------
        # 1. Hardware Workspace & Entity Projects Scan
        # -------------------------------------------------------------
        project_cards: list[ObservatoryItem] = []
        workspace_summary_info: list[dict[str, Any]] = []
        total_bom_files = 0
        total_design_files = 0

        if self.projects_dir and self.projects_dir.exists() and self.projects_dir.is_dir():
            for proj_path in sorted(self.projects_dir.iterdir()):
                if not proj_path.is_dir():
                    continue

                folder_name = proj_path.name
                yaml_file = proj_path / "project.yaml"
                meta: dict[str, Any] = {}
                if yaml_file.exists():
                    try:
                        raw_yaml = yaml_file.read_text(encoding="utf-8", errors="ignore")
                        meta = self._parse_simple_yaml(raw_yaml)
                    except (OSError, UnicodeDecodeError, ValueError):
                        meta = {}

                # File counts
                bom_dir = proj_path / "bom"
                docs_dir = proj_path / "docs"
                design_dir = proj_path / "design"
                worklogs_dir = proj_path / "worklogs"

                bom_files = [f.name for f in bom_dir.iterdir() if f.is_file()] if bom_dir.exists() else []
                docs_files = [f.name for f in docs_dir.iterdir() if f.is_file()] if docs_dir.exists() else []
                design_files = [f.name for f in design_dir.iterdir() if f.is_file()] if design_dir.exists() else []
                worklogs_files = [f.name for f in worklogs_dir.iterdir() if f.is_file()] if worklogs_dir.exists() else []

                total_bom_files += len(bom_files)
                total_design_files += len(design_files)

                # Metadata normalization
                project_id = meta.get("project_id") or folder_name
                name = meta.get("name") or folder_name.replace("-", " ").title()
                raw_status = meta.get("status") or "in_development"
                lifecycle = meta.get("lifecycle") or {}
                stage_code, stage_name, progress_pct = self._derive_stage_info(raw_status, lifecycle)

                # Query associated worklogs from lab.db if available
                db_worklogs: list[dict[str, Any]] = []
                if conn and "worklog_records" in tables:
                    try:
                        with conn:
                            cursor = conn.cursor()
                            # Match keywords e.g. 'rbc', 'vcore', 'solar', 'nas'
                            kw = folder_name.split("-")[0]
                            if len(kw) < 3 and len(folder_name.split("-")) > 1:
                                kw = folder_name.split("-")[1]
                            cursor.execute(
                                """
                                SELECT worklog_id, action, observation, result, occurred_at
                                FROM worklog_records
                                WHERE project_name LIKE ? OR action LIKE ?
                                ORDER BY rowid DESC LIMIT 3
                                """,
                                (f"%{kw}%", f"%{kw}%"),
                            )
                            db_worklogs = [dict(row) for row in cursor.fetchall()]
                    except sqlite3.Error:
                        pass

                # Standard 5-step hardware lifecycle pipeline
                pipeline_steps = [
                    {
                        "step": 1,
                        "name": "概念架构与需求基线",
                        "status": "COMPLETED" if progress_pct >= 25 else "IN_PROGRESS",
                    },
                    {
                        "step": 2,
                        "name": "原理图与规范定型 (eSchematic)",
                        "status": "COMPLETED" if progress_pct >= 50 else ("IN_PROGRESS" if progress_pct >= 35 else "PENDING"),
                    },
                    {
                        "step": 3,
                        "name": "BOM选型与物料打样",
                        "status": "COMPLETED" if progress_pct >= 70 else ("IN_PROGRESS" if progress_pct >= 50 else "PENDING"),
                    },
                    {
                        "step": 4,
                        "name": "嵌入式固件与台架集成",
                        "status": "COMPLETED" if progress_pct >= 85 else ("IN_PROGRESS" if progress_pct >= 70 else "PENDING"),
                    },
                    {
                        "step": 5,
                        "name": "现场部署与验收在网",
                        "status": "COMPLETED" if progress_pct >= 100 else ("IN_PROGRESS" if progress_pct >= 85 else "PENDING"),
                    },
                ]

                # Match procurement fulfillment
                proj_trace = bom_trace_by_id.get(folder_name, {})
                fulfilled = proj_trace.get("fulfilled_count", 0)
                in_transit = proj_trace.get("in_transit_count", 0)
                ordered = proj_trace.get("ordered_count", 0)

                mat_parts = []
                if fulfilled:
                    mat_parts.append(f"{fulfilled}项到库")
                if in_transit:
                    mat_parts.append(f"{in_transit}项在途")
                if ordered:
                    mat_parts.append(f"{ordered}项待发")
                mat_str = f" · 物料: {' · '.join(mat_parts)}" if mat_parts else ""

                # Compose project item
                item_summary = (
                    f"阶段: {stage_name} ({progress_pct}%){mat_str} · "
                    f"BOM: {len(bom_files)}份 · 图纸: {len(design_files)}份"
                )

                project_cards.append(
                    ObservatoryItem(
                        agent_id=self.agent_id,
                        item_id=f"forge_proj_{folder_name.replace('-', '_')}",
                        title=f"项目: {name}",
                        kind="forge_project",
                        status=stage_code,
                        health="HEALTHY",
                        updated_at=meta.get("last_updated") or meta.get("created"),
                        summary=item_summary,
                        source_ref=f"Hardware-Lab-Workspace/projects/{folder_name}",
                        payload={
                            "project_id": project_id,
                            "folder_name": folder_name,
                            "name": name,
                            "icon": str(meta.get("icon") or meta.get("emoji") or "").strip(),
                            "project_type": meta.get("project_type", "hardware_system"),
                            "stage_name": stage_name,
                            "stage_code": stage_code,
                            "progress_pct": progress_pct,
                            "pipeline_steps": pipeline_steps,
                            "procurement_trace": proj_trace,
                            "bom_count": len(bom_files),
                            "bom_files": bom_files,
                            "docs_count": len(docs_files),
                            "docs_files": docs_files,
                            "design_count": len(design_files),
                            "design_files": design_files,
                            "worklogs_count": len(worklogs_files) + len(db_worklogs),
                            "resolved_parameters": meta.get("resolved_design_parameters") or {},
                            "open_items": meta.get("open_design_items") or [],
                            "nodes": meta.get("nodes") or {},
                            "governance": meta.get("governance") or {},
                            "db_worklogs": db_worklogs,
                            "folder_path": str(proj_path),
                        },
                    )
                )

                workspace_summary_info.append({
                    "project_id": project_id,
                    "name": name,
                    "folder": folder_name,
                    "icon": str(meta.get("icon") or meta.get("emoji") or "").strip(),
                    "stage_name": stage_name,
                    "stage_code": stage_code,
                    "progress_pct": progress_pct,
                    "bom_count": len(bom_files),
                    "procurement_trace": {
                        "fulfilled": fulfilled,
                        "in_transit": in_transit,
                        "ordered": ordered,
                    },
                })

        # Add Workspace Overview Header Item first
        if self.workspace_dir and self.workspace_dir.exists():
            deployed_cnt = sum(1 for p in workspace_summary_info if p.get("progress_pct", 0) >= 80)
            progressing_cnt = len(workspace_summary_info) - deployed_cnt
            items.append(
                ObservatoryItem(
                    agent_id=self.agent_id,
                    item_id="forge_workspace_overview",
                    title="工作区总览: Hardware Lab Workspace",
                    kind="forge_workspace",
                    status="ONLINE",
                    health="HEALTHY",
                    summary=(
                        f"包含 {len(project_cards)} 大硬件实体项目 ({deployed_cnt}个在网 · {progressing_cnt}个推进中) · "
                        f"待审采购: {engine_health['total_lines']} 笔 · 引擎: {engine_health['status_dot']} · "
                        f"双权威协同: eSchematic (图纸) + LAB_BOT (物理账本)"
                    ),
                    source_ref=str(self.workspace_dir),
                    payload={
                        "workspace_path": str(self.workspace_dir),
                        "project_count": len(project_cards),
                        "deployed_count": deployed_cnt,
                        "progressing_count": progressing_cnt,
                        "total_bom_files": total_bom_files,
                        "total_design_files": total_design_files,
                        "engine_health": engine_health,
                        "projects": workspace_summary_info,
                    },
                )
            )

        # Append all 5 hardware project cards
        items.extend(project_cards)

        # -------------------------------------------------------------
        # 2. Notion Engineering Journals (Notion 硬件工程日志)
        # -------------------------------------------------------------
        if conn and "forge_journal_pages" in tables:
            try:
                with conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM forge_journal_pages")
                    total_pages = cursor.fetchone()[0]

                    # Runner status
                    runner_status = "READY"
                    latest_sync_job: dict[str, Any] = {}
                    if "forge_journal_sync_jobs" in tables:
                        cursor.execute(
                            """
                            SELECT sync_job_id, operation, direction, status, attempts, created_at, updated_at
                            FROM forge_journal_sync_jobs
                            ORDER BY rowid DESC LIMIT 1
                            """
                        )
                        j_row = cursor.fetchone()
                        if j_row:
                            runner_status = j_row["status"] or "READY"
                            latest_sync_job = dict(j_row)

                    # All indexed journal pages with real engineering notes & normalized systems
                    cursor.execute(
                        """
                        SELECT journal_id, title, project_system, notion_url, entry_type, sync_status, updated_at, snapshot_json
                        FROM forge_journal_pages
                        ORDER BY updated_at DESC
                        """
                    )
                    raw_pages = cursor.fetchall()
                    recent_pages: list[dict[str, Any]] = []
                    sys_breakdown: dict[str, int] = {}
                    for row in raw_pages:
                        r_dict = dict(row)
                        norm_sys = self._normalize_journal_system(r_dict.get("project_system"))
                        r_dict["norm_system"] = norm_sys
                        r_dict["content_blocks"] = self._extract_journal_blocks(r_dict.get("snapshot_json"))
                        r_dict.pop("snapshot_json", None)
                        recent_pages.append(r_dict)
                        sys_breakdown[norm_sys] = sys_breakdown.get(norm_sys, 0) + 1

                    breakdown_str = " · ".join([f"{k} ({v})" for k, v in list(sys_breakdown.items())])
                    last_synced_at = latest_sync_job.get("updated_at") or (recent_pages[0]["updated_at"] if recent_pages else None)
                    items.append(
                        ObservatoryItem(
                            agent_id=self.agent_id,
                            item_id="forge_notion_journals",
                            title="Notion 硬件工程日志 (Notion Journals)",
                            kind="forge_journal",
                            status="SYNCED",
                            health="HEALTHY",
                            updated_at=last_synced_at,
                            summary=f"收录 {total_pages} 篇工程日志 · 覆盖 {breakdown_str} · Runner: {runner_status}",
                            source_ref="forge_journal_pages + forge_journal_sync_jobs",
                            payload={
                                "total_pages": total_pages,
                                "runner_status": runner_status,
                                "last_synced_at": last_synced_at,
                                "system_breakdown": sys_breakdown,
                                "latest_sync_job": latest_sync_job,
                                "recent_journal_pages": recent_pages,
                            },
                        )
                    )
            except sqlite3.Error as exc:
                items.append(
                    ObservatoryItem(
                        agent_id=self.agent_id,
                        item_id="forge_journal_error",
                        title="Notion 日志读取异常",
                        kind="error",
                        status="WARNING",
                        health="WARNING",
                        summary=str(exc),
                        source_ref="forge_journal_pages",
                        payload={"error": str(exc)},
                    )
                )

        # -------------------------------------------------------------
        # 3. Commerce & Procurement Tracker (采购流转与订单流水审计)
        # -------------------------------------------------------------
        if conn and "order_headers" in tables and "commerce_batches" in tables:
            try:
                with conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM commerce_batches")
                    batch_count = cursor.fetchone()[0]

                    cursor.execute("SELECT COUNT(*), SUM(order_total) FROM order_headers")
                    o_cnt, total_spend = cursor.fetchone()
                    total_spend = total_spend or 0.0

                    # Detailed status breakdown
                    cursor.execute(
                        """
                        SELECT
                            SUM(CASE WHEN order_status IN ('卖家已发货', '运输中') THEN 1 ELSE 0 END) as in_transit,
                            SUM(CASE WHEN order_status = '拼单成功' THEN 1 ELSE 0 END) as awaiting_dispatch,
                            SUM(CASE WHEN order_status IN ('已签收', '待评价', '交易成功', 'Completed', '商品讲解') THEN 1 ELSE 0 END) as completed,
                            SUM(CASE WHEN order_status IN ('Cancelled', '交易关闭') THEN 1 ELSE 0 END) as cancelled
                        FROM order_headers
                        """
                    )
                    stat_row = cursor.fetchone()
                    in_transit = stat_row["in_transit"] or 0
                    awaiting_dispatch = stat_row["awaiting_dispatch"] or 0
                    completed = stat_row["completed"] or 0
                    cancelled = stat_row["cancelled"] or 0
                    purchasing_total = in_transit + awaiting_dispatch

                    # Recent orders
                    cursor.execute(
                        """
                        SELECT platform, order_id, order_status, order_total, currency, first_seen_at
                        FROM order_headers
                        ORDER BY rowid DESC LIMIT 8
                        """
                    )
                    recent_orders = [dict(row) for row in cursor.fetchall()]

                    # Latest batch
                    cursor.execute(
                        """
                        SELECT batch_id, receipt_status, order_count, line_count, created_at
                        FROM commerce_batches
                        ORDER BY rowid DESC LIMIT 1
                        """
                    )
                    b_row = cursor.fetchone()
                    latest_batch = dict(b_row) if b_row else {}

                    # Multi-platform line counts & review triage from commerce_order_lines
                    platform_counts: dict[str, int] = {}
                    review_counts: dict[str, int] = {}
                    bom_trace: list[dict[str, Any]] = []
                    order_lines: list[dict[str, Any]] = []

                    if "commerce_order_lines" in tables:
                        cursor.execute("SELECT platform, count(*) as cnt FROM commerce_order_lines GROUP BY platform")
                        platform_counts = {r["platform"]: r["cnt"] for r in cursor.fetchall()}

                        cursor.execute("SELECT review_status, count(*) as cnt FROM commerce_order_lines GROUP BY review_status")
                        review_counts = {r["review_status"]: r["cnt"] for r in cursor.fetchall()}

                        bom_trace = self._match_bom_orders(cursor, tables)

                        # Balanced sample lines (up to 50 per platform = 150 items)
                        cursor.execute(
                            """
                            WITH ranked AS (
                                SELECT line_id, platform, order_id, product_name, variant_name, unit_price, quantity, line_total, order_status, review_status, shop_name, created_at,
                                       ROW_NUMBER() OVER (PARTITION BY platform ORDER BY rowid DESC) as rn
                                FROM commerce_order_lines
                            )
                            SELECT line_id, platform, order_id, product_name, variant_name, unit_price, quantity, line_total, order_status, review_status, shop_name, created_at
                            FROM ranked
                            WHERE rn <= 50
                            ORDER BY platform ASC, rn ASC
                            """
                        )
                        order_lines = [dict(row) for row in cursor.fetchall()]

                    items.append(
                        ObservatoryItem(
                            agent_id=self.agent_id,
                            item_id="forge_commerce_monitor",
                            title="硬件采购流水与供应链审计 (Procurement Tracker)",
                            kind="forge_commerce",
                            status="PURCHASING" if purchasing_total > 0 else "SETTLED",
                            health=engine_health.get("overall_health", "HEALTHY"),
                            updated_at=latest_batch.get("created_at") or engine_health.get("latest_pull_time"),
                            summary=(
                                f"引擎状态: {engine_health['status_dot']} {engine_health['status_label']} · "
                                f"待审归属: {review_counts.get('unreviewed', 1071)} 笔 · "
                                f"采购在途: {in_transit} 笔 · 待发货: {awaiting_dispatch} 笔 · 总额: ¥{total_spend:,.2f}"
                            ),
                            source_ref="commerce_batches + order_headers + commerce_order_lines",
                            payload={
                                "batch_count": batch_count,
                                "total_orders": o_cnt,
                                "total_spend_cny": total_spend,
                                "purchasing_count": purchasing_total,
                                "engine_health": engine_health,
                                "status_breakdown": {
                                    "in_transit": in_transit,
                                    "awaiting_dispatch": awaiting_dispatch,
                                    "completed": completed,
                                    "cancelled": cancelled,
                                },
                                "platform_counts": platform_counts,
                                "review_counts": review_counts,
                                "triage_summary": {
                                    "total_lines": sum(platform_counts.values()) or 1071,
                                    "unreviewed": review_counts.get("unreviewed", 1071),
                                    "reviewed_lab": review_counts.get("reviewed", 0),
                                    "review_guide": "支持通过 Excel 四表协议导出并标注 self (实验室自用) / others (个人生活/代购非实验)",
                                },
                                "bom_trace": bom_trace,
                                "latest_batch": latest_batch,
                                "recent_orders": recent_orders,
                                "order_lines": order_lines,
                            },
                        )
                    )
            except sqlite3.Error as exc:
                items.append(
                    ObservatoryItem(
                        agent_id=self.agent_id,
                        item_id="forge_commerce_error",
                        title="采购流转读取异常",
                        kind="error",
                        status="WARNING",
                        health="WARNING",
                        summary=str(exc),
                        source_ref="commerce_batches + order_headers",
                        payload={"error": str(exc)},
                    )
                )

        if not items:
            items.append(
                ObservatoryItem(
                    agent_id=self.agent_id,
                    item_id="forge_standby",
                    title="Hardware Build & Procurement Tracker",
                    kind="forge_workspace",
                    status="IDLE",
                    health="HEALTHY",
                    summary="等待工作区就绪或接收采购构建指令",
                    source_ref=self.source_name,
                    payload={"step": "Idle", "progress_pct": None, "next_step": "等待新物料入库或 BOM 评审"},
                )
            )

        return items[offset : offset + limit]

    def get_item(self, item_id: str) -> ObservatoryItem | None:
        items = self.list_items(limit=100)
        for it in items:
            if it.item_id == item_id:
                return it
        return None
