"""Manage Commerce Review (Step 2: 用途归属与分类核对门控).

Supports:
  1. status: Show current review and triage statistics in lab.db
  2. export: Export official 4-sheet Excel review workbook with pre-populated AI suggestions
  3. auto-triage: Apply high-confidence AI classification directly to database
  4. commit: Validate and commit user-edited Excel review workbook back to lab.db
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from uuma.commerce_review import (
    commit_review,
    generate_review_workbook,
    preview_review_workbook,
)
from uuma.commerce_store import ALLOWED_CATEGORIES, ALLOWED_OWNERSHIPS, CommerceStore


def classify_text(pname: str, vname: str, sname: str) -> tuple[str, str, float]:
    """Strict hardware lab classifier according to user governance review.
    
    All items non-strictly hardware engineering (software subscriptions, stationery,
    household, office, personal goods) are strictly classified as 'others'.
    
    Returns:
        (ownership, category, confidence)
    """
    text = f"{pname} {vname} {sname}".lower()

    # Clear non-lab / household / office / stationery / software indicators
    exclude_keys = [
        "gemini", "锅", "壶", "苏打", "毛巾", "衣", "鞋", "裤", "纸巾", "洗洁精",
        "零食", "茶", "洗发", "沐浴", "拼豆", "按扣", "钥匙扣", "饰品", "耳环",
        "项链", "戒指", "发夹", "玩偶", "公仔", "收纳", "米", "油", "食品",
        "坚果", "糖", "糕点", "袜子", "雨伞", "纸箱", "保鲜膜", "垃圾袋",
        "支架", "手机", "玄关", "地垫", "地毯", "纱窗", "遮阳帘", "车窗",
        "素材", "婚礼", "psd", "筷", "勺", "餐具", "不织布", "煮蛋器",
        "钢化膜", "手机膜", "肥皂", "香皂", "毛笔", "墨水", "剃须刀", "桌垫",
        "硫酸纸", "信封", "手账", "被套", "床单", "床笠", "除雨", "镀晶",
        "粘虫", "转椅", "脚轮", "滑轮", "摘菜", "pen", "coins", "filter cartridge",
        "nesca", "tv box", "足贴", "盲盒", "泡泡玛特", "popmart", "烧烤",
        "裙带菜", "梳子", "吹风机", "菜板", "腰靠", "折叠门", "吸尘", "吸尘器",
        "吸尘机", "切纸", "碎纸", "磁贴", "隔断", "隔板", "鼠标", "清凉油",
        "小学生", "儿童", "自律神器", "时间管理", "学生学习", "display fan", "gift",
        "挂钩", "粘钩", "置物架", "菠萝", "键盘", "牙刷"
    ]
    if any(k in text for k in exclude_keys):
        return "others", "other", 1.0

    # Strict Hardware Lab: Electronics
    elec_keys = [
        "mcu", "esp32", "esp8266", "stm32", "芯片", "元件", "电阻", "电容",
        "传感器", "开发板", "oled", "模块", "串口", "单片机", "电路", "主板",
        "电源板", "电池", "32650", "18650", "锂电", "太阳能", "二极管", "三极管",
        "继电器", "变压器", "接插件", "排针", "航模", "无人机", "电机", "舵机",
        "电调", "gps", "tnc", "lora", "wi-fi", "wifi", "蓝牙", "网卡", "ssd",
        "内存", "cpu", "变频器", "ttl", "ch340", "cp2102", "sht30",
        "opa333", "tpl5010", "端子", "接线端子", "冷压", "香蕉插头", "香蕉插座",
        "测试头", "保险丝", "熔断器", "电表", "电度表", "电能表", "互感器",
        "电流互感器", "工业模组", "摄像头", "天线", "钻石天线", "f23h", "高增益",
        "基地台", "ptc加热", "ptc发热", "dji rsc2", "大疆如影", "网桥", "光伏"
    ]
    if any(k in text for k in elec_keys):
        return "self", "electronics", 1.0

    # Strict Hardware Lab: Tools
    tool_keys = [
        "热风枪", "烙铁", "万用表", "示波器", "分析仪", "螺丝刀",
        "镊子", "拆焊台", "雕刻机", "3d打印机", "测电笔", "卡尺",
        "电烙铁", "剥线钳", "压线钳", "手电钻", "测风仪", "风速仪",
        "风速计", "网络测线仪", "测线仪", "防毒面具", "放电负载"
    ]
    if any(k in text for k in tool_keys):
        return "self", "tool", 1.0

    # Strict Hardware Lab: Consumables & Structure Materials
    consumable_keys = [
        "焊锡", "松香", "助焊剂", "导热硅脂", "螺丝", "螺母", "扎带", "铜柱",
        "热缩管", "绝缘胶布", "生料带", "钢条", "不锈钢条", "铝合金", "亚克力",
        "pla", "petg", "abs", "3d打印耗材", "铜管", "硅胶线", "排线", "跳线",
        "十字扣件", "脚手架卡扣", "脚手架扣件", "短轴", "车轴", "传动轴",
        "齿轮轴", "压簧", "压缩簧", "耐特菲姆", "滴箭", "滴灌", "叠片过滤器",
        "葛兰头", "防水接头", "轴承钢珠", "不锈钢管", "704硅橡胶", "705密封胶"
    ]
    if any(k in text for k in consumable_keys):
        return "self", "consumable", 1.0

    return "others", "other", 1.0


def cmd_status(store: CommerceStore) -> None:
    with store.connect() as conn:
        total = conn.execute("SELECT count(*) FROM commerce_order_lines").fetchone()[0]
        unreviewed = conn.execute("SELECT count(*) FROM commerce_order_lines WHERE review_status = 'unreviewed'").fetchone()[0]
        reviewed_self = conn.execute("SELECT count(*) FROM commerce_order_lines WHERE review_status = 'reviewed' AND ownership = 'self'").fetchone()[0]
        reviewed_others = conn.execute("SELECT count(*) FROM commerce_order_lines WHERE review_status = 'reviewed' AND ownership = 'others'").fetchone()[0]

        cat_rows = conn.execute("SELECT category, count(*) FROM commerce_order_lines GROUP BY category").fetchall()
        platform_rows = conn.execute("SELECT platform, count(*) FROM commerce_order_lines GROUP BY platform").fetchall()

    print("==================================================")
    print(" 🛠️  Forge Lab Commerce Review (Step 2 门控状态)")
    print("==================================================")
    print(f"总物料行数 (Total Lines): {total}")
    print(f"待分类评审 (Unreviewed):  {unreviewed}  {'⚠️ 需要处理' if unreviewed > 0 else '✅ 已全部归属'}")
    print(f"已核定自用 (Self / Lab):  {reviewed_self}")
    print(f"已排除非实验 (Others):    {reviewed_others}")
    print("\n[平台分布 (Platforms)]")
    for r in platform_rows:
        print(f"  • {r[0]:10s}: {r[1]:4d} 行")
    print("\n[分类分布 (Categories)]")
    for r in cat_rows:
        print(f"  • {r[0]:12s}: {r[1]:4d} 行")
    print("==================================================")


def cmd_export(store: CommerceStore, output_path: Path | str | None = None) -> None:
    lines = store.list_order_lines(limit=10000)
    if not lines:
        print("未找到订单明细行。")
        return

    # Pre-populate intelligent AI suggestions
    for l in lines:
        pname = l.get("product_name", "")
        vname = l.get("variant_name", "")
        sname = l.get("shop_name", "")
        owner_sug, cat_sug, _ = classify_text(pname, vname, sname)
        l["ai_ownership_suggestion"] = owner_sug
        l["ai_category_suggestion"] = cat_sug
        # If line has not been reviewed yet, provide initial suggestion into category/ownership column
        if not l.get("ownership"):
            l["ownership"] = owner_sug
            l["category"] = cat_sug

    wb_bytes = generate_review_workbook(lines, task_scope="FORGE_LAB_FULL")

    target_path = Path(output_path) if output_path else Path.home() / "Downloads" / "commerce_review_workbook.xlsx"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(wb_bytes)

    print(f"✅ 成功导出 4 表审核工作簿！")
    print(f"📁 路径: {target_path}")
    print(f"📊 包含 {len(lines)} 行物料，已预填 AI 归属与分类建议。")
    print("\n💡 操作指南:")
    print("  1. 在 Excel 中打开该文件，切换到【订单待核对】Sheet。")
    print("  2. 核查 ownership 列（仅限填写 self 或 others，禁止按数量拆分）。")
    print("  3. 核查 category 列（electronics / tool / consumable / other）。")
    print("  4. 保存后运行: python scripts/manage-commerce-review.py commit <path> 完成写入！")


def cmd_auto_triage(store: CommerceStore, apply: bool = False, min_confidence: float = 0.85) -> None:
    lines = store.list_order_lines(limit=10000)
    unreviewed = [l for l in lines if l.get("review_status") == "unreviewed"]

    if not unreviewed:
        print("✅ 当前所有物料已完成分类评审，无需自动分诊。")
        return

    high_conf_updates = []
    skipped_count = 0

    for l in unreviewed:
        pname = l.get("product_name", "")
        vname = l.get("variant_name", "")
        sname = l.get("shop_name", "")
        owner, cat, conf = classify_text(pname, vname, sname)

        if conf >= min_confidence:
            high_conf_updates.append({
                "line_id": l["line_id"],
                "product_name": pname,
                "old_ownership": l.get("ownership"),
                "new_ownership": owner,
                "old_category": l.get("category"),
                "new_category": cat,
                "confidence": conf,
            })
        else:
            skipped_count += 1

    print(f"📊 自动分诊扫描完成:")
    print(f"  • 待评审总数: {len(unreviewed)} 行")
    print(f"  • 高置信度匹配: {len(high_conf_updates)} 行 (>= {min_confidence * 100:.0f}%)")
    print(f"  • 模糊保留待定: {skipped_count} 行")

    self_cnt = sum(1 for u in high_conf_updates if u["new_ownership"] == "self")
    others_cnt = sum(1 for u in high_conf_updates if u["new_ownership"] == "others")
    print(f"    - 判定实验室自用 (self):   {self_cnt} 行")
    print(f"    - 判定个人/生活 (others): {others_cnt} 行")

    if not apply:
        print("\n⚠️ 当前为预览模式 (Dry Run)。若确认写入数据库，请附加 --apply 参数:")
        print("   python scripts/manage-commerce-review.py auto-triage --apply")
        return

    # Apply updates transactionally
    with store.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for u in high_conf_updates:
            conn.execute(
                """
                UPDATE commerce_order_lines
                SET ownership = ?, category = ?, review_status = 'reviewed',
                    ai_ownership_suggestion = ?, ai_category_suggestion = ?,
                    review_version = review_version + 1, updated_at = datetime('now')
                WHERE line_id = ?
                """,
                (u["new_ownership"], u["new_category"], u["new_ownership"], u["new_category"], u["line_id"])
            )

    print(f"\n🎉 已成功写入 {len(high_conf_updates)} 行高置信度归属评审到 lab.db！")
    cmd_status(store)


def cmd_commit(store: CommerceStore, excel_path: Path | str) -> None:
    path = Path(excel_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Workbook not found: {path}")

    print(f"正在校验并预检: {path} ...")
    preview = preview_review_workbook(path, store)

    conflicts = preview.get("conflicts", [])
    updates = preview.get("updates", [])

    if conflicts:
        print(f"❌ 发现 {len(conflicts)} 处规则冲突或失效版本，阻止提交:")
        for c in conflicts[:10]:
            print(f"  • 行 {c.get('row')}: [{c.get('error_type')}] {c.get('message')}")
        if len(conflicts) > 10:
            print(f"  ... 另有 {len(conflicts) - 10} 处冲突。请修复后重试。")
        return

    if not updates:
        print("ℹ️ 未检测到任何所有权 (ownership) 或分类 (category) 变更。")
        return

    print(f"✔ 预检通过！共计检测到 {len(updates)} 处有效评审变更。")
    res = commit_review(preview, store)
    print(f"🎉 成功提交至 lab.db! commit_id: {res.get('commit_id')}, 更新行数: {res.get('lines_updated')}")
    cmd_status(store)


def main() -> None:
    parser = argparse.ArgumentParser(description="Forge Lab Commerce Review Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # status
    subparsers.add_parser("status", help="Show triage and review statistics")

    # export
    p_export = subparsers.add_parser("export", help="Export official 4-sheet review workbook")
    p_export.add_argument("path", nargs="?", default=None, help="Output Excel path")

    # auto-triage
    p_triage = subparsers.add_parser("auto-triage", help="Auto-classify high confidence lines")
    p_triage.add_argument("--apply", action="store_true", help="Apply updates to database")
    p_triage.add_argument("--min-confidence", type=float, default=0.85, help="Confidence threshold")

    # commit
    p_commit = subparsers.add_parser("commit", help="Commit reviewed Excel workbook")
    p_commit.add_argument("path", help="Path to reviewed Excel workbook")

    args = parser.parse_args()
    store = CommerceStore()

    if args.command == "status":
        cmd_status(store)
    elif args.command == "export":
        cmd_export(store, args.path)
    elif args.command == "auto-triage":
        cmd_auto_triage(store, apply=args.apply, min_confidence=args.min_confidence)
    elif args.command == "commit":
        cmd_commit(store, args.path)


if __name__ == "__main__":
    main()
