from __future__ import annotations

import json

import pytest

from uuma import mcp_worker


@pytest.fixture()
def setup_lab_env(tmp_path, monkeypatch):
    lab_db = tmp_path / "test_lab.db"
    monkeypatch.setenv("LAB_DATABASE_PATH", str(lab_db))
    monkeypatch.setenv("UUMA_AGENT_ID", "forge-lab-bot")
    monkeypatch.setattr(
        mcp_worker,
        "_wake_forge_journal_runner",
        lambda: {"status": "REQUESTED", "requested": True, "task_name": "fixture"},
    )
    mcp_worker._inventory.cache_clear()
    mcp_worker._procurement.cache_clear()
    mcp_worker._journal.cache_clear()
    mcp_worker._crawler_engine.cache_clear()
    return lab_db


def test_permission_gate(monkeypatch):
    monkeypatch.setenv("UUMA_AGENT_ID", "scholar")
    with pytest.raises(PermissionError, match="restricted to forge-lab-bot"):
        mcp_worker.inventory_status()
    with pytest.raises(PermissionError, match="restricted to forge-lab-bot"):
        mcp_worker.procurement_list_requirements()
    with pytest.raises(PermissionError, match="restricted to forge-lab-bot"):
        mcp_worker.procurement_check_crawler_status()
    with pytest.raises(PermissionError, match="restricted to forge-lab-bot"):
        mcp_worker.inventory_search_purchase_history("TPU")


def test_purchase_search_mcp_returns_staged_evidence(setup_lab_env):
    mcp_worker._inventory().import_purchase_history([{
        "source_key": "tpu-order",
        "source_workbook_hash": "workbook-hash",
        "source_sheet": "所有订单明细",
        "source_row": 740,
        "order_id": "2101620723153132851",
        "ordered_at": "2024-03-29 08:32:43",
        "status": "交易成功",
        "category": "3D打印 / 打印耗材",
        "product_name": "TPU printing filament",
        "product_url": "https://item.taobao.com/item.htm?id=41604517259",
        "variant": "TPU 白色200克1.75mm",
        "ordered_quantity": 1,
        "identity_key": "41604517259|TPU 白色200克1.75mm",
        "component_id": "cmp-tpu-white",
    }], commit=True)
    result = mcp_worker.inventory_search_purchase_history("TPU 200 1.75")
    assert result["count"] == result["total_count"] == 1
    assert result["match_mode"] == "exact"
    assert result["rows"][0]["product_url"] == (
        "https://item.taobao.com/item.htm?id=41604517259"
    )


def test_purchase_search_ranked_fallback(setup_lab_env):
    mcp_worker._inventory().import_purchase_history([
        {
            "source_key": "shield-18650",
            "source_workbook_hash": "w-hash",
            "source_sheet": "所有订单明细",
            "source_row": 820,
            "order_id": "ORD-18650",
            "ordered_at": "2023-09-10 13:59:28",
            "status": "交易成功",
            "category": "电子元器件",
            "product_name": "两路18650锂电池扩展板V8移动电源扩展板 5V3V",
            "product_url": "https://item.taobao.com/item.htm?id=589281902810",
            "variant": "两路",
            "ordered_quantity": 1,
            "identity_key": "589281902810|两路",
            "component_id": "cmp-18650",
        },
        {
            "source_key": "bms-32650",
            "source_workbook_hash": "w-hash",
            "source_sheet": "所有订单明细",
            "source_row": 587,
            "order_id": "ORD-32650",
            "ordered_at": "2024-10-30 15:19:48",
            "status": "交易成功",
            "category": "电子元器件",
            "product_name": "4串12.8V 32650磷酸铁锂电池保护板 带均衡 30A",
            "product_url": "https://item.taobao.com/item.htm?id=676235704594",
            "variant": "4串 磷酸铁锂电池保护板[带均衡]",
            "ordered_quantity": 2,
            "identity_key": "676235704594|4串",
            "component_id": "cmp-32650",
        },
    ], commit=True)

    # Natural Chinese phrase query that doesn't have an exact all-term match
    # triggers ranked fallback and surfaces both the 18650 shield and 32650 protection board
    res = mcp_worker.inventory_search_purchase_history("18650 电池保护板")
    assert res["total_count"] == 2
    assert res["match_mode"] == "partial"
    order_ids = [r["order_id"] for r in res["rows"]]
    assert "ORD-32650" in order_ids
    assert "ORD-18650" in order_ids


