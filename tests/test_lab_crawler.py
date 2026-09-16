from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from uuma.lab_crawler import (
    Alibaba1688Parser,
    CrawlerConfig,
    CrawlerError,
    SourcingCrawlerEngine,
    TaobaoParser,
    find_chrome_executable,
)
from uuma.lab_procurement import ProcurementStore


@pytest.mark.parametrize("during_confirmation", [False, True])
def test_browser_inspection_failure_never_confirms_verification(
    tmp_path, during_confirmation, monkeypatch
):
    # The optional browser dependency is absent from the core test environment.
    class PlaywrightError(Exception):
        pass

    sync_api = ModuleType("playwright.sync_api")
    sync_api.Error = PlaywrightError
    monkeypatch.setitem(sys.modules, "playwright", ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)

    engine = SourcingCrawlerEngine(CrawlerConfig(user_data_dir=tmp_path / "profile"))
    page = MagicMock()
    page.url = "https://s.taobao.com/search"
    failure = PlaywrightError("page closed")
    page.locator.return_value.first.is_visible.side_effect = (
        [True, failure] if during_confirmation else failure
    )

    with pytest.raises(CrawlerError, match="Could not") as caught:
        engine._handle_sliders_or_login(page, "taobao")
    assert caught.value.__cause__ is failure


@pytest.mark.parametrize("parser", [TaobaoParser, Alibaba1688Parser])
def test_parser_unexpected_programming_error_propagates(parser):
    with (
        patch("uuma.lab_crawler.json.loads", side_effect=RuntimeError("unexpected bug")),
        pytest.raises(RuntimeError, match="unexpected bug"),
    ):
        parser.parse_search_html("window.__INITIAL_DATA__ = {};")


@pytest.mark.parametrize("parser", [TaobaoParser, Alibaba1688Parser])
def test_parser_malformed_json_uses_fallback(parser):
    assert parser.parse_search_html("window.__INITIAL_DATA__ = {invalid};") == []


def test_find_chrome_and_config():
    path = find_chrome_executable()
    assert path is not None
    assert "chrome.exe" in path.lower()

    config = CrawlerConfig()
    engine = SourcingCrawlerEngine(config)
    status = engine.check_environment()
    assert status["chrome_installed"] is True
    assert "procurement" in str(status["profile_dir"])


def test_taobao_parser_with_json_data():
    sample_json = {
        "itemsArray": [
            {
                "title": "IBT-2 43A 直流电机驱动板",
                "price": "18.50",
                "nick": "优信电子专营店",
                "item_id": "12345678",
                "view_fee": "0.00",
            },
            {
                "title": "BTS7960 大功率驱动模块",
                "price": "16.80",
                "nick": "安信可旗舰店",
                "item_id": "87654321",
                "view_fee": "6.00",
            },
        ]
    }
    html = f"""
    <html>
    <head>
    <script>
    window.__INITIAL_DATA__ = {json.dumps(sample_json)};
    </script>
    </head>
    <body>Content</body>
    </html>
    """
    items = TaobaoParser.parse_search_html(html)
    assert len(items) == 2
    assert items[0]["shop_name"] == "优信电子专营店"
    assert items[0]["unit_price"] == 18.50
    assert items[0]["product_url"] == "https://item.taobao.com/item.htm?id=12345678"
    assert items[1]["unit_price"] == 16.80
    assert items[1]["shipping_fee"] == 6.00


def test_taobao_parser_with_dom_fallback():
    html = """
    <div>
        <a href="https://item.taobao.com/item.htm?id=99999">
            <span class="title">BTS7960 43A智能车电机驱动模块</span>
            <span class="price">¥17.90</span>
        </a>
    </div>
    """
    items = TaobaoParser.parse_search_html(html)
    assert len(items) == 1
    assert items[0]["product_url"] == "https://item.taobao.com/item.htm?id=99999"
    assert items[0]["unit_price"] == 17.90


def test_1688_parser_with_json_data():
    sample_json = {
        "offerList": [
            {
                "title": "BTS7960 直流电机驱动 批发",
                "price": "11.50",
                "companyName": "深圳市华强动力科技有限公司",
                "id": "6543210",
                "quantityBegin": "5",
            }
        ]
    }
    html = f"""
    <html>
    <body>
    <script>
    window.__INITIAL_DATA__ = {json.dumps(sample_json)};
    </script>
    </body>
    </html>
    """
    items = Alibaba1688Parser.parse_search_html(html)
    assert len(items) == 1
    assert items[0]["shop_name"] == "深圳市华强动力科技有限公司"
    assert items[0]["unit_price"] == 11.50
    assert items[0]["moq"] == 5.0
    assert items[0]["product_url"] == "https://detail.1688.com/offer/6543210.html"


def test_1688_parser_with_dom_fallback():
    html = """
    <div>
        <a href="https://detail.1688.com/offer/11223344.html">
            <span>BTS7960 智能小车电机驱动板 10个起批</span>
            <span>¥12.00</span>
        </a>
    </div>
    """
    items = Alibaba1688Parser.parse_search_html(html)
    assert len(items) == 1
    assert items[0]["unit_price"] == 12.00
    assert items[0]["product_url"] == "https://detail.1688.com/offer/11223344.html"


def test_search_harvest_and_evaluate_pipeline(tmp_path: Path):
    lab_db = tmp_path / "test_lab.db"
    store = ProcurementStore(lab_db)
    engine = SourcingCrawlerEngine(CrawlerConfig(user_data_dir=tmp_path / "profile"))

    def mock_crawl(platform: str, query: str, max_results: int = 5):
        if platform == "taobao":
            return [
                {
                    "platform": "taobao",
                    "shop_name": "优信电子",
                    "product_title": "IBT-2 43A 驱动板",
                    "product_url": "https://item.taobao.com/item.htm?id=111",
                    "unit_price": 18.00,
                    "pack_quantity": 1.0,
                    "moq": 1.0,
                    "shipping_fee": 6.00,
                    "free_shipping_threshold": 30.00,
                }
            ]
        elif platform == "1688":
            return [
                {
                    "platform": "1688",
                    "shop_name": "动力电子1688",
                    "product_title": "BTS7960 驱动板",
                    "product_url": "https://detail.1688.com/offer/222.html",
                    "unit_price": 12.50,
                    "pack_quantity": 1.0,
                    "moq": 2.0,
                    "shipping_fee": 8.00,
                    "free_shipping_threshold": None,
                }
            ]
        return []

    with patch.object(engine, "crawl_platform", side_effect=mock_crawl):
        result = engine.search_harvest_and_evaluate(
            query="IBT-2",
            target_quantity=2.0,
            proc_store=store,
        )

        assert result["query"] == "IBT-2"
        assert result["harvested_offers_count"] == 2
        assert len(result["evaluation"]["strategies"]) == 3
        lowest = result["evaluation"]["strategies"]["lowest_landed_cost"]
        assert lowest["status"] == "FEASIBLE"
        # 1688: 2 * 12.50 + 8.00 = 33.00 vs Taobao: 2 * 18.00 = 36.00 (free over 30).
        # 33.00 is lowest!
        assert lowest["total_landed_cost"] == 33.00
