from __future__ import annotations

import json
import logging
import os
import random
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .lab_procurement import ProcurementStore, _now

logger = logging.getLogger(__name__)


@dataclass
class CrawlerConfig:
    chrome_channel: str = "chrome"
    user_data_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("UUMA_DATA_DIR", Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "UuMA")
        )
        / "chrome_profiles"
        / "procurement"
    )
    cdp_url: str = ""
    timeout_ms: int = 30000
    headless: bool = False
    min_delay: float = 1.0
    max_delay: float = 2.5


class CrawlerError(RuntimeError):
    pass


def find_chrome_executable() -> str | None:
    candidates = [
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


class TaobaoParser:
    @staticmethod
    def parse_search_html(html: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        # 1. Attempt extracting embedded JSON data (window.__INITIAL_DATA__ or g_page_config)
        json_match = re.search(r"window\.__INITIAL_DATA__\s*=\s*(\{.*?\});", html, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                # Search itemsArray inside the data tree
                items = []
                if "itemlist" in data and "data" in data["itemlist"] and "auctions" in data["itemlist"]["data"]:
                    items = data["itemlist"]["data"]["auctions"]
                elif "data" in data and "itemsArray" in data["data"]:
                    items = data["data"]["itemsArray"]
                elif "itemsArray" in data:
                    items = data["itemsArray"]

                for it in items:
                    raw_price = it.get("price") or it.get("view_price") or it.get("raw_title_price") or 0.0
                    try:
                        price = float(raw_price)
                    except (ValueError, TypeError):
                        price = 0.0
                    title = it.get("title") or it.get("raw_title") or ""
                    title = re.sub(r"<[^>]+>", "", title).strip()
                    shop = it.get("nick") or it.get("shopName") or "淘宝商家"
                    nid = it.get("nid") or it.get("item_id") or it.get("auctionId") or ""
                    url = f"https://item.taobao.com/item.htm?id={nid}" if nid else it.get("detail_url", "")
                    if url and not url.startswith("http"):
                        url = "https:" + url
                    fee = float(it.get("view_fee", 0.0) or 0.0)
                    results.append({
                        "platform": "taobao",
                        "shop_name": shop,
                        "product_title": title,
                        "product_url": url,
                        "unit_price": price,
                        "pack_quantity": 1.0,
                        "moq": 1.0,
                        "shipping_fee": fee,
                        "free_shipping_threshold": None,
                    })
                if results:
                    return results
            except (ValueError, TypeError, KeyError, AttributeError) as e:
                logger.debug("Failed parsing window.__INITIAL_DATA__: %s", e)

        # 2. Regex fallback for product cards in static/rendered HTML
        # Extract title, price, and item url
        item_blocks = re.findall(
            r'<a[^>]*href="([^"]*(?:item\.taobao\.com|detail\.tmall\.com)[^"]*)"[^>]*>(.*?)</a>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        seen_urls = set()
        for href, content in item_blocks:
            clean_url = href.split("?")[0]
            id_match = re.search(r"id=([0-9]+)", href)
            nid = id_match.group(1) if id_match else clean_url
            if nid in seen_urls:
                continue
            seen_urls.add(nid)

            clean_text = re.sub(r"<[^>]+>", " ", content).strip()
            price_match = re.search(r"[¥￥$]\s*([0-9]+(?:\.[0-9]+)?)", clean_text)
            if not price_match:
                price_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*元", clean_text)
            if not price_match:
                price_match = re.search(r"\b([0-9]+\.[0-9]{1,2})\b", clean_text)
            price = float(price_match.group(1)) if price_match else 0.0
            title = re.sub(r"[¥￥$][0-9.]+", "", clean_text).strip()
            if len(title) > 5 and price > 0:
                full_url = href if href.startswith("http") else "https:" + href
                results.append({
                    "platform": "taobao",
                    "shop_name": "淘宝店铺",
                    "product_title": title[:80],
                    "product_url": full_url,
                    "unit_price": price,
                    "pack_quantity": 1.0,
                    "moq": 1.0,
                    "shipping_fee": 0.0,
                    "free_shipping_threshold": None,
                })

        return results


class Alibaba1688Parser:
    @staticmethod
    def parse_search_html(html: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        # 1. Attempt window.data or embedded JSON
        json_match = re.search(r"window\.data\.data\s*=\s*(\{.*?\});", html, re.DOTALL)
        if not json_match:
            json_match = re.search(r"window\.__INITIAL_DATA__\s*=\s*(\{.*?\});", html, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                items = data.get("offerList", []) or data.get("items", []) or []
                for it in items:
                    raw_price = it.get("price") or it.get("priceModel", {}).get("price") or 0.0
                    try:
                        price = float(raw_price)
                    except (ValueError, TypeError):
                        price = 0.0
                    title = it.get("subject") or it.get("title") or ""
                    title = re.sub(r"<[^>]+>", "", title).strip()
                    shop = it.get("companyName") or it.get("shopName") or "1688供应商"
                    oid = it.get("id") or it.get("offerId") or ""
                    url = f"https://detail.1688.com/offer/{oid}.html" if oid else it.get("detailUrl", "")
                    if url and not url.startswith("http"):
                        url = "https:" + url
                    moq = float(it.get("quantityBegin") or it.get("moq") or 1.0)
                    results.append({
                        "platform": "1688",
                        "shop_name": shop,
                        "product_title": title,
                        "product_url": url,
                        "unit_price": price,
                        "pack_quantity": 1.0,
                        "moq": max(moq, 1.0),
                        "shipping_fee": 6.0,  # 1688 typically has base shipping
                        "free_shipping_threshold": None,
                    })
                if results:
                    return results
            except (ValueError, TypeError, KeyError, AttributeError) as e:
                logger.debug("Failed parsing 1688 JSON: %s", e)

        # 2. Regex fallback on detail.1688.com links
        matches = re.findall(
            r'href="([^"]*detail\.1688\.com/offer/([0-9]+)\.html[^"]*)"[^>]*>(.*?)</a>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        seen_ids = set()
        for href, oid, content in matches:
            if oid in seen_ids:
                continue
            seen_ids.add(oid)

            clean_text = re.sub(r"<[^>]+>", " ", content).strip()
            price_match = re.search(r"[¥￥$]\s*([0-9]+(?:\.[0-9]+)?)", clean_text)
            if not price_match:
                price_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*元", clean_text)
            if not price_match:
                price_match = re.search(r"\b([0-9]+\.[0-9]{1,2})\b", clean_text)
            price = float(price_match.group(1)) if price_match else 0.0
            title = re.sub(r"[¥￥$][0-9.]+", "", clean_text).strip()
            if len(title) > 5 and price > 0:
                full_url = href if href.startswith("http") else "https:" + href
                results.append({
                    "platform": "1688",
                    "shop_name": "1688制造工厂/商行",
                    "product_title": title[:80],
                    "product_url": full_url,
                    "unit_price": price,
                    "pack_quantity": 1.0,
                    "moq": 2.0,  # Typical 1688 wholesale MOQ
                    "shipping_fee": 6.0,
                    "free_shipping_threshold": None,
                })

        return results


class SourcingCrawlerEngine:
    def __init__(self, config: CrawlerConfig | None = None):
        self.config = config or CrawlerConfig()
        self.config.user_data_dir.mkdir(parents=True, exist_ok=True)

    def _sleep_random(self) -> None:
        delay = random.uniform(self.config.min_delay, self.config.max_delay)
        time.sleep(delay)

    def check_environment(self) -> dict[str, Any]:
        chrome_path = find_chrome_executable()
        profile_exists = self.config.user_data_dir.exists()
        has_cookies = False
        cookie_file = self.config.user_data_dir / "Default" / "Network" / "Cookies"
        if cookie_file.exists() or (self.config.user_data_dir / "Default" / "Cookies").exists():
            has_cookies = True

        return {
            "chrome_installed": chrome_path is not None,
            "chrome_path": chrome_path,
            "profile_dir": str(self.config.user_data_dir),
            "profile_exists": profile_exists,
            "has_persisted_session": has_cookies,
            "headless": self.config.headless,
        }

    def _handle_sliders_or_login(self, page, platform: str) -> None:
        """Inspect if anti-bot slider or login wall is active, and pause for human if needed."""
        from playwright.sync_api import Error as PlaywrightError

        url = page.url
        is_login = "login.taobao.com" in url or "login.1688.com" in url or "passport.1688.com" in url

        # Check for presence of slider captcha elements
        has_slider = False
        try:
            slider_el = page.locator("#nc_1-stage-1, .baxia-dialog-content, .nc_wrapper, #nocaptcha, iframe[src*='captcha']").first
            if slider_el.is_visible(timeout=1500):
                has_slider = True
        except PlaywrightError as exc:
            raise CrawlerError("Could not inspect browser verification state.") from exc

        if is_login or has_slider:
            msg = (
                f"[Human-in-the-Loop] ⚠️ 检测到 {platform.upper()} "
                + ("登录页面" if is_login else "安全滑块验证")
                + "！\n请在打开的 Chrome 浏览器窗口中完成操作（窗口将保持打开，最长等待 60 秒）..."
            )
            print(msg)
            logger.warning(msg)

            # Wait up to 60 seconds for the user to solve or redirect
            start_wait = time.time()
            while time.time() - start_wait < 60:
                page.wait_for_timeout(1500)
                curr_url = page.url
                if "login.taobao.com" not in curr_url and "login.1688.com" not in curr_url:
                    try:
                        active_slider = page.locator("#nc_1-stage-1, .baxia-dialog-content").first
                        if not active_slider.is_visible(timeout=1000):
                            print(f"[Human-in-the-Loop] ✅ {platform.upper()} 验证已通过，继续自动化抓取。")
                            return
                    except PlaywrightError as exc:
                        raise CrawlerError("Could not confirm browser verification completion.") from exc
            logger.warning(f"Timeout waiting for human to solve {platform} verification.")

    def crawl_platform(self, platform: str, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        from playwright.sync_api import sync_playwright

        platform = platform.lower().strip()
        encoded_query = urllib.parse.quote(query.strip())
        if platform == "taobao":
            search_url = f"https://s.taobao.com/search?q={encoded_query}"
        elif platform == "1688":
            search_url = f"https://s.1688.com/youyuan/index.htm?tab=all&keywords={encoded_query}"
        else:
            raise CrawlerError(f"Unsupported platform: {platform}")

        offers: list[dict[str, Any]] = []

        with sync_playwright() as p:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--lang=zh-CN",
            ]

            context = p.chromium.launch_persistent_context(
                user_data_dir=str(self.config.user_data_dir),
                channel=self.config.chrome_channel,
                headless=self.config.headless,
                args=launch_args,
                viewport={"width": 1280, "height": 800},
            )

            try:
                page = context.new_page()
                # Anti-detection stealth override
                page.add_init_script(
                    """
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    window.chrome = { runtime: {} };
                    """
                )

                logger.info(f"Navigating to {platform} search: {search_url}")
                page.goto(search_url, wait_until="domcontentloaded", timeout=self.config.timeout_ms)
                self._sleep_random()

                # Check and handle verification or login
                self._handle_sliders_or_login(page, platform)

                # Scroll down slightly to trigger lazy-loaded product cards
                page.evaluate("window.scrollBy(0, 500)")
                page.wait_for_timeout(1200)

                html = page.content()

                # Parse DOM using corresponding platform parser
                if platform == "taobao":
                    offers = TaobaoParser.parse_search_html(html)
                elif platform == "1688":
                    offers = Alibaba1688Parser.parse_search_html(html)

            finally:
                context.close()

        # Deduplicate and trim to max_results
        filtered = []
        seen = set()
        for off in offers:
            key = (off["shop_name"], off["product_title"])
            if key not in seen and off["unit_price"] > 0:
                seen.add(key)
                filtered.append(off)
            if len(filtered) >= max_results:
                break

        return filtered

    def search_and_harvest(
        self,
        query: str,
        *,
        platforms: list[str] | None = None,
        max_per_platform: int = 5,
        requirement_id: str | None = None,
    ) -> list[dict[str, Any]]:
        target_platforms = platforms or ["taobao", "1688"]
        harvested: list[dict[str, Any]] = []

        for plat in target_platforms:
            try:
                results = self.crawl_platform(plat, query, max_results=max_per_platform)
                for item in results:
                    item["requirement_id"] = requirement_id
                    item["metadata"] = {"harvested_query": query, "source": "live_crawler", "captured_at": _now()}
                    harvested.append(item)
            except Exception:
                # Isolate platform failures while preserving their complete traceback.
                logger.exception("Error crawling %s for query %r", plat, query)

        return harvested

    def search_harvest_and_evaluate(
        self,
        query: str,
        *,
        requirement_id: str | None = None,
        target_quantity: float = 1.0,
        platforms: list[str] | None = None,
        max_per_platform: int = 5,
        proc_store: ProcurementStore | None = None,
    ) -> dict[str, Any]:
        if proc_store is None:
            raise CrawlerError("ProcurementStore instance is required.")

        # 1. Term expansion: expand query into search aliases
        term_info = proc_store.lookup_or_expand_terms(query)
        primary_query = query.strip()
        if not primary_query and term_info["aliases"]:
            primary_query = term_info["aliases"][0]

        # 2. Ensure requirement exists in DB
        rid = requirement_id
        if not rid:
            req = proc_store.create_requirement(
                item_name=primary_query,
                target_quantity=target_quantity,
                metadata={"origin": "live_crawler_search", "original_query": query},
            )
            rid = req["requirement_id"]
        else:
            req = proc_store.get_requirement(rid)

        # 3. Perform live crawling on Taobao and 1688
        harvested_offers = self.search_and_harvest(
            primary_query,
            platforms=platforms,
            max_per_platform=max_per_platform,
            requirement_id=rid,
        )

        # 4. Record offers into database
        recorded = []
        if harvested_offers:
            recorded = proc_store.record_offers(harvested_offers)

        # 5. Evaluate sourcing using Phase 1 multi-strategy algorithm
        evaluation = proc_store.evaluate_sourcing([rid])

        return {
            "query": query,
            "primary_search_term": primary_query,
            "requirement_id": rid,
            "term_expansion": term_info,
            "harvested_offers_count": len(recorded),
            "harvested_offers": recorded,
            "evaluation": evaluation,
        }