def test_commerce_search_order_lines_mcp(setup_lab_env):
    store = mcp_worker._commerce_store()
    store.bootstrap()
    with store.connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO commerce_order_lines
            (line_id, platform, account_id, order_id, product_id, sku_id,
             product_name, variant_name, unit_price, quantity, line_total,
             currency, category, ownership, review_status, created_at, updated_at,
             shop_name, item_url, order_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "line_test_18650",
                "taobao",
                "test@example.com",
                "ORD-COMM-18650",
                "p_18650",
                "sku_18650",
                "18650电池座 V3开发板兼容 树莓派过充保护 5V",
                "二路18650电池座（不带线）",
                11.6,
                2.0,
                23.2,
                "CNY",
                "electronics",
                "self",
                "unreviewed",
                "2026-09-28T10:00:00+00:00",
                "2026-09-28T10:00:00+00:00",
                "专业18650店",
                "https://item.taobao.com/item.htm?id=806773274407",
                "2026-09-05",
            ),
        )
        conn.commit()

    # Exact search
    res = mcp_worker.commerce_search_order_lines("18650 电池座")
    assert res["count"] == 1
    assert res["match_mode"] == "exact"
    assert res["rows"][0]["order_id"] == "ORD-COMM-18650"
    assert res["rows"][0]["platform"] == "taobao"

    # Search with natural phrase fallback
    res_fb = mcp_worker.commerce_search_order_lines("18650 电池保护板")
    assert res_fb["count"] >= 1
    assert res_fb["rows"][0]["order_id"] == "ORD-COMM-18650"


def test_build_management_tools(setup_lab_env):
    created = mcp_worker.lab_create_build(
        json.dumps({
            "design_revision_id": "REV-MOTOR-V1",
            "design_manifest_hash": "abc123hash",
            "build_id": "BUILD-001"
        })
    )
    assert created["build_id"] == "BUILD-001"

    listed = mcp_worker.lab_list_builds()
    assert listed["count"] == 1
    assert listed["builds"][0]["build_id"] == "BUILD-001"

    updated = mcp_worker.lab_update_build_status("BUILD-001", "IN_PROGRESS")
    assert updated["status"] == "IN_PROGRESS"


def test_commissioning_tools(setup_lab_env):
    mcp_worker.lab_create_build(json.dumps({"design_revision_id": "REV-1", "build_id": "B-01"}))
    rec = mcp_worker.lab_record_commissioning(
        json.dumps({
            "build_id": "B-01",
            "test_name": "Oscilloscope Step Response",
            "status": "PASS",
            "metrics": {"overshoot_pct": 4.2, "settling_ms": 12.5},
            "notes": "Within target specs"
        })
    )
    assert rec["status"] == "PASS"

    listed = mcp_worker.lab_list_commissioning(build_id="B-01")
    assert listed["count"] == 1
    assert listed["records"][0]["metrics"]["overshoot_pct"] == 4.2


