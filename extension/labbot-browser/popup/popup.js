document.addEventListener("DOMContentLoaded", () => {
  const hostStatusBadge = document.getElementById("hostStatusBadge");
  const activeTabStatus = document.getElementById("activeTabStatus");
  const activeTaskInfo = document.getElementById("activeTaskInfo");
  const btnStart = document.getElementById("btnStart");
  const btnAutoPaging = document.getElementById("btnAutoPaging");
  const btnExportTaobao = document.getElementById("btnExportTaobao");
  const platformSelect = document.getElementById("platformSelect");

  let currentActiveTab = null;

  function updateExportButtonVisibility() {
    if (btnExportTaobao) {
      btnExportTaobao.style.display = platformSelect.value === "taobao" ? "block" : "none";
    }
  }

  platformSelect.addEventListener("change", updateExportButtonVisibility);

  // 1. Detect current active tab & auto-select platform
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs && tabs[0]) {
      currentActiveTab = tabs[0];
      const url = currentActiveTab.url || "";
      const lower = url.toLowerCase();

      activeTabStatus.textContent = `当前标签: ${currentActiveTab.title ? currentActiveTab.title.substring(0, 30) + '... ' : ''}(${url ? new URL(url).hostname : '未知'})`;

      if (lower.includes("taobao.com") || lower.includes("tmall.com")) {
        platformSelect.value = "taobao";
      } else if (lower.includes("shopee.com.my")) {
        platformSelect.value = "shopee";
      } else if (lower.includes("pinduoduo.com") || lower.includes("yangkeduo.com")) {
        platformSelect.value = "pdd";
      }
    } else {
      activeTabStatus.textContent = "未检测到活跃标签页";
    }
    updateExportButtonVisibility();
  });

  // 2. Refresh native host status
  function refreshStatus() {
    chrome.runtime.sendMessage({ type: "GET_STATUS" }, (response) => {
      if (chrome.runtime.lastError || !response) {
        hostStatusBadge.textContent = "DISCONNECTED";
        hostStatusBadge.className = "badge badge-disconnected";
        return;
      }

      const status = response.hostStatus || "DISCONNECTED";
      hostStatusBadge.textContent = status;
      if (status === "CONNECTED") {
        hostStatusBadge.className = "badge badge-connected";
      } else {
        hostStatusBadge.className = "badge badge-disconnected";
      }
    });
  }

  // 3. Click Taobao Export Button across ALL frames
  if (btnExportTaobao) {
    btnExportTaobao.addEventListener("click", () => {
      if (!currentActiveTab || !currentActiveTab.id) {
        activeTaskInfo.innerHTML = "<p style='color:red;'>未检测到活动标签页。</p>";
        return;
      }

      btnExportTaobao.disabled = true;
      activeTaskInfo.innerHTML = "<p>正在跨页面所有框架检索【导出订单】按钮...</p>";

      chrome.scripting.executeScript({
        target: { tabId: currentActiveTab.id, allFrames: true },
        func: () => {
          const candidates = Array.from(document.querySelectorAll("button, a, span, div, i, p"));
          for (const el of candidates) {
            const txt = (el.innerText || el.textContent || "").trim();
            if (txt.includes("导出订单") && el.children.length <= 3) {
              el.click();
              return { success: true, text: txt, url: window.location.href };
            }
          }
          return { success: false, url: window.location.href };
        }
      }, (results) => {
        btnExportTaobao.disabled = false;
        if (chrome.runtime.lastError) {
          activeTaskInfo.innerHTML = `<p style="color:red;">Error: ${chrome.runtime.lastError.message}</p>`;
          return;
        }

        const clicked = (results || []).find(r => r.result && r.result.success);
        if (clicked) {
          activeTaskInfo.innerHTML = `
            <p style="color: #16a34a; font-weight: bold;">✔ 已成功点击淘宝【导出订单】按钮！</p>
            <p style="font-size:12px;color:#4b5563;margin-top:4px;">
              请在网页弹窗中确认导出时间范围，保存 Excel 文件到本地 Downloads 文件夹。<br>
              系统已就绪，可一键读取该 Excel 完成高精度比价与核收！
            </p>
          `;
        } else {
          activeTaskInfo.innerHTML = `
            <p style="color: #d97706;">未在当前页面所有框架中找到【导出订单】按钮。</p>
            <p style="font-size:11px;color:#6b7280;">请确认当前标签页处于已买到的宝贝主列表页面（buyertrade.taobao.com/trade/itemlist.htm）。</p>
          `;
        }
      });
    });
  }

  // 4. Universal In-Frame DOM Extractor
  btnStart.addEventListener("click", () => {
    if (!currentActiveTab || !currentActiveTab.id) {
      activeTaskInfo.innerHTML = "<p style='color:red;'>未找到活跃标签页。</p>";
      return;
    }

    const platform = platformSelect.value;
    const accountId = "alansyling@gmail.com";

    btnStart.disabled = true;
    btnStart.textContent = "Scanning...";
    activeTaskInfo.innerHTML = "<p>正在全面扫描所有框架内的订单卡片与商品链接...</p>";

    // Execute universal parsing across ALL frames
    chrome.scripting.executeScript({
      target: { tabId: currentActiveTab.id, allFrames: true },
      func: runFrameExtraction,
      args: [platform]
    }, (results) => {
      btnStart.disabled = false;
      btnStart.textContent = "Start DOM Extraction";

      if (chrome.runtime.lastError) {
        activeTaskInfo.innerHTML = `<p style="color:red;">扫描失败: ${chrome.runtime.lastError.message}。请刷新当前网页（F5）后再试。</p>`;
        return;
      }

      // Collect orders from all frames
      let allOrders = [];
      const frameSummaries = [];

      (results || []).forEach((res, idx) => {
        if (res && res.result && Array.isArray(res.result.orders) && res.result.orders.length > 0) {
          allOrders = allOrders.concat(res.result.orders);
        }
        if (res && res.result) {
          frameSummaries.push(`Frame ${idx}: ${res.result.note || (res.result.orders ? res.result.orders.length + ' orders' : '0')}`);
        }
      });

      // Deduplicate orders by order_id
      const uniqueOrders = [];
      const seen = new Set();
      for (const ord of allOrders) {
        if (!seen.has(ord.order_id)) {
          seen.add(ord.order_id);
          uniqueOrders.push(ord);
        }
      }

      if (uniqueOrders.length > 0) {
        activeTaskInfo.innerHTML = `<p style="color: #16a34a;"><strong>提取成功！</strong> 正在将 ${uniqueOrders.length} 笔订单回传入库...</p>`;

        const batchId = `${platform}_batch_${Date.now()}`;
        const batch = {
          batch_id: batchId,
          platform: platform,
          account_id: accountId,
          task_id: `task_popup_${platform}_${Date.now()}`,
          orders: uniqueOrders
        };

        chrome.runtime.sendMessage({
          type: "SUBMIT_BATCH",
          batch: batch
        }, (subRes) => {
          if (subRes && subRes.success) {
            activeTaskInfo.innerHTML = `
              <p style="color: #16a34a; font-weight: bold;">✔ 提取并入库成功！</p>
              <p style="font-size:12px;color:#374151;">已入库 <strong>${uniqueOrders.length}</strong> 笔真实订单到 lab.db 并完成不可变归档。</p>
            `;
          } else {
            activeTaskInfo.innerHTML = `<p style="color:red;">入库保存失败: ${(subRes && subRes.error) || 'Native host未响应'}</p>`;
          }
        });
      } else {
        const diagTips = platform === "taobao"
          ? "建议：对于淘宝，推荐直接点击上方的橙色按钮 <strong>【点击淘宝【导出订单】】</strong> 导出官方 Excel！"
          : (platform === "shopee"
            ? "建议：请确认当前页面处于 Shopee 购买记录列表页（shopee.com.my/user/purchase）或订单详情页，向下滚动加载订单后再次点击提取。"
            : "建议：请确认处于拼多多订单列表页面。");
        activeTaskInfo.innerHTML = `
          <p style="color: #d97706; font-weight: bold;">未扫描到展开的订单卡片</p>
          <p style="font-size:11px;color:#6b7280;margin-top:4px;">
            诊断信息: ${frameSummaries.join(" | ") || '无框架响应'}<br>
            ${diagTips}
          </p>
        `;
      }
    });
  });

  // 5. Automated Pagination Crawler
  if (btnAutoPaging) {
    btnAutoPaging.addEventListener("click", () => {
      if (!currentActiveTab || !currentActiveTab.id) {
        activeTaskInfo.innerHTML = "<p style='color:red;'>未找到活跃标签页。</p>";
        return;
      }

      const platform = platformSelect.value;
      btnAutoPaging.disabled = true;
      btnStart.disabled = true;
      activeTaskInfo.innerHTML = "<p style='color:#0284c7;font-weight:bold;'>⏩ 正在自动连续翻页采集（最多 5 页），请保持当前网页开启...</p>";

      chrome.tabs.sendMessage(currentActiveTab.id, {
        type: "EXECUTE_COMMAND",
        command: {
          action: "AUTO_CRAWL",
          payload: { platform: platform, max_pages: 5 }
        }
      }, (response) => {
        btnAutoPaging.disabled = false;
        btnStart.disabled = false;

        if (chrome.runtime.lastError) {
          activeTaskInfo.innerHTML = `<p style="color:red;">翻页指令未响应: ${chrome.runtime.lastError.message}。请刷新当前网页（F5）后再试。</p>`;
          return;
        }

        if (response && response.success && response.result) {
          activeTaskInfo.innerHTML = `
            <p style="color: #16a34a; font-weight: bold;">🎉 自动连续翻页采集完成！</p>
            <p style="font-size:12px;color:#374151;">已连续翻阅 <strong>${response.result.pages}</strong> 页，累计抓取 <strong>${response.result.total_orders}</strong> 笔订单入库 (lab.db)！</p>
          `;
        } else {
          activeTaskInfo.innerHTML = `<p style="color:#d97706;">提示: ${(response && response.error) || '未采集到新订单，或已达尾页'}</p>`;
        }
      });
    });
  }

  refreshStatus();
  setInterval(refreshStatus, 3000);
});

