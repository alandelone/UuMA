from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

REQUIREMENT_STATUSES = {"OPEN", "SOURCING", "ORDERED", "FULFILLED", "CANCELLED"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class ProcurementError(ValueError):
    pass


class ProcurementStore:
    def __init__(self, database_path: Path | str):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.bootstrap()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database_path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def bootstrap(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS component_refs (
                    component_id TEXT PRIMARY KEY,
                    display_name_snapshot TEXT,
                    source_system TEXT NOT NULL DEFAULT 'eschematic',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS purchase_lots (
                    lot_id TEXT PRIMARY KEY,
                    component_id TEXT NOT NULL REFERENCES component_refs(component_id),
                    supplier TEXT,
                    offer_ref TEXT,
                    ordered_quantity REAL,
                    received_at TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sourcing_requirements (
                    requirement_id TEXT PRIMARY KEY,
                    component_id TEXT REFERENCES component_refs(component_id),
                    item_name TEXT NOT NULL,
                    specs TEXT NOT NULL DEFAULT '',
                    target_quantity REAL NOT NULL CHECK(target_quantity > 0),
                    target_unit_price REAL,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS sourcing_term_rules (
                    rule_id TEXT PRIMARY KEY,
                    target_name TEXT UNIQUE NOT NULL,
                    aliases_json TEXT NOT NULL DEFAULT '[]',
                    package_keywords_json TEXT NOT NULL DEFAULT '[]',
                    raw_material_alternatives_json TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS supplier_offers (
                    offer_id TEXT PRIMARY KEY,
                    requirement_id TEXT REFERENCES sourcing_requirements(requirement_id),
                    platform TEXT NOT NULL,
                    shop_name TEXT NOT NULL,
                    product_title TEXT NOT NULL,
                    variant_name TEXT NOT NULL DEFAULT '',
                    product_url TEXT NOT NULL DEFAULT '',
                    unit_price REAL NOT NULL CHECK(unit_price >= 0),
                    pack_quantity REAL NOT NULL DEFAULT 1.0 CHECK(pack_quantity > 0),
                    moq REAL NOT NULL DEFAULT 1.0 CHECK(moq > 0),
                    tiered_prices_json TEXT NOT NULL DEFAULT '[]',
                    shipping_fee REAL NOT NULL DEFAULT 0.0 CHECK(shipping_fee >= 0),
                    free_shipping_threshold REAL,
                    captured_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS sourcing_evaluations (
                    evaluation_id TEXT PRIMARY KEY,
                    requirement_ids_json TEXT NOT NULL,
                    strategy_results_json TEXT NOT NULL,
                    evaluated_at TEXT NOT NULL
                );
                """
            )

    # -------------------------------------------------------------------------
    # Component ref helper
    # -------------------------------------------------------------------------
    def register_component(self, component_id: str, display_name: str = "") -> dict[str, str]:
        cid = component_id.strip()
        if not cid:
            raise ProcurementError("component_id is required.")
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO component_refs(component_id, display_name_snapshot, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(component_id) DO UPDATE SET
                    display_name_snapshot=COALESCE(excluded.display_name_snapshot, component_refs.display_name_snapshot),
                    updated_at=excluded.updated_at
                """,
                (cid, display_name.strip() or None, _now()),
            )
        return {"component_id": cid, "status": "registered"}

    # -------------------------------------------------------------------------
    # Sourcing Requirements CRUD
    # -------------------------------------------------------------------------
    def create_requirement(
        self,
        item_name: str,
        target_quantity: float,
        *,
        component_id: str | None = None,
        specs: str = "",
        target_unit_price: float | None = None,
        metadata: dict[str, Any] | None = None,
        requirement_id: str | None = None,
    ) -> dict[str, Any]:
        name = item_name.strip()
        if not name:
            raise ProcurementError("item_name is required.")
        if target_quantity <= 0:
            raise ProcurementError("target_quantity must be positive.")
        if target_unit_price is not None and target_unit_price < 0:
            raise ProcurementError("target_unit_price cannot be negative.")

        cid = component_id.strip() if component_id and component_id.strip() else None
        if cid:
            self.register_component(cid, name)

        rid = requirement_id.strip() if requirement_id and requirement_id.strip() else _id("req")
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        created_at = _now()

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO sourcing_requirements(
                    requirement_id, component_id, item_name, specs, target_quantity,
                    target_unit_price, status, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
                """,
                (rid, cid, name, specs.strip(), float(target_quantity), target_unit_price, created_at, meta_json),
            )

        return self.get_requirement(rid)

    def get_requirement(self, requirement_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM sourcing_requirements WHERE requirement_id = ?",
                (requirement_id.strip(),),
            ).fetchone()
            if row is None:
                raise ProcurementError(f"Requirement '{requirement_id}' not found.")
            res = dict(row)
            res["metadata"] = json.loads(res.pop("metadata_json") or "{}")
            return res

    def list_requirements(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        query = "SELECT * FROM sourcing_requirements"
        params: list[Any] = []
        if status:
            st = status.strip().upper()
            if st not in REQUIREMENT_STATUSES:
                raise ProcurementError(f"Unknown status '{status}'. Valid: {sorted(REQUIREMENT_STATUSES)}")
            query += " WHERE status = ?"
            params.append(st)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, limit))

        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
            results = []
            for row in rows:
                item = dict(row)
                item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
                results.append(item)
            return results

    def update_requirement_status(self, requirement_id: str, status: str) -> dict[str, Any]:
        st = status.strip().upper()
        if st not in REQUIREMENT_STATUSES:
            raise ProcurementError(f"Unknown status '{status}'. Valid: {sorted(REQUIREMENT_STATUSES)}")
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE sourcing_requirements SET status = ? WHERE requirement_id = ?",
                (st, requirement_id.strip()),
            )
            if cursor.rowcount == 0:
                raise ProcurementError(f"Requirement '{requirement_id}' not found.")
        return self.get_requirement(requirement_id)

    def create_requirements_from_shortages(
        self, shortages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        created: list[dict[str, Any]] = []
        for row in shortages:
            cid = str(row.get("component_id", "")).strip() or None
            qty = float(row.get("shortage", row.get("required", row.get("quantity", 0))))
            if qty <= 0:
                continue
            name = str(row.get("item_name") or row.get("display_name") or cid or "Unnamed Component").strip()
            specs = str(row.get("specs") or row.get("package") or "").strip()
            req = self.create_requirement(
                item_name=name,
                target_quantity=qty,
                component_id=cid,
                specs=specs,
                metadata={"origin": "bom_shortage", "raw_row": row},
            )
            created.append(req)
        return created

    # -------------------------------------------------------------------------
    # Term Expansion & Alias Rules
    # -------------------------------------------------------------------------
    def save_term_rule(
        self,
        target_name: str,
        aliases: list[str],
        *,
        package_keywords: list[str] | None = None,
        raw_materials: list[dict[str, Any]] | None = None,
        rule_id: str | None = None,
    ) -> dict[str, Any]:
        key = target_name.strip().upper()
        if not key:
            raise ProcurementError("target_name is required.")
        rid = rule_id.strip() if rule_id and rule_id.strip() else _id("rule")
        now = _now()
        aliases_json = json.dumps([a.strip() for a in aliases if a.strip()], ensure_ascii=False)
        pkg_json = json.dumps([p.strip() for p in (package_keywords or []) if p.strip()], ensure_ascii=False)
        raw_json = json.dumps(raw_materials or [], ensure_ascii=False)

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO sourcing_term_rules(
                    rule_id, target_name, aliases_json, package_keywords_json,
                    raw_material_alternatives_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(target_name) DO UPDATE SET
                    aliases_json=excluded.aliases_json,
                    package_keywords_json=excluded.package_keywords_json,
                    raw_material_alternatives_json=excluded.raw_material_alternatives_json,
                    updated_at=excluded.updated_at
                """,
                (rid, key, aliases_json, pkg_json, raw_json, now),
            )
        return self.get_term_rule(key)  # type: ignore

    def get_term_rule(self, target_name: str) -> dict[str, Any] | None:
        key = target_name.strip().upper()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM sourcing_term_rules WHERE target_name = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            res = dict(row)
            res["aliases"] = json.loads(res.pop("aliases_json") or "[]")
            res["package_keywords"] = json.loads(res.pop("package_keywords_json") or "[]")
            res["raw_material_alternatives"] = json.loads(res.pop("raw_material_alternatives_json") or "[]")
            return res

    def lookup_or_expand_terms(self, query: str, component_id: str = "") -> dict[str, Any]:
        q = query.strip()
        cid = component_id.strip()
        # 1. Try local rule database
        for target in [q, cid]:
            if target:
                rule = self.get_term_rule(target)
                if rule:
                    return {
                        "query": q or cid,
                        "component_id": cid,
                        "aliases": rule["aliases"],
                        "package_keywords": rule["package_keywords"],
                        "raw_material_alternatives": rule["raw_material_alternatives"],
                        "source": "local_rule",
                        "rule_id": rule["rule_id"],
                    }

        # 2. Heuristic rule-based candidate expansion
        aliases: list[str] = [q] if q else []
        package_keywords: list[str] = []
        raw_materials: list[dict[str, Any]] = []

        # Detect chip models or alphanumeric identifiers like BTS7960, LM2596, ESP32, STM32F103
        model_matches = re.findall(r"[A-Za-z]+[0-9]+[A-Za-z0-9_\-]*", q or cid)
        for m in model_matches:
            upper_m = m.upper()
            if upper_m not in [a.upper() for a in aliases]:
                aliases.append(upper_m)
            aliases.append(f"{upper_m} 模块")
            aliases.append(f"{upper_m} 芯片")

        if any("驱动" in a or "DRIVER" in a.upper() or "MOTOR" in a.upper() for a in aliases):
            aliases.extend(["直流电机驱动", "大功率H桥", "智能车驱动板"])
            package_keywords.extend(["TO-263", "贴片", "带散热片"])

        return {
            "query": q or cid,
            "component_id": cid,
            "aliases": list(dict.fromkeys(aliases)),
            "package_keywords": list(dict.fromkeys(package_keywords)),
            "raw_material_alternatives": raw_materials,
            "source": "heuristic_candidate",
            "rule_id": None,
        }

    # -------------------------------------------------------------------------
    # Supplier Offers Management
    # -------------------------------------------------------------------------
    def record_offers(self, offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        recorded = []
        now = _now()
        with self.connect() as connection:
            for item in offers:
                platform = str(item.get("platform", "other")).strip().lower()
                shop_name = str(item.get("shop_name", "")).strip()
                title = str(item.get("product_title", "")).strip()
                unit_price = float(item.get("unit_price", -1))
                if not shop_name or not title:
                    raise ProcurementError("Each offer requires 'shop_name' and 'product_title'.")
                if unit_price < 0:
                    raise ProcurementError("Each offer requires 'unit_price' >= 0.")

                oid = str(item.get("offer_id") or "").strip() or _id("off")
                req_id = str(item.get("requirement_id") or "").strip() or None
                variant = str(item.get("variant_name", "")).strip()
                url = str(item.get("product_url", "")).strip()
                pack_qty = max(float(item.get("pack_quantity", 1.0)), 0.0001)
                moq = max(float(item.get("moq", 1.0)), 0.0001)
                shipping_fee = max(float(item.get("shipping_fee", 0.0)), 0.0)
                free_thresh = item.get("free_shipping_threshold")
                free_thresh_val = float(free_thresh) if free_thresh is not None else None

                tiered_prices = item.get("tiered_prices", [])
                if isinstance(tiered_prices, str):
                    tiered_json = tiered_prices
                else:
                    tiered_json = json.dumps(tiered_prices, ensure_ascii=False)

                meta = item.get("metadata", {})
                meta_json = json.dumps(meta, ensure_ascii=False)

                connection.execute(
                    """
                    INSERT INTO supplier_offers(
                        offer_id, requirement_id, platform, shop_name, product_title,
                        variant_name, product_url, unit_price, pack_quantity, moq,
                        tiered_prices_json, shipping_fee, free_shipping_threshold,
                        captured_at, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        oid, req_id, platform, shop_name, title, variant, url,
                        unit_price, pack_qty, moq, tiered_json, shipping_fee,
                        free_thresh_val, now, meta_json,
                    ),
                )
                recorded.append(oid)

        return [self.get_offer(oid) for oid in recorded]

    def get_offer(self, offer_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM supplier_offers WHERE offer_id = ?", (offer_id.strip(),)
            ).fetchone()
            if row is None:
                raise ProcurementError(f"Offer '{offer_id}' not found.")
            res = dict(row)
            res["tiered_prices"] = json.loads(res.pop("tiered_prices_json") or "[]")
            res["metadata"] = json.loads(res.pop("metadata_json") or "{}")
            return res

    def list_offers(
        self, requirement_id: str = "", shop_name: str = "", limit: int = 100
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM supplier_offers WHERE 1=1"
        params: list[Any] = []
        if requirement_id.strip():
            query += " AND requirement_id = ?"
            params.append(requirement_id.strip())
        if shop_name.strip():
            query += " AND shop_name LIKE ?"
            params.append(f"%{shop_name.strip()}%")
        query += " ORDER BY captured_at DESC LIMIT ?"
        params.append(max(1, limit))

        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
            results = []
            for row in rows:
                item = dict(row)
                item["tiered_prices"] = json.loads(item.pop("tiered_prices_json") or "[]")
                item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
                results.append(item)
            return results

    # -------------------------------------------------------------------------
    # Snippet Parser
    # -------------------------------------------------------------------------
    def parse_offer_snippet(self, text: str) -> dict[str, Any]:
        s = text.strip()
        if not s:
            raise ProcurementError("Snippet text cannot be empty.")

        # Platform detection
        platform = "other"
        if "taobao.com" in s or "tb.cn" in s or "【淘宝】" in s:
            platform = "taobao"
        elif "1688.com" in s or "【1688】" in s:
            platform = "1688"
        elif "szlcsc.com" in s or "lcsc.com" in s or "立创" in s:
            platform = "lcsc"
        elif "yangkeduo.com" in s or "pinduoduo.com" in s or "拼多多" in s:
            platform = "pdd"
        elif "jd.com" in s or "京东" in s:
            platform = "jd"

        # URL extraction
        url_match = re.search(r"https?://[^\s，,）)\"'>]+", s)
        product_url = url_match.group(0) if url_match else ""

        # Price extraction: ¥16.50, ￥16.50, 16.5元, 单价: 16.5, 价格: 16.5
        price = 0.0
        price_match = re.search(r"(?:[¥￥\$]|单价[:：]?\s*|价格[:：]?\s*)([0-9]+(?:\.[0-9]+)?)", s)
        if not price_match:
            price_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*元", s)
        if price_match:
            price = float(price_match.group(1))

        # Shipping fee
        shipping_fee = 0.0
        free_thresh = None
        if "包邮" in s:
            shipping_fee = 0.0
        ship_match = re.search(r"运费[:：]?\s*(?:[¥￥])?\s*([0-9]+(?:\.[0-9]+)?)", s)
        if ship_match:
            shipping_fee = float(ship_match.group(1))

        thresh_match = re.search(r"满\s*([0-9]+(?:\.[0-9]+)?)\s*(?:包邮|免运费)", s)
        if thresh_match:
            free_thresh = float(thresh_match.group(1))

        # MOQ
        moq = 1.0
        moq_match = re.search(r"(?:起订量|起批|起订|MOQ)[:：]?\s*([0-9]+(?:\.[0-9]+)?)", s, re.IGNORECASE)
        if not moq_match:
            moq_match = re.search(r"([0-9]+)\s*(?:件|个|只|片|套)?\s*起批", s)
        if moq_match:
            moq = float(moq_match.group(1))

        # Pack quantity
        pack_quantity = 1.0
        pack_match = re.search(r"(?:每包|每盘|包装规格)[:：]?\s*([0-9]+(?:\.[0-9]+)?)", s)
        if not pack_match:
            pack_match = re.search(r"([0-9]+)\s*(?:只|片|个|pcs|PCS)/(?:包|盘|袋)", s, re.IGNORECASE)
        if pack_match:
            pack_quantity = float(pack_match.group(1))

        # Shop name
        shop_name = ""
        shop_match = re.search(r"(?:店铺|店名|商家)[:：]?\s*([^\s，,、\n]+)", s)
        if shop_match:
            shop_name = shop_match.group(1)
        else:
            shop_suffix_match = re.search(r"([A-Za-z0-9\u4e00-\u9fa5]{2,15}(?:旗舰店|专营店|专卖店|企业店|商行|电子|科技))", s)
            if shop_suffix_match:
                shop_name = shop_suffix_match.group(1)

        # Title: extract from first non-empty line or clean snippet
        lines = [line.strip() for line in s.splitlines() if line.strip()]
        title = lines[0] if lines else s[:60]
        # Clean title from URL or price badges if present
        title = re.sub(r"https?://[^\s]+", "", title).strip()
        title = re.sub(r"【[^】]+】", "", title).strip()
        if not title:
            title = f"{platform.upper()} 商品"

        return {
            "platform": platform,
            "shop_name": shop_name or f"{platform}_shop",
            "product_title": title,
            "product_url": product_url,
            "unit_price": price,
            "pack_quantity": pack_quantity,
            "moq": moq,
            "shipping_fee": shipping_fee,
            "free_shipping_threshold": free_thresh,
            "variant_name": "",
            "raw_snippet": s,
        }

    # -------------------------------------------------------------------------
    # Multi-Strategy Sourcing Optimization
    # -------------------------------------------------------------------------
    def evaluate_sourcing(self, requirement_ids: list[str]) -> dict[str, Any]:
        if not requirement_ids:
            raise ProcurementError("requirement_ids cannot be empty.")

        requirements = [self.get_requirement(rid) for rid in requirement_ids]
        offers_by_req: dict[str, list[dict[str, Any]]] = {}
        all_offers = self.list_offers(limit=1000)

        for req in requirements:
            rid = req["requirement_id"]
            name_upper = req["item_name"].upper()
            cid = (req["component_id"] or "").upper()
            term_info = self.lookup_or_expand_terms(req["item_name"], req["component_id"] or "")
            alias_set = {a.upper() for a in term_info["aliases"]}
            alias_set.add(name_upper)
            if cid:
                alias_set.add(cid)

            matched = []
            for off in all_offers:
                # 1. Exact requirement_id match
                if off["requirement_id"] == rid:
                    matched.append(off)
                    continue
                # 2. Or title match on name or aliases
                off_title_upper = off["product_title"].upper()
                if any(alias in off_title_upper for alias in alias_set if len(alias) >= 2):
                    matched.append(off)

            offers_by_req[rid] = matched

        # Helper to compute cost for an offer covering a requirement
        def compute_offer_line_cost(req: dict[str, Any], off: dict[str, Any]) -> dict[str, Any]:
            target_qty = float(req["target_quantity"])
            pack_qty = max(float(off["pack_quantity"]), 1.0)
            moq = max(float(off["moq"]), 1.0)
            needed_packs = math.ceil(target_qty / pack_qty)
            order_packs = max(math.ceil(moq / pack_qty) if moq > pack_qty else moq, needed_packs)
            order_qty = order_packs * pack_qty

            # Check tiered pricing (pack price)
            pack_price = float(off["unit_price"])
            tiered = off.get("tiered_prices", [])
            if tiered:
                sorted_tiers = sorted(tiered, key=lambda t: float(t.get("min_qty", 0)), reverse=True)
                for t in sorted_tiers:
                    min_q = float(t.get("min_qty", 0))
                    if order_qty >= min_q or order_packs >= min_q:
                        pack_price = float(t.get("unit_price", pack_price))
                        break

            goods_cost = round(order_packs * pack_price, 2)
            effective_unit_price = round(goods_cost / order_qty, 4) if order_qty > 0 else pack_price
            return {
                "requirement_id": req["requirement_id"],
                "item_name": req["item_name"],
                "offer_id": off["offer_id"],
                "platform": off["platform"],
                "shop_name": off["shop_name"],
                "product_title": off["product_title"],
                "product_url": off["product_url"],
                "order_quantity": order_qty,
                "order_packs": order_packs,
                "effective_unit_price": effective_unit_price,
                "goods_cost": goods_cost,
                "shipping_fee": float(off["shipping_fee"]),
                "free_shipping_threshold": off.get("free_shipping_threshold"),
            }

        # Helper to aggregate shop shipping
        def compute_shop_shipping(lines: list[dict[str, Any]]) -> tuple[dict[str, float], float]:
            shop_goods: dict[str, float] = {}
            shop_base_ship: dict[str, float] = {}
            shop_thresholds: dict[str, float | None] = {}

            for line in lines:
                shop = line["shop_name"]
                shop_goods[shop] = round(shop_goods.get(shop, 0.0) + line["goods_cost"], 2)
                shop_base_ship[shop] = max(shop_base_ship.get(shop, 0.0), line["shipping_fee"])
                if line["free_shipping_threshold"] is not None:
                    curr_th = shop_thresholds.get(shop)
                    shop_thresholds[shop] = min(curr_th, line["free_shipping_threshold"]) if curr_th is not None else line["free_shipping_threshold"]

            final_shipping: dict[str, float] = {}
            total_shipping = 0.0
            for shop, goods in shop_goods.items():
                thresh = shop_thresholds.get(shop)
                if thresh is not None and goods >= thresh:
                    actual = 0.0
                else:
                    actual = shop_base_ship[shop]
                final_shipping[shop] = actual
                total_shipping += actual

            return final_shipping, round(total_shipping, 2)

        all_candidate_lines: dict[str, list[dict[str, Any]]] = {}
        missing_reqs = []
        for req in requirements:
            rid = req["requirement_id"]
            offs = offers_by_req.get(rid, [])
            if not offs:
                missing_reqs.append(req)
                continue
            all_candidate_lines[rid] = [compute_offer_line_cost(req, off) for off in offs]

        lowest_landed_cost_strategy: dict[str, Any] = {"status": "UNAVAILABLE"}
        minimal_shipments_strategy: dict[str, Any] = {"status": "UNAVAILABLE"}
        diy_strategy: dict[str, Any] = {"status": "UNAVAILABLE", "alternatives": []}

        if len(missing_reqs) == 0:
            candidate_shops = sorted({line["shop_name"] for lines in all_candidate_lines.values() for line in lines})

            best_landed_total = float("inf")
            best_landed_assignment: list[dict[str, Any]] = []

            total_combos = 1
            for lines in all_candidate_lines.values():
                total_combos *= len(lines)

            if total_combos <= 2000:
                import itertools

                req_keys = list(all_candidate_lines.keys())
                for combo in itertools.product(*[all_candidate_lines[k] for k in req_keys]):
                    lines = list(combo)
                    _, total_ship = compute_shop_shipping(lines)
                    total_goods = sum(l["goods_cost"] for l in lines)
                    total_landed = round(total_goods + total_ship, 2)
                    if total_landed < best_landed_total:
                        best_landed_total = total_landed
                        best_landed_assignment = lines
            else:
                chosen: list[dict[str, Any]] = []
                for lines in all_candidate_lines.values():
                    best_line = min(lines, key=lambda l: l["goods_cost"])
                    chosen.append(best_line)
                _, total_ship = compute_shop_shipping(chosen)
                best_landed_total = round(sum(l["goods_cost"] for l in chosen) + total_ship, 2)
                best_landed_assignment = chosen

            shop_ship_map, ship_total = compute_shop_shipping(best_landed_assignment)
            lowest_landed_cost_strategy = {
                "status": "FEASIBLE",
                "strategy_name": "Lowest Landed Cost (全网最低到手总价)",
                "total_goods_cost": round(sum(l["goods_cost"] for l in best_landed_assignment), 2),
                "total_shipping_fee": ship_total,
                "total_landed_cost": best_landed_total,
                "shop_count": len(shop_ship_map),
                "shops_shipping": shop_ship_map,
                "selected_items": best_landed_assignment,
            }

            # Strategy 2: Single-Shop bundle
            single_shop_candidates = []
            for shop in candidate_shops:
                can_cover_all = True
                shop_lines = []
                for rid, lines in all_candidate_lines.items():
                    matching_in_shop = [l for l in lines if l["shop_name"] == shop]
                    if not matching_in_shop:
                        can_cover_all = False
                        break
                    shop_lines.append(min(matching_in_shop, key=lambda l: l["goods_cost"]))
                if can_cover_all:
                    _, ship_cost = compute_shop_shipping(shop_lines)
                    tot = round(sum(l["goods_cost"] for l in shop_lines) + ship_cost, 2)
                    single_shop_candidates.append((tot, shop, shop_lines, ship_cost))

            if single_shop_candidates:
                single_shop_candidates.sort(key=lambda x: x[0])
                tot, shop, shop_lines, ship_cost = single_shop_candidates[0]
                minimal_shipments_strategy = {
                    "status": "FEASIBLE",
                    "strategy_name": "Single-Shop Bundle (极简单店一站式打包)",
                    "shop_name": shop,
                    "shop_count": 1,
                    "total_goods_cost": round(sum(l["goods_cost"] for l in shop_lines), 2),
                    "total_shipping_fee": ship_cost,
                    "total_landed_cost": tot,
                    "selected_items": shop_lines,
                }
            else:
                minimal_shipments_strategy = {
                    "status": "PARTIAL",
                    "strategy_name": "Minimal Multi-Shop Bundle (暂无法单店买齐，已精简为最少店铺)",
                    "shop_count": lowest_landed_cost_strategy.get("shop_count", 0),
                    "total_landed_cost": lowest_landed_cost_strategy.get("total_landed_cost", 0),
                    "selected_items": lowest_landed_cost_strategy.get("selected_items", []),
                }

        # Strategy 3: Raw material alternatives
        diy_alternatives = []
        for req in requirements:
            term_info = self.lookup_or_expand_terms(req["item_name"], req["component_id"] or "")
            raws = term_info.get("raw_material_alternatives", [])
            if raws:
                for alt in raws:
                    diy_alternatives.append({
                        "requirement_id": req["requirement_id"],
                        "finished_item": req["item_name"],
                        "alternative_name": alt.get("name", "DIY Alternative"),
                        "estimated_diy_cost": alt.get("estimated_diy_cost", 0.0),
                        "details": alt.get("details", ""),
                    })

        if diy_alternatives:
            diy_strategy = {
                "status": "AVAILABLE",
                "strategy_name": "Raw Material / First-Principles DIY (第一性原理自制替代)",
                "alternatives": diy_alternatives,
            }

        eval_id = _id("eval")
        result = {
            "evaluation_id": eval_id,
            "requirement_ids": requirement_ids,
            "missing_requirements": [r["requirement_id"] for r in missing_reqs],
            "strategies": {
                "lowest_landed_cost": lowest_landed_cost_strategy,
                "minimal_shipments": minimal_shipments_strategy,
                "raw_material_diy": diy_strategy,
            },
            "evaluated_at": _now(),
        }

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO sourcing_evaluations(
                    evaluation_id, requirement_ids_json, strategy_results_json, evaluated_at
                ) VALUES (?, ?, ?, ?)
                """,
                (eval_id, json.dumps(requirement_ids), json.dumps(result, ensure_ascii=False), _now()),
            )

        return result

    # -------------------------------------------------------------------------
    # Order Confirmation & Bridge to purchase_lots
    # -------------------------------------------------------------------------
    def confirm_order(self, order_plan: dict[str, Any]) -> dict[str, Any]:
        selected_offers = order_plan.get("selected_offers", [])
        if not selected_offers:
            raise ProcurementError("order_plan must contain 'selected_offers'.")

        order_id = str(order_plan.get("order_id") or "").strip() or _id("order")
        notes = str(order_plan.get("notes", "")).strip()
        created_lots: list[dict[str, Any]] = []
        updated_requirements: list[str] = []
        now = _now()

        with self.connect() as connection:
            for item in selected_offers:
                qty = float(item.get("ordered_quantity", item.get("order_quantity", 0)))
                if qty <= 0:
                    raise ProcurementError("Each selected offer must have positive 'ordered_quantity'.")

                rid = str(item.get("requirement_id") or "").strip() or None
                cid = str(item.get("component_id") or "").strip()
                item_name = str(item.get("item_name", "")).strip()

                if not cid and rid:
                    req_row = connection.execute(
                        "SELECT component_id, item_name FROM sourcing_requirements WHERE requirement_id = ?",
                        (rid,),
                    ).fetchone()
                    if req_row:
                        cid = req_row["component_id"] or ""
                        if not item_name:
                            item_name = req_row["item_name"]

                if not cid:
                    cid = f"CMP-{uuid4().hex[:8].upper()}"

                connection.execute(
                    """
                    INSERT INTO component_refs(component_id, display_name_snapshot, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(component_id) DO UPDATE SET
                        display_name_snapshot=COALESCE(excluded.display_name_snapshot, component_refs.display_name_snapshot),
                        updated_at=excluded.updated_at
                    """,
                    (cid, item_name or None, now),
                )

                lot_id = _id("lot")
                supplier = str(item.get("shop_name") or item.get("platform") or "unknown_supplier").strip()
                offer_ref = str(item.get("offer_id") or item.get("product_url") or "").strip()

                meta = {
                    "order_id": order_id,
                    "requirement_id": rid,
                    "unit_price": item.get("effective_unit_price", item.get("unit_price")),
                    "platform": item.get("platform"),
                    "product_url": item.get("product_url"),
                    "notes": notes,
                }

                connection.execute(
                    """
                    INSERT INTO purchase_lots(
                        lot_id, component_id, supplier, offer_ref, ordered_quantity,
                        received_at, metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
                    """,
                    (lot_id, cid, supplier, offer_ref or None, qty, json.dumps(meta, ensure_ascii=False), now),
                )

                created_lots.append({
                    "lot_id": lot_id,
                    "component_id": cid,
                    "supplier": supplier,
                    "offer_ref": offer_ref,
                    "ordered_quantity": qty,
                    "status": "AWAITING_RECEIVING",
                })

                if rid:
                    connection.execute(
                        "UPDATE sourcing_requirements SET status = 'ORDERED' WHERE requirement_id = ?",
                        (rid,),
                    )
                    updated_requirements.append(rid)

        return {
            "order_id": order_id,
            "status": "ORDER_CONFIRMED",
            "created_purchase_lots": created_lots,
            "updated_requirements": list(dict.fromkeys(updated_requirements)),
            "confirmed_at": now,
        }