def test_worklog_and_failure_tools(setup_lab_env):
    mcp_worker.lab_create_build(json.dumps({"design_revision_id": "REV-1", "build_id": "B-01"}))
    mcp_worker.inventory_receive(
        json.dumps({
            "component_id": "cmp-ic-555",
            "quantity": 10,
            "display_name": "NE555 Timer"
        })
    )

    # Worklog
    log = mcp_worker.lab_record_worklog(
        json.dumps({
            "project_name": "Timer Bringup",
            "action": "Checked pin 3 pulse output",
            "observation": "Duty cycle deviated by 15%",
            "build_id": "B-01",
            "hypothesis": "Capacitor tolerance +/- 20%",
            "confirmed_cause": "Electrolytic cap leakage",
            "result": "Swapped to ceramic; output stable",
            "parts": ["cmp-ic-555"]
        })
    )
    assert log["project_name"] == "Timer Bringup"

    logs = mcp_worker.lab_list_worklogs(project_name="Timer Bringup")
    assert logs["count"] == 1
    assert logs["worklogs"][0]["action"] == "Checked pin 3 pulse output"

    # Failure
    fail = mcp_worker.lab_record_failure(
        json.dumps({
            "symptom": "No pulse generated from output pin",
            "severity": "HIGH",
            "build_id": "B-01",
            "component_id": "cmp-ic-555",
            "confirmed_cause": "Pin 4 RESET left floating",
            "action_taken": "Tied pin 4 to VCC"
        })
    )
    assert fail["severity"] == "HIGH"

    fails = mcp_worker.lab_list_failures(severity="HIGH")
    assert fails["count"] == 1
    assert fails["failures"][0]["component_id"] == "cmp-ic-555"


def test_forge_journal_sync_tools(setup_lab_env):
    snapshot = mcp_worker.lab_journal_register_snapshot(
        json.dumps({
            "notion_page_id": "notion-log-1",
            "notion_url": "https://notion.so/notion-log-1",
            "title": "Power rail fault",
            "remote_content_hash": "hash-v1",
            "project_system": "Bench PSU",
            "entry_type": "Problem",
            "snapshot": {"raw_note": "Rail collapsed under load."},
        })
    )
    assert snapshot["sync_status"] == "SYNCED"

    queued = mcp_worker.lab_journal_queue_write(
        json.dumps({
            "operation": "PATCH_LOG",
            "journal_id": snapshot["journal_id"],
            "idempotency_key": "patch-notion-log-1-v1",
            "payload": {
                "change_summary": "Added separated observation and hypothesis.",
                "change_reason": "Keep the engineering trace explicit.",
            },
        })
    )
    assert queued["status"] == "QUEUED"
    assert queued["delivery_trigger"]["status"] == "REQUESTED"

    claimed = mcp_worker.lab_journal_claim_write("openclaw-sync")
    assert claimed["claimed"] is True
    finished = mcp_worker.lab_journal_finish_write(
        json.dumps({
            "sync_job_id": queued["sync_job_id"],
            "worker_id": "openclaw-sync",
            "succeeded": True,
            "remote_page_id": "notion-log-1",
            "remote_url": "https://notion.so/notion-log-1",
            "remote_content_hash": "hash-v2",
        })
    )
    assert finished["status"] == "SYNCED"
    status = mcp_worker.lab_journal_sync_status(notion_page_id="notion-log-1")
    assert status["counts"] == {"SYNCED": 1}


def test_chat_capture_fills_worklog_queues_notion_and_is_idempotent(setup_lab_env):
    capture = json.dumps({
        "title": "VCore 3 hotend temperature oscillation",
        "project_system": "VCore 3",
        "entry_type": "problem",
        "raw_note": "After the nozzle change, temperature oscillated by about 8 C.",
        "action": "Changed the nozzle and ran a heat test.",
        "observation": "Hotend temperature oscillated by about 8 C.",
        "hypothesis": "The heater cartridge may have shifted.",
    })

    first = mcp_worker.lab_journal_capture_chat(capture)
    second = mcp_worker.lab_journal_capture_chat(capture)

    assert first["worklog"]["worklog_id"] == second["worklog"]["worklog_id"]
    assert first["journal_job"]["sync_job_id"] == second["journal_job"]["sync_job_id"]
    assert first["journal_job"]["delivery_trigger"]["requested"] is True
    worklogs = mcp_worker.lab_list_worklogs(project_name="VCore 3")
    assert worklogs["count"] == 1
    assert worklogs["worklogs"][0]["source_ref"].startswith("hermes-chat://content/")
    status = mcp_worker.lab_journal_sync_status(sync_status="QUEUED")
    assert status["counts"] == {"QUEUED": 1}
    assert status["pages"][0]["entry_type"] == "Problem"


