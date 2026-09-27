document.addEventListener("DOMContentLoaded", () => {
  const hostStatusBadge = document.getElementById("hostStatusBadge");
  const activeTabStatus = document.getElementById("activeTabStatus");
  const activeTaskInfo = document.getElementById("activeTaskInfo");
  const btnStart = document.getElementById("btnStart");
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
        activeTaskInfo.innerHTML = `
          <p style="color: #d97706; font-weight: bold;">未扫描到展开的订单卡片</p>
          <p style="font-size:11px;color:#6b7280;margin-top:4px;">
            诊断信息: ${frameSummaries.join(" | ") || '无框架响应'}<br>
            建议：对于淘宝，推荐直接点击上方的橙色按钮 <strong>【点击淘宝【导出订单】】</strong> 导出官方 Excel！
          </p>
        `;
      }
    });
  });

  refreshStatus();
  setInterval(refreshStatus, 3000);
});

/**
 * Universal extraction function executed inside each frame
 */
function runFrameExtraction(platform) {
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
      // Find candidate containers:
      // A. Known class containers
      let cards = Array.from(document.querySelectorAll(
        ".bought-wrapper-mod, div[class*='bought-wrapper'], tbody[class*='order-body'], " +
        "[class*='index-mod__order-container'], [class*='orderContainer'], table.bought-table, " +
        "div[data-id], div[class*='bought-item'], div[class*='trade-item']"
      ));

      // B. If not found by classes, find by text nodes containing "订单号" or "订单编号"
      if (cards.length === 0) {
        const candidateSet = new Set();
        const allSpans = Array.from(document.querySelectorAll("span, div, p, td"));
        allSpans.forEach(el => {
          const t = el.innerText || "";
          if (t.includes("订单号") || t.includes("订单编号")) {
            // Find parent container
            let curr = el;
            for (let i = 0; i < 6; i++) {
              if (!curr.parentElement || curr.parentElement === document.body) break;
              curr = curr.parentElement;
              if (curr.querySelectorAll("a[href*='item'], a[href*='detail']").length > 0 || curr.tagName === 'TABLE' || curr.tagName === 'TBODY') {
                candidateSet.add(curr);
                break;
              }
            }
          }
        });
        cards = Array.from(candidateSet);
      }

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

          // Total amount
          let totalAmount = 0.0;
          const priceMatches = cardText.match(/[¥￥]\s*([0-9]+\.?[0-9]*)/g);
          if (priceMatches && priceMatches.length > 0) {
            const nums = priceMatches.map(p => parseFloat(p.replace(/[^0-9.]/g, "")) || 0);
            totalAmount = Math.max(...nums);
          }

          // Items
          const anchors = Array.from(card.querySelectorAll("a[href*='item.taobao.com'], a[href*='detail.tmall.com']"));
          const items = [];

          if (anchors.length > 0) {
            anchors.forEach((a, aIdx) => {
              const pName = (a.innerText || "").replace(/\s+/g, " ").trim() || `Taobao Product ${aIdx + 1}`;
              const pUrl = a.href || "";
              const idMatch = pUrl.match(/[?&]id=(\d+)/);
              const pId = idMatch ? idMatch[1] : `p_tb_${aIdx}`;

              // Look for spec near anchor
              let vName = "";
              const parentRow = a.closest("tr, div, li") || a.parentElement;
              if (parentRow) {
                const specEl = parentRow.querySelector("[class*='spec'], [class*='sku'], [class*='props']");
                if (specEl) vName = (specEl.innerText || "").trim();
              }

              items.push({
                product_id: pId,
                sku_id: vName ? `sku_${vName}` : "",
                product_name: pName,
                variant_name: vName,
                quantity: 1.0,
                unit_price: totalAmount > 0 ? (totalAmount / anchors.length) : 0.0,
                line_total: totalAmount > 0 ? (totalAmount / anchors.length) : 0.0
              });
            });
          } else {
            items.push({
              product_id: `p_tb_${orderId}`,
              sku_id: "",
              product_name: "Taobao Order Item",
              variant_name: "",
              quantity: 1.0,
              unit_price: totalAmount,
              line_total: totalAmount
            });
          }

          results.push({
            order_id: orderId,
            status: status,
            total_amount: totalAmount,
            currency: "CNY",
            items: items
          });
        } catch (e) {}
      });

      return { orders: results, note: `Found ${results.length} Taobao orders in frame` };
    }

    // 2. SHOPEE extraction
    if (platform === "shopee") {
      const cards = Array.from(document.querySelectorAll(".purchase-list-page__order-card, .order-card, [class*='order-card']"));
      cards.forEach(card => {
        try {
          let orderId = "";
          const t = card.innerText || "";
          const m = t.match(/[A-Z0-9]{12,}/);
          if (m) orderId = m[0];
          if (!orderId || seenOrderIds.has(orderId)) return;
          seenOrderIds.add(orderId);

          let total = 0.0;
          const pMatch = t.match(/RM\s*([0-9]+\.?[0-9]*)/i);
          if (pMatch) total = parseFloat(pMatch[1]) || 0.0;

          results.push({
            order_id: orderId,
            status: "Completed",
            total_amount: total,
            currency: "MYR",
            items: [{
              product_id: `p_shopee_${orderId}`,
              sku_id: "",
              product_name: "Shopee Purchase Item",
              variant_name: "",
              quantity: 1.0,
              unit_price: total,
              line_total: total
            }]
          });
        } catch (e) {}
      });
      return { orders: results, note: `Found ${results.length} Shopee orders in frame` };
    }

    // 3. PDD extraction
    if (platform === "pdd") {
      const cards = Array.from(document.querySelectorAll(".order-item-card, .order-card, div[class*='order-item'], div[class*='order_card']"));
      cards.forEach(card => {
        try {
          const t = card.innerText || "";
          const m = t.match(/[0-9\-]{10,}/);
          const orderId = m ? m[0].replace(/-/g, "") : "";
          if (!orderId || seenOrderIds.has(orderId)) return;
          seenOrderIds.add(orderId);

          let total = 0.0;
          const pMatch = t.match(/[¥￥]\s*([0-9]+\.?[0-9]*)/);
          if (pMatch) total = parseFloat(pMatch[1]) || 0.0;

          results.push({
            order_id: orderId,
            status: "拼单成功",
            total_amount: total,
            currency: "CNY",
            items: [{
              product_id: `p_pdd_${orderId}`,
              sku_id: "",
              product_name: "Pinduoduo Purchase Item",
              variant_name: "",
              quantity: 1.0,
              unit_price: total,
              line_total: total
            }]
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
