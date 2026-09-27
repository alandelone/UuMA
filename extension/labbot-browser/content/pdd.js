/**
 * Pinduoduo Order Extraction Content Script Adapter
 */

(function () {
  const core = window.UuMAExtractionCore;

  const PddAdapter = {
    isPaused: false,

    pause() {
      this.isPaused = true;
    },

    resume() {
      this.isPaused = false;
    },

    async extract(payload) {
      const accountId = payload.account_id || "default_pdd";
      const maxOrders = payload.max_orders || 100;
      console.log(`[PddAdapter] Starting extraction for account: ${accountId}`);

      const orders = this.parseOrdersOnPage();
      if (orders.length === 0) {
        return {
          extracted_count: 0,
          note: "No orders found on the current Pinduoduo page. Navigate to orders list (yangkeduo.com/orders.html or mobile orders page)."
        };
      }

      const batchId = `pdd_batch_${Date.now()}`;
      const batch = {
        batch_id: batchId,
        platform: "pdd",
        account_id: accountId,
        task_id: payload.task_id || "task_pdd",
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
    },

    parseOrdersOnPage() {
      let cards = Array.from(document.querySelectorAll(
        ".order-item-card, .order-card, div[class*='order-item'], div[class*='order_card'], div[class*='OrderItem']"
      ));

      if (cards.length === 0) {
        // Fallback for list items or container divs
        cards = Array.from(document.querySelectorAll("div[role='listitem'], .pdd-order-card"));
      }

      const results = [];

      cards.forEach((card) => {
        try {
          let orderId = "";
          // 1. Order ID
          const idEl = card.querySelector("[class*='order-id'], [class*='order-sn'], [class*='orderSn'], [class*='sn']");
          if (idEl) {
            const txt = core.cleanText(idEl);
            const m = txt.match(/[0-9\-]{10,}/);
            if (m) orderId = m[0].replace(/-/g, "");
          }

          if (!orderId) {
            for (const tag of card.querySelectorAll("span, div, p")) {
              const txt = core.cleanText(tag);
              if (txt.includes("订单编号") || txt.includes("订单号")) {
                const m = txt.match(/\d{12,}/);
                if (m) {
                  orderId = m[0];
                  break;
                }
              }
            }
          }

          if (!orderId) return;

          // 2. Status
          const statusEl = card.querySelector("[class*='status'], [class*='order-state'], [class*='state']");
          const status = statusEl ? core.cleanText(statusEl) : "拼单成功";

          // 3. Total amount
          let totalAmount = 0.0;
          const totalEl = card.querySelector("[class*='order-amount'], [class*='total-price'], [class*='pay-amount'], [class*='price']");
          if (totalEl) {
            totalAmount = core.parsePrice(core.cleanText(totalEl));
          }

          // 4. Item Details
          const nameEl = card.querySelector("[class*='goods-name'], [class*='title'], [class*='product-name']");
          const specEl = card.querySelector("[class*='spec'], [class*='sku'], [class*='sku-desc']");
          const qtyEl = card.querySelector("[class*='quantity'], [class*='goods-number'], [class*='count']");

          const pName = nameEl ? core.cleanText(nameEl) : "Pinduoduo Item";
          const vName = specEl ? core.cleanText(specEl) : "";
          const qty = qtyEl ? (parseFloat(core.cleanText(qtyEl).replace(/[^0-9.]/g, "")) || 1.0) : 1.0;
          const unitPrice = totalAmount > 0 ? (Math.round((totalAmount / qty) * 100) / 100) : 0.0;

          const productId = `p_pdd_${Math.abs(pName.split("").reduce((a,b)=>{a=((a<<5)-a)+b.charCodeAt(0);return a&a},0)) % 10000000}`;
          const skuId = vName ? `sku_pdd_${Math.abs(vName.split("").reduce((a,b)=>{a=((a<<5)-a)+b.charCodeAt(0);return a&a},0)) % 1000000}` : "";

          const items = [{
            product_id: productId,
            sku_id: skuId,
            product_name: pName,
            variant_name: vName,
            quantity: qty,
            unit_price: unitPrice,
            line_total: totalAmount
          }];

          results.push({
            order_id: orderId,
            status: status,
            total_amount: totalAmount,
            currency: "CNY",
            items: items
          });
        } catch (err) {
          console.warn("[PddAdapter] Error parsing PDD card:", err);
        }
      });

      return results;
    }
  };

  core.registerAdapter("pdd", PddAdapter);

  // Passive auto-extraction: automatically extracts orders on page load after components render
  setTimeout(async () => {
    try {
      const orders = PddAdapter.parseOrdersOnPage();
      if (orders && orders.length > 0) {
        console.log(`[PddAdapter] Auto-extracted ${orders.length} orders on page load.`);
        const batchId = `pdd_batch_auto_${Date.now()}`;
        await core.submitBatch({
          batch_id: batchId,
          platform: "pdd",
          account_id: "alansyling@gmail.com",
          task_id: "task_auto_pdd",
          orders: orders
        });
      }
    } catch (e) {
      console.debug("[PddAdapter] Passive auto-extraction skip:", e.message);
    }
  }, 2500);
})();