def test_chat_capture_rejects_incomplete_or_unknown_type(setup_lab_env):
    with pytest.raises(ValueError, match="requires: observation"):
        mcp_worker.lab_journal_capture_chat(json.dumps({
            "title": "Incomplete",
            "project_system": "Bench",
            "entry_type": "Problem",
            "raw_note": "Something happened.",
            "action": "Powered it on.",
        }))
    with pytest.raises(ValueError, match="Problem, Experiment, Repair, or Build"):
        mcp_worker.lab_journal_capture_chat(json.dumps({
            "title": "Meeting note",
            "project_system": "Bench",
            "entry_type": "Discussion",
            "raw_note": "Discussed the bench.",
            "action": "Talked.",
            "observation": "No physical work occurred.",
        }))


def test_windows_journal_wakeup_respects_paused_task(monkeypatch):
    completed = mcp_worker.subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="ERROR: The task is disabled."
    )
    monkeypatch.setattr(mcp_worker.os, "name", "nt")
    monkeypatch.setattr(mcp_worker.subprocess, "run", lambda *args, **kwargs: completed)

    result = mcp_worker._wake_forge_journal_runner()

    assert result == {
        "status": "PAUSED",
        "requested": False,
        "task_name": "UuMA Forge Journal Runner",
    }


def test_lessons_and_design_feedback_tools(setup_lab_env):
    # Propose Lesson
    lesson = mcp_worker.lab_propose_lesson(
        json.dumps({
            "statement": "Never leave active-low reset lines floating in harsh electrical environments",
            "scope": "All microcontroller and timer circuits",
            "target_system": "ESCHEMATIC",
            "severity": "BLOCK",
            "confidence": 0.98,
            "status": "CANDIDATE",
            "evidence_refs": ["worklog://timer/bringup-01"]
        })
    )
    assert lesson["status"] == "CANDIDATE"

    listed_lessons = mcp_worker.lab_list_lessons(status="CANDIDATE")
    assert listed_lessons["count"] == 1

    with pytest.raises(PermissionError, match="reviewer lifecycle decisions"):
        mcp_worker.lab_update_lesson_status(lesson["lesson_id"], "ACCEPTED")

    # Propose Design Feedback
    mcp_worker.inventory_receive(
        json.dumps({"component_id": "cmp-res-10k", "quantity": 10, "display_name": "10k Resistor"})
    )
    feedback = mcp_worker.eschematic_submit_design_feedback(
        json.dumps({
            "design_revision_id": "REV-TIMER-V1",
            "change_summary": "Add external 10k pull-up resistor to RESET pin",
            "rationale": "Prevents spontaneous reset caused by motor transients",
            "target_component_id": "cmp-res-10k",
            "evidence_refs": ["worklog://timer/bringup-01"]
        })
    )
    assert feedback["status"] == "PROPOSED"

    proposals = mcp_worker.eschematic_list_design_feedback(design_revision_id="REV-TIMER-V1")
    assert proposals["count"] == 1
    assert proposals["proposals"][0]["change_summary"] == "Add external 10k pull-up resistor to RESET pin"