/**
 * Universal extraction function executed inside each frame
 */
async function runFrameExtraction(platform) {
  function hashString(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = (hash << 5) - hash + str.charCodeAt(i);
      hash |= 0;
    }
    return hash;
  }

  try {
    if (!document || !document.body) {
      return { orders: [], note: "No body" };
    }

    const text = document.body.innerText || "";
    if (text.length < 50) {
      return { orders: [], note: "Empty body" };
    }

    const results = [];
    const seenOrderIds = new Set();

    // 1. TAOBAO extraction
    if (platform === "taobao") {
      let cards = Array.from(document.querySelectorAll(
        "table.bought-table, .bought-wrapper-mod, div[class*='bought-wrapper'], " +
        "[class*='index-mod__order-container'], [class*='orderContainer'], table[class*='bought'], div[class*='trade-item']"
      ));

      if (cards.length === 0) {
        const candidateSet = new Set();
        const allSpans = Array.from(document.querySelectorAll("span, div, p, td, b"));
        allSpans.forEach(el => {
          const t = (el.innerText || el.textContent || "").trim();
          if (t.includes("订单号") || t.includes("订单编号") || t.includes("Order ID")) {
            let curr = el;
            for (let i = 0; i < 8; i++) {
              if (!curr.parentElement || curr.parentElement === document.body) break;
              curr = curr.parentElement;
              if (
                curr.tagName === 'TABLE' ||
                curr.classList.contains("bought-table") ||
                curr.classList.contains("bought-wrapper-mod") ||
                (curr.querySelectorAll("a[href*='item'], a[href*='detail']").length > 0 &&
                 curr.querySelectorAll("tbody, tr, [class*='item']").length >= 2)
              ) {
                candidateSet.add(curr);
                break;
              }
            }
          }
        });
        cards = Array.from(candidateSet);
      }

      // Ensure every candidate card is expanded to its parent TABLE if it lacks item links
      const expandedCards = cards.map(c => {
        if (c.querySelectorAll("a[href*='item'], a[href*='detail']").length === 0) {
          const parentTable = c.closest("table, .bought-wrapper-mod, div[class*='bought-wrapper'], [class*='order-container'], div[class*='trade-item']");
          if (parentTable && parentTable.querySelectorAll("a[href*='item'], a[href*='detail']").length > 0) {
            return parentTable;
          }
          if (c.parentElement && c.parentElement.querySelectorAll("a[href*='item'], a[href*='detail']").length > 0) {
            return c.parentElement;
          }
        }
        return c;
      });

      const uniqueCards = Array.from(new Set(expandedCards));
      cards = uniqueCards.filter(c => {
        const txt = (c.innerText || c.textContent || "").trim();
        if (txt.length < 30) return false;
        return !uniqueCards.some(other => other !== c && c.contains(other));
      });

      cards.forEach(card => {
        try {
          const cardText = card.innerText || "";
          let orderId = "";

          const idMatch = cardText.match(/订单号[：:\s]*(\d{15,25})/) || cardText.match(/订单编号[：:\s]*(\d{15,25})/);
          if (idMatch) {
            orderId = idMatch[1];
          } else {
            const attrId = card.getAttribute("data-id") || card.getAttribute("data-orderid");
            if (attrId && /^\d{15,}$/.test(attrId.trim())) orderId = attrId.trim();
          }

          if (!orderId || seenOrderIds.has(orderId)) return;
          seenOrderIds.add(orderId);

          // Status
          let status = "交易成功";
          for (const s of ["交易成功", "卖家已发货", "买家已付款", "等待买家付款", "交易关闭", "退款成功"]) {
            if (cardText.includes(s)) { status = s; break; }
          }

          // Order Time
          let orderTime = "";
          const timeMatch = cardText.match(/\b(\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)\b/);
          if (timeMatch) orderTime = timeMatch[1];

          // Shop Name
          let shopName = "";
          const shopEl = card.querySelector("[class*='shop-name'], [class*='seller'], [class*='shop_name'], a[href*='shop.taobao.com'], a[href*='store.taobao.com']");
          if (shopEl) {
            shopName = (shopEl.innerText || shopEl.textContent || "").trim();
          }
          if (!shopName) {
            const shopMatch = cardText.match(/(?:店铺|掌柜|卖家)[：:\s]*([^\s\n\r]+)/);
            if (shopMatch) shopName = shopMatch[1];
          }

          // Shipping Fee
          let shippingFee = 0.0;
          const shipMatch = cardText.match(/(?:含运费|运费)[：:\s]*[¥￥]?\s*([0-9]+\.?[0-9]*)/);
          if (shipMatch) shippingFee = parseFloat(shipMatch[1]) || 0.0;

          // Total amount
          let totalAmount = 0.0;
          const priceMatches = cardText.match(/[¥￥]\s*([0-9]+\.?[0-9]*)/g);
          if (priceMatches && priceMatches.length > 0) {
            const nums = priceMatches.map(p => parseFloat(p.replace(/[^0-9.]/g, "")) || 0);
            totalAmount = Math.max(...nums);
          }

          // Items with deduplication
          const rawAnchors = Array.from(card.querySelectorAll("a[href*='item.taobao.com'], a[href*='detail.tmall.com']"));
          const itemsMap = new Map();

          if (rawAnchors.length > 0) {
            rawAnchors.forEach((a, aIdx) => {
              const href = a.href || "";
              let text = (a.innerText || "").replace(/\s+/g, " ").trim();

              // Filter out phantom recommendation / action badges
              if (/已购买\d+次|再次购买|去评价|追加评价|查看物流|申请售后|退款|投诉/.test(text)) {
                return;
              }
              if (text === "[交易快照]" || text === "交易快照") {
                return;
              }
              // Strip trailing [交易快照]
              text = text.replace(/\[交易快照\]/g, "").trim();

              const idMatch = href.match(/[?&]id=(\d+)/);
              const pId = idMatch ? idMatch[1] : `p_tb_${aIdx}`;

              let vName = "";
              let qty = 1.0;
              let unitPrice = 0.0;
              let fullRow = a.closest("tr") || a.closest("[class*='item-mod']") || a.closest("[class*='item-row']") || a.closest("[class*='bought-item']");
              if (!fullRow) {
                let curr = a.parentElement;
                for (let i = 0; i < 4; i++) {
                  if (!curr || curr === card) break;
                  if (curr.children.length >= 3 || curr.querySelectorAll("td").length >= 3) {
                    fullRow = curr;
                    break;
                  }
                  curr = curr.parentElement;
                }
              }
              if (!fullRow) fullRow = a.closest("div, li") || a.parentElement;

              if (fullRow) {
                const specEl = fullRow.querySelector("[class*='spec'], [class*='sku'], [class*='props'], [class*='item-spec']");
                if (specEl) vName = (specEl.innerText || "").trim();

                const tds = Array.from(fullRow.querySelectorAll("td"));
                if (tds.length >= 3) {
                  const tPrice = parseFloat((tds[1].innerText || "").replace(/[^0-9.]/g, "")) || 0;
                  if (tPrice > 0) unitPrice = tPrice;
                  const tCount = parseFloat((tds[2].innerText || "").replace(/[^0-9.]/g, "")) || 0;
                  if (tCount > 0) qty = tCount;
                }

                if (qty <= 1.0) {
                  const qtyEl = fullRow.querySelector("[class*='quantity'], [class*='count'], [class*='num'], [class*='number']");
                  if (qtyEl) {
                    const q = parseFloat(qtyEl.innerText.replace(/[^0-9.]/g, ""));
                    if (q > 0) qty = q;
                  }
                }
                if (unitPrice <= 0) {
                  const priceEl = fullRow.querySelector("[class*='unit-price'], [class*='price']");
                  if (priceEl) {
                    const pm = priceEl.innerText.match(/[0-9]+\.?[0-9]*/);
                    if (pm) unitPrice = parseFloat(pm[0]) || 0.0;
                  }
                }
              }

              const itemKey = `${pId}_${vName}`;
              if (!itemsMap.has(itemKey)) {
                itemsMap.set(itemKey, {
                  product_id: pId,
                  sku_id: vName ? `sku_${vName}` : "",
                  product_name: text || `Taobao Product ${pId}`,
                  variant_name: vName,
                  quantity: qty,
                  unit_price: unitPrice,
                  line_total: 0.0,
                  item_url: href.startsWith("http") ? href : `https://item.taobao.com/item.htm?id=${pId}`,
                  shop_name: shopName,
                  order_time: orderTime,
                  shipping_fee: shippingFee,
                  order_status: status
                });
              } else {
                const existing = itemsMap.get(itemKey);
                if (text && (!existing.product_name || existing.product_name.startsWith("Taobao Product"))) {
                  existing.product_name = text;
                }
                if (href && !existing.item_url) existing.item_url = href;
              }
            });
          } else {
            // Find item containers directly
            const itemNodes = Array.from(card.querySelectorAll(".item-mod, tr[class*='item'], div[class*='item-row'], div[class*='order-item']"));
            itemNodes.forEach((node, nIdx) => {
              const nameEl = node.querySelector("[class*='item-title'], [class*='title'], [class*='desc'], [class*='name']");
              const specEl = node.querySelector("[class*='item-spec'], [class*='sku'], [class*='spec'], [class*='props']");
              const qtyEl = node.querySelector("[class*='quantity'], [class*='count'], [class*='num']");
              const priceEl = node.querySelector("[class*='unit-price'], [class*='price']");
              const linkEl = node.querySelector("a");

              const pName = (nameEl ? nameEl.innerText : "").replace(/\s+/g, " ").trim() || `Taobao Item ${nIdx + 1}`;
              const vName = (specEl ? specEl.innerText : "").trim();
              const qty = qtyEl ? (parseFloat(qtyEl.innerText.replace(/[^0-9.]/g, "")) || 1.0) : 1.0;
              let unitPrice = 0.0;
              if (priceEl) {
                const pm = priceEl.innerText.match(/[0-9]+\.?[0-9]*/);
                if (pm) unitPrice = parseFloat(pm[0]) || 0.0;
              }

              let pId = `p_tb_${orderId}_${nIdx}`;
              let itemUrl = "";
              if (linkEl && linkEl.href) {
                itemUrl = linkEl.href;
                const m = itemUrl.match(/[?&]id=(\d+)/);
                if (m) pId = m[1];
              }

              itemsMap.set(`node_${nIdx}`, {
                product_id: pId,
                sku_id: vName ? `sku_${vName}` : "",
                product_name: pName,
                variant_name: vName,
                quantity: qty,
                unit_price: unitPrice,
                line_total: Math.round(unitPrice * qty * 100) / 100,
                item_url: itemUrl,
                shop_name: shopName,
                order_time: orderTime,
                shipping_fee: shippingFee,
                order_status: status
              });
            });
          }

          let items = Array.from(itemsMap.values());
          if (items.length === 0) {
            items.push({
              product_id: `p_tb_${orderId}`,
              sku_id: "",
              product_name: "Taobao Order Item",
              variant_name: "",
              quantity: 1.0,
              unit_price: totalAmount,
              line_total: totalAmount,
              item_url: "",
              shop_name: shopName,
              order_time: orderTime,
              shipping_fee: shippingFee,
              order_status: status
            });
          } else {
            items.forEach(it => {
              if (it.unit_price <= 0 && totalAmount > 0) {
                it.unit_price = Math.round((totalAmount / items.length) * 100) / 100;
              }
              it.line_total = Math.round(it.unit_price * it.quantity * 100) / 100;
            });
          }

          results.push({
            order_id: orderId,
            status: status,
            total_amount: totalAmount,
            currency: "CNY",
            shop_name: shopName,
            order_time: orderTime,
            shipping_fee: shippingFee,
            items: items
          });
        } catch (e) {}
      });

      return { orders: results, note: `Found ${results.length} Taobao orders in frame` };
    }

    // 2. SHOPEE extraction
    if (platform === "shopee") {
      // Strategy 1: Session API Direct Fetch (Runs in page context with active cookies)
      const isShopeeDomain = window.location && window.location.hostname && window.location.hostname.includes("shopee.com");
      if (isShopeeDomain && typeof fetch === "function") {
        const endpoints = [
          "/api/v4/order/get_order_list?limit=30&offset=0&list_type=3",
          "/api/v4/order/get_order_list?limit=30&offset=0&list_type=7",
          "/api/v4/order/get_order_list?limit=30&offset=0&list_type=8",
          "/api/v4/order/get_order_list?limit=30&offset=0",
          "/api/v4/order/get_order_list?limit=30&offset=0&list_type=0",
          "/api/v4/order/get_all_order_and_item_list?limit=30&offset=0"
        ];
        for (const ep of endpoints) {
          try {
            const resp = await fetch(ep, { credentials: "include" });
            if (resp.ok) {
              const body = await resp.json();
              const list = body.data?.details_list || body.data?.orders || body.details_list || [];
              if (Array.isArray(list) && list.length > 0) {
                for (const ord of list) {
                  const orderId = String(ord.order_sn || ord.order_id || ord.info_card?.order_sn || ord.info_card?.order_id || "");
                  if (!orderId || seenOrderIds.has(orderId)) continue;
                  seenOrderIds.add(orderId);

                  let totalAmount = 0.0;
                  if (ord.info_card && ord.info_card.final_total != null) {
                    totalAmount = ord.info_card.final_total / 100000;
                  } else if (ord.final_total != null) {
                    totalAmount = ord.final_total / 100000;
                  } else if (ord.total_price != null) {
                    totalAmount = ord.total_price / 100000;
                  }

                  let shippingFee = 0.0;
                  if (ord.info_card && ord.info_card.shipping_fee != null) {
                    shippingFee = ord.info_card.shipping_fee / 100000;
                  }

                  const status = ord.status_label || ord.info_card?.status_label || ord.status || "Completed";

                  let orderTime = "";
                  const cTime = ord.create_time || ord.info_card?.create_time;
                  if (cTime) {
                    const d = new Date(cTime > 1e11 ? cTime : cTime * 1000);
                    if (!isNaN(d.getTime())) {
                      orderTime = d.toISOString().replace("T", " ").substring(0, 19);
                    }
                  }

                  let shopName = "";
                  const items = [];
                  const cards = ord.info_card?.order_list_cards || ord.order_list_cards || [];
                  for (const c of cards) {
                    if (c.shop_info && c.shop_info.shop_name) {
                      shopName = c.shop_info.shop_name;
                    }
                    const groups = c.product_info?.item_groups || c.item_groups || [];
                    for (const g of groups) {
                      const rawItems = g.items || [];
                      for (const item of rawItems) {
                        const pName = item.name || item.item_name || "Shopee Item";
                        const vName = item.model_name || item.variation_name || "";
                        const qty = Number(item.amount || item.quantity || 1);
                        let uPrice = 0.0;
                        if (item.item_price != null) {
                          uPrice = item.item_price / 100000;
                        } else if (item.price != null) {
                          uPrice = item.price / 100000;
                        } else {
                          uPrice = totalAmount > 0 ? (totalAmount / qty) : 0.0;
                        }
                        const pId = String(item.item_id || item.product_id || "");
                        const shopId = String(item.shop_id || c.shop_info?.shop_id || "");
                        const itemUrl = pId ? `https://shopee.com.my/product/${shopId || '0'}/${pId}` : "";
                        const skuId = vName ? `sku_${encodeURIComponent(vName.substring(0, 30))}` : "";

                        items.push({
                          product_id: pId || `p_shopee_${orderId}_${items.length}`,
                          sku_id: skuId,
                          product_name: pName,
                          variant_name: vName,
                          quantity: qty,
                          unit_price: uPrice,
                          line_total: Math.round(uPrice * qty * 100) / 100,
                          item_url: itemUrl,
                          shop_name: shopName,
                          order_time: orderTime,
                          shipping_fee: shippingFee,
                          order_status: status
                        });
                      }
                    }
                  }

                  if (items.length === 0) {
                    items.push({
                      product_id: `p_shopee_${orderId}`,
                      sku_id: "",
                      product_name: "Shopee Purchase Item",
                      variant_name: "",
                      quantity: 1.0,
                      unit_price: totalAmount,
                      line_total: totalAmount,
                      item_url: "",
                      shop_name: shopName,
                      order_time: orderTime,
                      shipping_fee: shippingFee,
                      order_status: status
                    });
                  }

                  results.push({
                    order_id: orderId,
                    status: status,
                    total_amount: Math.round(totalAmount * 100) / 100,
                    currency: "MYR",
                    shop_name: shopName,
                    order_time: orderTime,
                    shipping_fee: shippingFee,
                    items: items
                  });
                }

                if (results.length > 0) {
                  return { orders: results, note: `Extracted ${results.length} orders via Shopee session API` };
                }
              }
            }
          } catch (e) {
            console.debug("[Shopee] API fetch attempt failed:", e.message);
          }
        }
      }

      // Strategy 2: Anchor-based & Semantic DOM Traversal
      const currentUrl = (window.location && window.location.href) || "";
      const detailUrlMatch = currentUrl.match(/\/user\/purchase\/order\/([A-Za-z0-9]+)/);
      const isDetailPage = !!detailUrlMatch;

      const candidateCards = new Set();
      const patternPrice = /RM\s*[0-9]+(?:\.[0-9]{2})?/i;
      const patternKeyword = /(?:Total|Jumlah|总额|合计|实付|Buy Again|Beli Semula|再次购买|Completed|Selesai|已完成|To Ship|Untuk Dihantar|待发货|To Receive|Untuk Diterima|待收货|Cancelled|Dibatalkan|已取消|Refund|Bayaran Balik|退款|Order|Pesanan|订单|Order SN|Order ID|Pesanan ID)/i;

      // 1. Explicit fixture/card matches
      const explicitCards = Array.from(document.querySelectorAll(
        ".purchase-list-page__order-card, .order-card, div[class*='order-card']"
      ));
      explicitCards.forEach(c => {
        const txt = c.textContent || "";
        if (txt.length >= 25 && patternPrice.test(txt)) candidateCards.add(c);
      });

      // 2. Universal Topological Leaf Card Search
      if (candidateCards.size === 0) {
        const elements = Array.from(document.querySelectorAll("div, section, article, li, tbody"));
        for (const el of elements) {
          const txt = el.textContent || "";
          if (txt.length >= 35 && txt.length <= 6000 && patternPrice.test(txt) && patternKeyword.test(txt)) {
            if (el.querySelector("img, a[href*='product'], a[href*='-i.'], a[href*='order'], a[href*='purchase']") || /x\s*\d+/i.test(txt)) {
              candidateCards.add(el);
            }
          }
        }
      }

      // 3. Anchor-based ascent from links
      if (candidateCards.size === 0) {
        const productAnchors = Array.from(document.querySelectorAll(
          "a[href*='/product/'], a[href*='-i.'], a[href*='/order/'], a[href*='purchase'], a[href*='/item/']"
        ));
        for (const a of productAnchors) {
          let curr = a;
          for (let i = 0; i < 16; i++) {
            if (!curr.parentElement || curr.parentElement === document.body) break;
            curr = curr.parentElement;
            const txt = curr.textContent || "";
            if (patternPrice.test(txt) && patternKeyword.test(txt)) {
              candidateCards.add(curr);
              break;
            }
          }
        }
      }

      // Filter out outer containers that contain other candidate cards
      let cards = Array.from(candidateCards);
      cards = cards.filter(c => !cards.some(other => other !== c && c.contains(other)));

      if (cards.length === 0 && isDetailPage) {
        cards = [document.body];
      }

      cards.forEach((card, cIdx) => {
        try {
          const cardText = card.textContent || "";

          // 1. Order ID
          let orderId = "";
          if (isDetailPage && detailUrlMatch) {
            orderId = detailUrlMatch[1];
          }

          if (!orderId) {
            const detailLink = card.querySelector("a[href*='/order/']");
            if (detailLink) {
              const lm = detailLink.href.match(/\/order\/([A-Za-z0-9]+)/);
              if (lm) orderId = lm[1];
            }
          }

          if (!orderId) {
            const idEl = card.querySelector("[class*='order-sn'], [class*='ordersn'], [class*='order-id'], [class*='orderId'], [class*='order-number']");
            if (idEl) {
              const m = idEl.textContent.trim().match(/[A-Za-z0-9]{8,35}/);
              if (m) orderId = m[0];
            }
          }

          if (!orderId) {
            const idMatch = cardText.match(/(?:Order\s*(?:SN|ID|No\.?)|订单编号)[：:\s]*([A-Za-z0-9]{8,35})/i);
            if (idMatch) orderId = idMatch[1];
          }

          if (!orderId) {
            const header = card.querySelector(".order-header, [class*='header']");
            if (header) {
              const hm = (header.textContent || "").match(/[A-Za-z0-9]{10,35}/);
              if (hm) orderId = hm[0];
            }
          }

          if (!orderId) {
            const dataId = card.getAttribute("data-order-id") || card.getAttribute("data-id") || card.getAttribute("data-sn");
            if (dataId) orderId = dataId.trim();
          }

          // Fallback deterministic ID
          if (!orderId) {
            const firstLink = card.querySelector("a[href*='/product/'], a[href*='-i.']");
            let seed = "";
            if (firstLink && firstLink.href) {
              const m = firstLink.href.match(/product\/(\d+)\/(\d+)|-i\.(\d+)\.(\d+)/);
              if (m) seed = m[2] || m[1] || m[4] || m[3];
            }
            if (!seed) {
              seed = String(Math.abs(hashString(cardText.substring(0, 100)))).substring(0, 8);
            }
            orderId = `SP_${cIdx + 1}_${seed}`;
          }

          if (seenOrderIds.has(orderId)) return;
          seenOrderIds.add(orderId);

          // 2. Status
          let status = "Completed";
          const statusEl = card.querySelector("[class*='order-status'], [class*='status-text'], [class*='status-label'], [class*='status'], [class*='order-state']");
          if (statusEl) {
            status = statusEl.textContent.trim();
          } else {
            const statusCandidates = [
              "Completed", "To Ship", "To Receive", "To Pay", "Cancelled", "Refund Completed", "Return Refund",
              "已完成", "待发货", "运输中", "待付款", "已取消", "退款成功", "退货/退款"
            ];
            for (const sc of statusCandidates) {
              if (cardText.includes(sc)) {
                status = sc;
                break;
              }
            }
          }

          // 3. Shop Name
          let shopName = "";
          const shopEl = card.querySelector("[class*='shop-name'], [class*='seller-name'], [class*='shop-header'], [class*='seller'], a[href*='/shop/'], a[href*='shopee.com.my/shop']");
          if (shopEl) {
            shopName = shopEl.textContent.trim().replace(/^(Visit\s*Shop|Chat\s*Now|进店|聊天)\s*/i, "").trim();
          }
          if (!shopName) {
            const sm = cardText.match(/(?:Shop|Seller|店铺|掌柜|卖家)[：:\s]*([^\n\r\t]+)/i);
            if (sm) shopName = sm[1].trim();
          }

          // 4. Order Time
          let orderTime = "";
          const timeMatch = cardText.match(/\b(\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)\b/);
          if (timeMatch) {
            orderTime = timeMatch[1];
          } else {
            const timeMatch2 = cardText.match(/\b(\d{2}[/-]\d{2}[/-]\d{4}(?:\s+\d{2}:\d{2})?)\b/);
            if (timeMatch2) orderTime = timeMatch2[1];
          }

          // 5. Shipping Fee
          let shippingFee = 0.0;
          const shipMatch = cardText.match(/(?:Shipping\s*(?:Fee|Total)?|运费)[：:\s]*RM\s*([0-9]+\.?[0-9]*)/i);
          if (shipMatch) shippingFee = parseFloat(shipMatch[1]) || 0.0;

          // 6. Order Total
          let totalAmount = 0.0;
          const totalEl = card.querySelector("[class*='order-total'], [class*='total-price'], [class*='purchase-card__total'], [class*='totalPrice'], [class*='total']");
          if (totalEl) {
            const tm = totalEl.textContent.match(/RM\s*([0-9]+\.?[0-9]*)/i) || totalEl.textContent.match(/([0-9]+\.?[0-9]*)/);
            if (tm) totalAmount = parseFloat(tm[1]) || 0.0;
          }
          if (totalAmount <= 0) {
            const tmRegex = cardText.match(/(?:Order\s*Total|Total\s*Price|Total\s*Payment|Total|订单总额|实付金额|合计)[：:\s]*RM\s*([0-9]+\.?[0-9]*)/i);
            if (tmRegex) totalAmount = parseFloat(tmRegex[1]) || 0.0;
          }
          if (totalAmount <= 0) {
            const footer = card.querySelector(".order-footer, [class*='footer']");
            if (footer) {
              const fm = (footer.textContent || "").match(/RM\s*([0-9]+\.?[0-9]*)/i);
              if (fm) totalAmount = parseFloat(fm[1]) || 0.0;
            }
          }

          // 7. Items
          let itemNodes = Array.from(card.querySelectorAll(
            ".order-item, .product-item, div[class*='order-item'], div[class*='product-item'], " +
            "div[class*='purchase-card__item'], div[class*='order-content__item'], div[class*='item-card'], div[class*='item-row']"
          ));

          if (itemNodes.length === 0) {
            const links = Array.from(card.querySelectorAll("a[href*='/product/'], a[href*='-i.']"));
            const parentSet = new Set();
            for (const l of links) {
              let cParent = l;
              for (let i = 0; i < 4; i++) {
                if (!cParent.parentElement || cParent.parentElement === card) break;
                cParent = cParent.parentElement;
                if (cParent.textContent.length > 10) {
                  parentSet.add(cParent);
                  break;
                }
              }
            }
            itemNodes = Array.from(parentSet);
          }

          const items = [];
          const seenItemKeys = new Set();

          itemNodes.forEach((node, nIdx) => {
            const nameEl = node.querySelector("[class*='item-name'], [class*='product-name'], [class*='product-title'], [class*='title'], [class*='name']");
            const specEl = node.querySelector("[class*='variation'], [class*='model'], [class*='spec'], [class*='item-variation'], [class*='variant']");
            const qtyEl = node.querySelector("[class*='quantity'], [class*='item-quantity'], [class*='qty'], [class*='count']");
            const priceEl = node.querySelector("[class*='item-price'], [class*='price'], [class*='unit-price']");
            const linkEl = node.querySelector("a[href*='/product/'], a[href*='-i.'], a[href*='/item/']") || node.querySelector("a");

            let pName = nameEl ? nameEl.textContent.trim().replace(/\s+/g, " ") : "";
            if (!pName && linkEl) {
              pName = linkEl.textContent.trim().replace(/\s+/g, " ");
            }
            if (!pName) pName = `Shopee Item ${nIdx + 1}`;

            let vName = specEl ? specEl.textContent.trim().replace(/^(Variation|Model|Type|规格|型号|Package|Color)[：:\s]*/i, "").trim() : "";

            let qty = 1.0;
            if (qtyEl) {
              const qm = qtyEl.textContent.match(/x\s*([0-9]+(?:\.[0-9]+)?)/i) || qtyEl.textContent.match(/([0-9]+(?:\.[0-9]+)?)/);
              if (qm) qty = parseFloat(qm[1]) || 1.0;
            }

            let unitPrice = 0.0;
            if (priceEl) {
              const pm = priceEl.textContent.match(/RM\s*([0-9]+\.?[0-9]*)/i) || priceEl.textContent.match(/([0-9]+\.?[0-9]*)/);
              if (pm) unitPrice = parseFloat(pm[1]) || 0.0;
            }

            let pId = "";
            let itemUrl = "";
            if (linkEl && linkEl.href) {
              const href = linkEl.href;
              itemUrl = href.startsWith("http") ? href : `https://shopee.com.my${href}`;
              const idMatch = href.match(/\/product\/(\d+)\/(\d+)/) || href.match(/-i\.(\d+)\.(\d+)/) || href.match(/[?&]item_id=(\d+)/);
              if (idMatch) {
                pId = idMatch[2] || idMatch[1];
              }
            }
            if (!pId) {
              pId = `p_shopee_${orderId}_${nIdx}`;
            }

            const skuId = vName ? `sku_${encodeURIComponent(vName.substring(0, 30))}` : "";
            const itemKey = `${pId}_${vName}`;
            if (seenItemKeys.has(itemKey)) return;
            seenItemKeys.add(itemKey);

            items.push({
              product_id: pId,
              sku_id: skuId,
              product_name: pName,
              variant_name: vName,
              quantity: qty,
              unit_price: unitPrice,
              line_total: Math.round(unitPrice * qty * 100) / 100,
              item_url: itemUrl,
              shop_name: shopName,
              order_time: orderTime,
              shipping_fee: shippingFee,
              order_status: status
            });
          });

          // Price calculation if missing
          if (items.length > 0) {
            const totalItemsQty = items.reduce((sum, it) => sum + (it.quantity || 1), 0);
            items.forEach(it => {
              if (it.unit_price <= 0 && totalAmount > 0) {
                if (items.length === 1) {
                  it.unit_price = Math.round((totalAmount / it.quantity) * 100) / 100;
                } else {
                  it.unit_price = Math.round((totalAmount / (totalItemsQty || items.length)) * 100) / 100;
                }
              }
              it.line_total = Math.round(it.unit_price * it.quantity * 100) / 100;
            });
          } else {
            items.push({
              product_id: `p_shopee_${orderId}`,
              sku_id: "",
              product_name: "Shopee Purchase Item",
              variant_name: "",
              quantity: 1.0,
              unit_price: totalAmount,
              line_total: totalAmount,
              item_url: "",
              shop_name: shopName,
              order_time: orderTime,
              shipping_fee: shippingFee,
              order_status: status
            });
          }

          results.push({
            order_id: orderId,
            status: status,
            total_amount: totalAmount,
            currency: "MYR",
            shop_name: shopName,
            order_time: orderTime,
            shipping_fee: shippingFee,
            items: items
          });
        } catch (e) {}
      });
      return { orders: results, note: `Found ${results.length} Shopee orders via DOM parser` };
    }

    // 3. PDD extraction
    if (platform === "pdd") {
      const currentUrl = (window.location && window.location.href) || "";
      const isDetailPage = currentUrl.includes("/order.html") || currentUrl.includes("order_sn=");
      const detailUrlMatch = currentUrl.match(/[?&]order_sn=([0-9\-]+)/) || currentUrl.match(/\/order\/([0-9\-]+)/);

      let cards = Array.from(document.querySelectorAll(
        ".order-item-card, .order-card, div[class*='order-item'], div[class*='order_card'], " +
        "div[class*='OrderItem'], div[class*='pdd-order'], div[class*='order-item-module'], div[role='listitem']"
      ));

      if (cards.length === 0) {
        const candidateSet = new Set();
        const allTextEls = document.querySelectorAll("span, div, p, a");
        for (const el of allTextEls) {
          const txt = el.textContent || "";
          if (
            (txt.includes("订单编号") || txt.includes("订单号") || txt.includes("order_sn")) &&
            /[0-9\-]{10,}/.test(txt)
          ) {
            let curr = el;
            for (let i = 0; i < 6; i++) {
              if (!curr.parentElement || curr.parentElement === document.body) break;
              curr = curr.parentElement;
              if (
                curr.querySelector("[class*='goods-name'], [class*='goods-info'], [class*='goods-item'], a[href*='goods_id']") ||
                curr.querySelector("[class*='order-amount'], [class*='total-price'], [class*='price']")
              ) {
                candidateSet.add(curr);
                break;
              }
            }
          }
        }
        cards = Array.from(candidateSet);
      }

      if (cards.length === 0 && isDetailPage) {
        cards = [document.body];
      }

      cards.forEach(card => {
        try {
          const cardText = card.textContent || "";

          // 1. Order ID
          let orderId = "";
          if (isDetailPage && detailUrlMatch) {
            orderId = detailUrlMatch[1].replace(/-/g, "");
          }

          if (!orderId) {
            const idEl = card.querySelector("[class*='order-sn'], [class*='orderSn'], [class*='order-id'], [class*='orderId'], [class*='sn']");
            if (idEl) {
              const raw = (idEl.textContent || "").trim();
              const m = raw.match(/[0-9\-]{10,35}/);
              if (m) orderId = m[0].replace(/-/g, "");
            }
          }

          if (!orderId) {
            const detailLink = card.querySelector("a[href*='order_sn=']");
            if (detailLink) {
              const lm = detailLink.href.match(/order_sn=([0-9\-]+)/);
              if (lm) orderId = lm[1].replace(/-/g, "");
            }
          }

          if (!orderId) {
            const idMatch = cardText.match(/(?:订单编号|订单号|order_sn)[：:\s]*([0-9\-]{10,35})/i);
            if (idMatch) orderId = idMatch[1].replace(/-/g, "");
          }

          if (!orderId || seenOrderIds.has(orderId)) return;
          seenOrderIds.add(orderId);

          // 2. Status
          let status = "拼单成功";
          const statusEl = card.querySelector("[class*='order-status'], [class*='order-state'], [class*='status-text'], [class*='status'], [class*='state']");
          if (statusEl) {
            status = (statusEl.textContent || "").trim();
          } else {
            const candidates = [
              "拼单成功", "已签收", "待发货", "已发货", "运输中", "待收货",
              "交易成功", "退款成功", "拼单中", "待付款", "交易关闭", "退款中"
            ];
            for (const cand of candidates) {
              if (cardText.includes(cand)) {
                status = cand;
                break;
              }
            }
          }

          // 3. Shop name
          let shopName = "";
          const shopEl = card.querySelector("[class*='mall-name'], [class*='mall_name'], [class*='shop-name'], [class*='shop'], [class*='merchant'], [class*='seller'], a[href*='mall_id']");
          if (shopEl) {
            shopName = (shopEl.textContent || "").trim().replace(/^(进店\s*[>》]?|商家[：:]\s*|店铺[：:]\s*)/, "").trim();
          }
          if (!shopName) {
            const sm = cardText.match(/(?:店铺|商家|掌柜)[：:\s]*([^\n\r\t]+)/i);
            if (sm) shopName = sm[1].trim();
          }

          // 4. Order time
          let orderTime = "";
          const timeMatch = cardText.match(/\b(\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)\b/);
          if (timeMatch) orderTime = timeMatch[1];

          // 5. Shipping fee
          let shippingFee = 0.0;
          const shipMatch = cardText.match(/(?:含运费|运费)[：:\s]*[¥￥]?\s*([0-9]+\.?[0-9]*)/i);
          if (shipMatch) shippingFee = parseFloat(shipMatch[1]) || 0.0;

          // 6. Total amount
          let totalAmount = 0.0;
          const totalEl = card.querySelector("[class*='order-amount'], [class*='total-price'], [class*='pay-amount'], [class*='real-price']");
          if (totalEl) {
            const tm = totalEl.textContent.match(/[¥￥]?\s*([0-9]+\.?[0-9]*)/);
            if (tm) totalAmount = parseFloat(tm[1]) || 0.0;
          }
          if (totalAmount <= 0) {
            const tmRegex = cardText.match(/(?:实付金额|实付款|实付|合计|订单总额)[：:\s]*[¥￥]?\s*([0-9]+\.?[0-9]*)/i);
            if (tmRegex) totalAmount = parseFloat(tmRegex[1]) || 0.0;
          }

          // 7. Items (Multi-line support)
          let itemNodes = Array.from(card.querySelectorAll(
            ".goods-info, .goods-item, .order-item, div[class*='goods-info'], div[class*='goods-item'], " +
            "div[class*='order-item'], div[class*='product-item']"
          ));

          if (itemNodes.length === 0) {
            const links = Array.from(card.querySelectorAll("a[href*='goods_id']"));
            const parentSet = new Set();
            for (const l of links) {
              let curr = l;
              for (let i = 0; i < 4; i++) {
                if (!curr.parentElement || curr.parentElement === card) break;
                curr = curr.parentElement;
                if (curr.textContent.length > 10) {
                  parentSet.add(curr);
                  break;
                }
              }
            }
            itemNodes = Array.from(parentSet);
          }

          if (itemNodes.length === 0) {
            itemNodes = [card];
          }

          const items = [];
          const seenItemKeys = new Set();

          itemNodes.forEach((node, nIdx) => {
            const nameEl = node.querySelector("[class*='goods-name'], [class*='goods-title'], [class*='title'], [class*='product-name'], [class*='name']");
            const specEl = node.querySelector("[class*='spec'], [class*='sku'], [class*='sku-desc'], [class*='props']");
            const qtyEl = node.querySelector("[class*='goods-number'], [class*='quantity'], [class*='count'], [class*='qty'], [class*='num']");
            const priceEl = node.querySelector("[class*='goods-price'], [class*='unit-price'], [class*='price']");
            const linkEl = node.querySelector("a[href*='goods_id']") || node.querySelector("a");

            let pName = nameEl ? (nameEl.textContent || "").trim().replace(/\s+/g, " ") : "";
            if (!pName && linkEl) {
              pName = (linkEl.textContent || "").trim().replace(/\s+/g, " ");
            }
            if (!pName) pName = `Pinduoduo Item ${nIdx + 1}`;
            pName = pName.replace(/^[【\[](?:拼单返现|正品保障|退货包运费)[】\]]\s*/, "").trim();

            let vName = specEl ? (specEl.textContent || "").trim().replace(/^(配置|规格|型号|已选)[：:\s]*/i, "").trim() : "";

            let qty = 1.0;
            if (qtyEl) {
              const qText = qtyEl.textContent || "";
              const qm = qText.match(/(\d+(?:\.\d+)?)\s*件/i) || qText.match(/x\s*([0-9]+(?:\.[0-9]+)?)/i) || qText.match(/([0-9]+(?:\.[0-9]+)?)/);
              if (qm) qty = parseFloat(qm[1]) || 1.0;
            }

            let unitPrice = 0.0;
            if (priceEl) {
              const pm = priceEl.textContent.match(/[¥￥]?\s*([0-9]+\.?[0-9]*)/);
              if (pm) unitPrice = parseFloat(pm[1]) || 0.0;
            }

            let pId = "";
            let itemUrl = "";
            if (linkEl && linkEl.href) {
              const href = linkEl.href;
              itemUrl = href.startsWith("http") ? href : `https://mobile.yangkeduo.com${href}`;
              const idMatch = href.match(/[?&]goods_id=(\d+)/) || href.match(/\/goods\/(\d+)/);
              if (idMatch) pId = idMatch[1];
            }
            if (!pId) pId = `p_pdd_${orderId}_${nIdx}`;

            const skuId = vName ? `sku_pdd_${encodeURIComponent(vName.substring(0, 30))}` : "";
            const itemKey = `${pId}_${vName}`;
            if (seenItemKeys.has(itemKey)) return;
            seenItemKeys.add(itemKey);

            items.push({
              product_id: pId,
              sku_id: skuId,
              product_name: pName,
              variant_name: vName,
              quantity: qty,
              unit_price: unitPrice,
              line_total: Math.round(unitPrice * qty * 100) / 100,
              item_url: itemUrl,
              shop_name: shopName,
              order_time: orderTime,
              shipping_fee: shippingFee,
              order_status: status
            });
          });

          // Price calculation & line total adjustment
          if (items.length > 0) {
            const totalItemsQty = items.reduce((sum, it) => sum + (it.quantity || 1), 0);
            items.forEach(it => {
              if (it.unit_price <= 0 && totalAmount > 0) {
                if (items.length === 1) {
                  it.unit_price = Math.round((totalAmount / it.quantity) * 100) / 100;
                } else {
                  it.unit_price = Math.round((totalAmount / (totalItemsQty || items.length)) * 100) / 100;
                }
              } else if (items.length === 1 && it.quantity > 1 && Math.abs(it.unit_price - totalAmount) < 0.01) {
                it.unit_price = Math.round((totalAmount / it.quantity) * 100) / 100;
              }
              it.line_total = Math.round(it.unit_price * it.quantity * 100) / 100;
            });
          } else {
            items.push({
              product_id: `p_pdd_${orderId}`,
              sku_id: "",
              product_name: "Pinduoduo Purchase Item",
              variant_name: "",
              quantity: 1.0,
              unit_price: totalAmount,
              line_total: totalAmount,
              item_url: "",
              shop_name: shopName,
              order_time: orderTime,
              shipping_fee: shippingFee,
              order_status: status
            });
          }

          results.push({
            order_id: orderId,
            status: status,
            total_amount: totalAmount,
            currency: "CNY",
            shop_name: shopName,
            order_time: orderTime,
            shipping_fee: shippingFee,
            items: items
          });
        } catch (e) {}
      });
      return { orders: results, note: `Found ${results.length} PDD orders in frame` };
    }

    return { orders: [], note: "Unknown platform" };
  } catch (err) {
    return { orders: [], note: `Frame error: ${err.message}` };
  }
}
