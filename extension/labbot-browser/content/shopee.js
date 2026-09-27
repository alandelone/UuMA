/**
 * Shopee MY Order Extraction Content Script Adapter
 */

(function () {
  const core = window.UuMAExtractionCore;

  const ShopeeAdapter = {
    isPaused: false,

    pause() {
      this.isPaused = true;
    },

    resume() {
      this.isPaused = false;
    },

    async extract(payload) {
      const accountId = payload.account_id || "default_shopee";
      const maxOrders = payload.max_orders || 100;
      console.log(`[ShopeeAdapter] Starting extraction for account: ${accountId}`);

      const orders = this.parseOrdersOnPage();
      if (orders.length === 0) {
        return {
          extracted_count: 0,
          note: "No orders found on the current Shopee page."
        };
      }

      const batchId = `shopee_batch_${Date.now()}`;
      const batch = {
        batch_id: batchId,
        platform: "shopee",
        account_id: accountId,
        task_id: payload.task_id || "task_shopee",
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
      const orderCards = document.querySelectorAll(".purchase-list-page__order-card, .order-card, [class*='order-card']");
      const results = [];

      orderCards.forEach((card, idx) => {
        try {
          let orderId = "";
          const orderIdElem = card.querySelector("[class*='order-id'], [class*='order-sn'], [class*='ordersn']");
          if (orderIdElem) {
            orderId = core.cleanText(orderIdElem).replace(/[^0-9A-Za-z]/g, "");
          } else {
            for (const el of card.querySelectorAll("span, div")) {
              const txt = core.cleanText(el);
              if (txt.includes("Order SN") || txt.includes("Order ID")) {
                const match = txt.match(/[A-Za-z0-9]{8,}/);
                if (match) {
                  orderId = match[0];
                  break;
                }
              }
            }
          }

          if (!orderId) {
            console.warn("[ShopeeAdapter] Skipping order card without identifiable order ID.");
            return;
          }

          const statusElem = card.querySelector("[class*='order-status'], [class*='status-text']");
          const status = statusElem ? core.cleanText(statusElem) : "Completed";

          const totalElem = card.querySelector("[class*='total-price'], [class*='order-total']");
          const totalAmount = totalElem ? core.parsePrice(core.cleanText(totalElem)) : 0.0;

          // Parse items
          const itemNodes = card.querySelectorAll("[class*='order-item'], [class*='product-item']");
          const items = [];

          if (itemNodes.length > 0) {
            itemNodes.forEach((node, itemIdx) => {
              const nameElem = node.querySelector("[class*='item-name'], [class*='product-name'], [class*='title']");
              const variantElem = node.querySelector("[class*='variation'], [class*='model'], [class*='spec']");
              const qtyElem = node.querySelector("[class*='quantity'], [class*='item-quantity'], [class*='qty']");
              const priceElem = node.querySelector("[class*='item-price'], [class*='price']");
              const linkElem = node.querySelector("a[href*='product'], a[href*='item']");

              let productId = "";
              if (linkElem && linkElem.href) {
                const pMatch = linkElem.href.match(/\/(\d+)\/(\d+)|\/product\/[^/]+\/(\d+)|item_id=(\d+)/);
                if (pMatch) {
                  productId = pMatch[1] || pMatch[2] || pMatch[3] || pMatch[4];
                }
              }

              const productName = nameElem ? core.cleanText(nameElem) : "Shopee Product";
              const variantName = variantElem ? core.cleanText(variantElem) : "";
              const qtyText = qtyElem ? core.cleanText(qtyElem) : "1";
              const quantity = parseFloat(qtyText.replace(/[^0-9.]/g, "")) || 1.0;
              const unitPrice = priceElem ? core.parsePrice(core.cleanText(priceElem)) : (totalAmount / (itemNodes.length || 1));

              items.push({
                product_id: productId || "p_shopee_" + encodeURIComponent(productName.substring(0, 20)),
                sku_id: variantName ? "sku_" + encodeURIComponent(variantName) : "",
                product_name: productName,
                variant_name: variantName,
                quantity: quantity,
                unit_price: unitPrice,
                line_total: unitPrice * quantity
              });
            });
          } else {
            items.push({
              product_id: "p_shopee_line",
              sku_id: "",
              product_name: "Shopee Purchase Item",
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
            currency: "MYR",
            items: items
          });
        } catch (err) {
          console.warn("[ShopeeAdapter] Error parsing card:", err);
        }
      });

      return results;
    }
  };

  core.registerAdapter("shopee", ShopeeAdapter);

  // Passive auto-extraction: automatically extracts orders on page load after components render
  setTimeout(async () => {
    try {
      const orders = ShopeeAdapter.parseOrdersOnPage();
      if (orders && orders.length > 0) {
        console.log(`[ShopeeAdapter] Auto-extracted ${orders.length} orders on page load.`);
        const batchId = `shopee_batch_auto_${Date.now()}`;
        await core.submitBatch({
          batch_id: batchId,
          platform: "shopee",
          account_id: "alansyling@gmail.com",
          task_id: "task_auto_shopee",
          orders: orders
        });
      }
    } catch (e) {
      console.debug("[ShopeeAdapter] Passive auto-extraction skip:", e.message);
    }
  }, 2500);
})();