def test_procurement_tools(setup_lab_env):
    # 1. Create requirement
    req = mcp_worker.procurement_create_requirement(
        json.dumps({
            "item_name": "IBT-2 Motor Driver",
            "target_quantity": 2.0,
            "component_id": "CMP-IBT2",
            "specs": "43A H-Bridge",
            "target_unit_price": 18.0,
        })
    )
    assert req["item_name"] == "IBT-2 Motor Driver"
    rid = req["requirement_id"]

    # 2. List requirements
    reqs = mcp_worker.procurement_list_requirements(status="OPEN")
    assert reqs["count"] == 1

    # 3. Create requirements from shortages
    shortage_res = mcp_worker.procurement_create_requirements_from_shortages(
        json.dumps([{"component_id": "CMP-RES-10K", "shortage": 100.0, "item_name": "0805 10K Resistor"}])
    )
    assert shortage_res["count"] == 1
    res_rid = shortage_res["requirements"][0]["requirement_id"]

    # 4. Save and expand term rules
    mcp_worker.procurement_save_term_rule(
        json.dumps({
            "target_name": "IBT-2 Motor Driver",
            "aliases": ["BTS7960", "43A 直流电机驱动"],
            "package_keywords": ["TO-263"],
            "raw_materials": [{"name": "BTS7960 裸片 + DIY PCB", "estimated_diy_cost": 8.0}],
        })
    )
    term_res = mcp_worker.procurement_expand_terms("IBT-2 Motor Driver")
    assert term_res["source"] == "local_rule"
    assert "BTS7960" in term_res["aliases"]

    # 5. Parse snippet
    snippet_res = mcp_worker.procurement_parse_offer_snippet(
        "【淘宝】https://item.taobao.com/item.htm?id=123 优信电子 IBT-2电机驱动 ￥18.00 运费: 6.00 满30包邮"
    )
    assert snippet_res["platform"] == "taobao"
    assert snippet_res["unit_price"] == 18.0
    assert snippet_res["free_shipping_threshold"] == 30.0

    # 6. Record offers
    mcp_worker.procurement_record_offers(
        json.dumps([
            {
                "requirement_id": rid,
                "platform": "taobao",
                "shop_name": "优信电子",
                "product_title": "IBT-2 43A 驱动板",
                "unit_price": 18.0,
                "shipping_fee": 6.0,
                "free_shipping_threshold": 30.0,
            },
            {
                "requirement_id": res_rid,
                "platform": "taobao",
                "shop_name": "优信电子",
                "product_title": "0805 10K 电阻 100只装",
                "unit_price": 5.0,
                "pack_quantity": 100.0,
                "shipping_fee": 6.0,
                "free_shipping_threshold": 30.0,
            },
        ])
    )

    # 7. List offers
    offers_listed = mcp_worker.procurement_list_offers(shop_name="优信电子")
    assert offers_listed["count"] == 2

    # 8. Evaluate sourcing
    eval_res = mcp_worker.procurement_evaluate_sourcing(json.dumps([rid, res_rid]))
    assert eval_res["strategies"]["minimal_shipments"]["status"] == "FEASIBLE"
    assert eval_res["strategies"]["minimal_shipments"]["total_landed_cost"] == 41.0
    assert eval_res["strategies"]["raw_material_diy"]["status"] == "AVAILABLE"

    # 9. Confirm order
    order_res = mcp_worker.procurement_confirm_order(
        json.dumps({
            "order_id": "ORD-TEST-001",
            "selected_offers": [
                {
                    "requirement_id": rid,
                    "component_id": "CMP-IBT2",
                    "ordered_quantity": 2.0,
                    "unit_price": 18.0,
                    "shop_name": "优信电子",
                    "platform": "taobao",
                }
            ],
            "notes": "MCP tool integration test",
        })
    )
    assert order_res["status"] == "ORDER_CONFIRMED"
    assert len(order_res["created_purchase_lots"]) == 1
    assert rid in order_res["updated_requirements"]

    # 10. Check crawler environment status
    crawler_status = mcp_worker.procurement_check_crawler_status()
    assert crawler_status["chrome_installed"] is True
    assert "profile_dir" in crawler_status

    # 11. Auto search and evaluate with mock
    mock_harvested = [
        {
            "platform": "taobao",
            "shop_name": "淘宝创客店",
            "product_title": "LM2596S 降压模块",
            "product_url": "https://item.taobao.com/item.htm?id=9988",
            "unit_price": 3.20,
            "shipping_fee": 0.0,
        }
    ]
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            mcp_worker._crawler_engine(),
            "crawl_platform",
            lambda platform, query, max_results=5: mock_harvested if platform == "taobao" else [],
        )
        auto_res = mcp_worker.procurement_auto_search_and_evaluate(
            query="LM2596S",
            target_quantity=5.0,
            platforms="taobao",
        )
        assert auto_res["query"] == "LM2596S"
        assert auto_res["harvested_offers_count"] == 1
        assert auto_res["evaluation"]["strategies"]["lowest_landed_cost"]["status"] == "FEASIBLE"
