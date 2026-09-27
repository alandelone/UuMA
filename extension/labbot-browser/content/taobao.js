/**
 * Taobao Order Extraction Content Script Adapter
 * Supports standard Taobao buyer trade lists, React/Vue dynamic cards, and export button triggers.
 */

(function () {
  const core = window.UuMAExtractionCore;

  const TaobaoAdapter = {
    isPaused: false,

    pause() {
      this.isPaused = true;
    },

    resume() {
      this.isPaused = false;
    },

    findExportButton() {
      const candidates = Array.from(document.querySelectorAll("button, a, span, div"));
      for (const el of candidates) {
        const txt = (el.textContent || "").trim();
        if (txt.includes("导出订单") && el.children.length <= 3) {
          return el;
        }
      }
      return null;
    },

    clickExportButton() {
      const btn = this.findExportButton();
      if (!btn) {
        return { success: false, error: "未在当前页面找到【导出订单】按钮，请确认处于已买到的宝贝页面。" };
      }
      btn.click();
      return {
        success: true,
        message: "已点击淘宝【导出订单】按钮！请在页面弹窗中确认导出时间范围并下载 Excel 表格。"
      };
    },

    findOrderRoots() {
      // 1. Selector search
      const selectorMatches = Array.from(document.querySelectorAll(
        ".bought-wrapper-mod, div[class*='bought-wrapper'], tbody[class*='order-body'], " +
        "[class*='index-mod__order-container'], [class*='orderContainer'], div[data-id], " +
        "table.bought-table, tr[class*='order-item'], [class*='bought-item'], [class*='trade-item'], " +
        "div[class*='item-list'] > div, #tp-bought-root > div > div"
      ));

      if (selectorMatches.length > 0) {
        // Filter out tiny containers or full wrapper
        const valid = selectorMatches.filter(el => {
          const txt = el.textContent || "";
          return txt.length > 30 && (txt.includes("订单号") || txt.includes("订单编号") || /\d{15,}/.test(txt) || el.querySelector("a[href*='item'], a[href*='detail']"));
        });
        if (valid.length > 0) return valid;
      }

      // 2. Semantic Text Search: Find elements containing "订单号" or "订单编号"
      const candidateRoots = new Set();
      const allTextContainers = document.querySelectorAll("span, div, p, td, th, li");
      for (const el of allTextContainers) {
        const txt = el.textContent || "";
        if ((txt.includes("订单号") || txt.includes("订单编号")) && /\d{15,}/.test(txt)) {
          let curr = el;
          let container = el;
          for (let i = 0; i < 6; i++) {
            if (!curr.parentElement || curr.parentElement === document.body) break;
            curr = curr.parentElement;
            if (
              curr.tagName === "TABLE" ||
              curr.tagName === "TBODY" ||
              curr.getAttribute("data-id") ||
              (curr.className && typeof curr.className === "string" && (
                curr.className.includes("container") ||
                curr.className.includes("wrapper") ||
                curr.className.includes("mod") ||
                curr.className.includes("card")
              ))
            ) {
              container = curr;
              break;
            }
            if (curr.children.length > 1 && curr.querySelectorAll("a[href*='item'], a[href*='detail']").length > 0) {
              container = curr;
              break;
            }
          }
          candidateRoots.add(container);
        }
      }

      if (candidateRoots.size > 0) {
        return Array.from(candidateRoots);
      }

      // 3. Anchor Search: Find product item links
      const itemLinks = Array.from(document.querySelectorAll("a[href*='item.taobao.com'], a[href*='detail.tmall.com']"));
      for (const link of itemLinks) {
        let curr = link;
        for (let i = 0; i < 7; i++) {
          if (!curr.parentElement || curr.parentElement === document.body) break;
          curr = curr.parentElement;
          if (curr.textContent && (curr.textContent.includes("订单号") || /\d{15,}/.test(curr.textContent))) {
            candidateRoots.add(curr);
            break;
          }
        }
      }

      return Array.from(candidateRoots);
    },

    parseOrdersOnPage() {
      const orderRoots = this.findOrderRoots();
      console.log(`[TaobaoAdapter] Scanning page: found ${orderRoots.length} candidate order containers.`);

      const results = [];
      const seenOrderIds = new Set();

      orderRoots.forEach((card, idx) => {
        try {
          let orderId = "";
          // 1. Order ID from data-id or text
          const attrId = card.getAttribute("data-id") || card.getAttribute("data-orderid");
          if (attrId && /^\d{15,}$/.test(attrId.trim())) {
            orderId = attrId.trim();
          }

          if (!orderId) {
            const cardText = card.textContent || "";
            const match = cardText.match(/订单号[：:\s]*(\d{15,25})/) || cardText.match(/订单编号[：:\s]*(\d{15,25})/);
            if (match) {
              orderId = match[1];
            } else {
              const digitsMatch = cardText.match(/\b\d{16,22}\b/);
              if (digitsMatch) orderId = digitsMatch[0];
            }
          }

          if (!orderId || seenOrderIds.has(orderId)) return;
          seenOrderIds.add(orderId);

          // 2. Status
          let status = "交易成功";
          const statusElem = card.querySelector("[class*='order-status'], [class*='status'], [class*='trade-status'], [class*='state']");
          if (statusElem) {
            status = core.cleanText(statusElem);
          } else {
            const cardText = card.textContent || "";
            for (const s of ["交易成功", "卖家已发货", "买家已付款", "等待买家付款", "交易关闭", "退款成功"]) {
              if (cardText.includes(s)) {
                status = s;
                break;
              }
            }
          }

          // 3. Total amount
          let totalAmount = 0.0;
          const totalElem = card.querySelector("[class*='real-price'], [class*='total-price'], [class*='realprice'], [class*='amount'], [class*='actual-price']");
          if (totalElem) {
            totalAmount = core.parsePrice(core.cleanText(totalElem));
          } else {
            // Find ¥ symbols in the card
            const priceMatches = (card.textContent || "").match(/[¥￥]\s*([0-9]+\.?[0-9]*)/g);
            if (priceMatches && priceMatches.length > 0) {
              // Usually the last or largest price is the total
              const numbers = priceMatches.map(p => core.parsePrice(p));
              totalAmount = Math.max(...numbers);
            }
          }

          // 4. Items
          let itemRows = Array.from(card.querySelectorAll(".item-mod, tr[class*='item'], div[class*='item-row'], div[class*='order-item']"));
          if (itemRows.length === 0) {
            // Try finding anchors pointing to products
            const anchors = Array.from(card.querySelectorAll("a[href*='item.taobao.com'], a[href*='detail.tmall.com']"));
            if (anchors.length > 0) {
              itemRows = anchors.map(a => a.closest("tr, div, li") || a.parentElement);
            } else {
              itemRows = [card];
            }
          }

          // De-duplicate item rows
          itemRows = Array.from(new Set(itemRows));

          const items = [];
          itemRows.forEach((itemEl, itemIdx) => {
            const nameElem = itemEl.querySelector("[class*='item-title'], [class*='title'], [class*='desc'], [class*='name'], a[href*='item'], a[href*='detail']");
            const specElem = itemEl.querySelector("[class*='item-spec'], [class*='sku'], [class*='spec'], [class*='props'], [class*='sku-desc']");
            const qtyElem = itemEl.querySelector("[class*='quantity'], [class*='count'], [class*='num']");
            const priceElem = itemEl.querySelector("[class*='unit-price'], [class*='price']");
            const linkElem = itemEl.querySelector("a[href*='item.taobao.com'], a[href*='detail.tmall.com']") || itemEl.closest("a");

            let productId = "";
            if (linkElem && linkElem.href) {
              const pMatch = linkElem.href.match(/[?&]id=(\d+)/);
              if (pMatch) productId = pMatch[1];
            }

            const productName = nameElem ? core.cleanText(nameElem) : `Taobao Product ${itemIdx + 1}`;
            const variantName = specElem ? core.cleanText(specElem) : "";
            const qty = qtyElem ? (parseFloat(core.cleanText(qtyElem).replace(/[^0-9.]/g, "")) || 1.0) : 1.0;
            const unitPrice = priceElem ? core.parsePrice(core.cleanText(priceElem)) : (totalAmount > 0 ? (totalAmount / itemRows.length) : 0.0);

            items.push({
              product_id: productId || `p_tb_${Math.abs(core.cleanText(productName).split("").reduce((a,b)=>{a=((a<<5)-a)+b.charCodeAt(0);return a&a},0)) % 10000000}`,
              sku_id: variantName ? `sku_tb_${Math.abs(variantName.split("").reduce((a,b)=>{a=((a<<5)-a)+b.charCodeAt(0);return a&a},0)) % 1000000}` : "",
              product_name: productName,
              variant_name: variantName,
              quantity: qty,
              unit_price: unitPrice,
              line_total: Math.round(unitPrice * qty * 100) / 100
            });
          });

          results.push({
            order_id: orderId,
            status: status,
            total_amount: totalAmount,
            currency: "CNY",
            items: items
          });
        } catch (err) {
          console.warn("[TaobaoAdapter] Error parsing order card:", err);
        }
      });

      return results;
    },

    async extract(payload) {
      const accountId = payload.account_id || "alansyling@gmail.com";
      const maxOrders = payload.max_orders || 100;
      console.log(`[TaobaoAdapter] Starting extraction for account: ${accountId}`);

      const orders = this.parseOrdersOnPage();
      const exportBtn = this.findExportButton();

      if (orders.length === 0) {
        return {
          extracted_count: 0,
          export_button_found: exportBtn !== null,
          note: exportBtn
            ? "页面 DOM 解析中未识别到展开的卡片，但已检测到【导出订单】按钮！您可直接点击【点击淘宝【导出订单】】按钮生成官方 Excel。"
            : "未在当前页面检测到订单卡片。请确认当前标签页为淘宝【已买到的宝贝】页面（buyertrade.taobao.com）。"
        };
      }

      const batchId = `taobao_batch_${Date.now()}`;
      const batch = {
        batch_id: batchId,
        platform: "taobao",
        account_id: accountId,
        task_id: payload.task_id || "task_taobao",
        orders: orders.slice(0, maxOrders)
      };

      // Submit batch to service worker
      await core.submitBatch(batch);

      // Report checkpoint
      await core.reportCheckpoint({
        last_page_url: window.location.href,
        orders_extracted: batch.orders.length,
        timestamp: new Date().toISOString()
      }, "RUNNING");

      return {
        batch_id: batchId,
        orders_extracted: batch.orders.length
      };
    }
  };

  core.registerAdapter("taobao", TaobaoAdapter);

  // Passive auto-extraction on page load after components render
  setTimeout(async () => {
    try {
      const orders = TaobaoAdapter.parseOrdersOnPage();
      if (orders && orders.length > 0) {
        console.log(`[TaobaoAdapter] Auto-extracted ${orders.length} orders on page load.`);
        const batchId = `taobao_batch_auto_${Date.now()}`;
        await core.submitBatch({
          batch_id: batchId,
          platform: "taobao",
          account_id: "alansyling@gmail.com",
          task_id: "task_auto_taobao",
          orders: orders
        });
      }
    } catch (e) {
      console.debug("[TaobaoAdapter] Passive auto-extraction skip:", e.message);
    }
  }, 2500);
})();
