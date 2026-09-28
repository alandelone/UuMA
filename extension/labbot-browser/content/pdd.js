/**
 * Pinduoduo Order Extraction Content Script Adapter
 * Supports mobile.yangkeduo.com/orders.html, order details (/order.html?order_sn=...),
 * desktop/H5 order cards, multi-line items, SKU/variant specs, status, and pagination.
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

    findOrderRoots() {
      const currentUrl = (window.location && window.location.href) || "";
      const isDetailPage = currentUrl.includes("/order.html") || currentUrl.includes("order_sn=");

      // 1. Specific class selectors for PDD order cards
      const selectorMatches = Array.from(document.querySelectorAll(
        ".order-item-card, .order-card, div[class*='order-item'], div[class*='order_card'], " +
        "div[class*='OrderItem'], div[class*='pdd-order'], div[class*='order-item-module'], div[role='listitem']"
      ));

      if (selectorMatches.length > 0) {
        const valid = selectorMatches.filter(el => {
          const txt = el.textContent || "";
          return txt.length > 15 && (
            txt.includes("订单编号") || txt.includes("订单号") || txt.includes("拼单成功") ||
            txt.includes("已签收") || txt.includes("待发货") || txt.includes("退款成功") ||
            /[0-9\-]{10,}/.test(txt) ||
            el.querySelector("[class*='goods-name'], [class*='goods-info'], a[href*='goods_id']")
          );
        });
        if (valid.length > 0) return valid;
      }

      // 2. Semantic text search for 订单编号 / 订单号
      const candidateRoots = new Set();
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
              candidateRoots.add(curr);
              break;
            }
          }
        }
      }

      if (candidateRoots.size > 0) {
        return Array.from(candidateRoots);
      }

      // 3. Fallback for single order detail page
      if (isDetailPage) {
        return [document.body];
      }

      return [];
    },

    parseOrdersOnPage() {
      const orderRoots = this.findOrderRoots();
      console.log(`[PddAdapter] Scanning page: found ${orderRoots.length} candidate order containers.`);

      const results = [];
      const seenOrderIds = new Set();
      const currentUrl = (window.location && window.location.href) || "";
      const detailUrlMatch = currentUrl.match(/[?&]order_sn=([0-9\-]+)/) || currentUrl.match(/\/order\/([0-9\-]+)/);
      const isDetailPage = !!detailUrlMatch;

      orderRoots.forEach((card, idx) => {
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

          if (!orderId) {
            const header = card.querySelector(".order-header, [class*='header']");
            if (header) {
              const hm = (header.textContent || "").match(/[0-9\-]{10,35}/);
              if (hm) orderId = hm[0].replace(/-/g, "");
            }
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

          // 3. Shop Name
          let shopName = "";
          const shopEl = card.querySelector("[class*='mall-name'], [class*='mall_name'], [class*='shop-name'], [class*='shop'], [class*='merchant'], [class*='seller'], a[href*='mall_id']");
          if (shopEl) {
            shopName = (shopEl.textContent || "").trim().replace(/^(进店\s*[>》]?|商家[：:]\s*|店铺[：:]\s*)/, "").trim();
          }
          if (!shopName) {
            const sm = cardText.match(/(?:店铺|商家|掌柜)[：:\s]*([^\n\r\t]+)/i);
            if (sm) shopName = sm[1].trim();
          }

          // 4. Order Time
          let orderTime = "";
          const timeMatch = cardText.match(/\b(\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)\b/);
          if (timeMatch) {
            orderTime = timeMatch[1];
          }

          // 5. Shipping Fee
          let shippingFee = 0.0;
          const shipMatch = cardText.match(/(?:含运费|运费)[：:\s]*[¥￥]?\s*([0-9]+\.?[0-9]*)/i);
          if (shipMatch) {
            shippingFee = parseFloat(shipMatch[1]) || 0.0;
          }

          // 6. Total Amount
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
          if (totalAmount <= 0) {
            const footer = card.querySelector(".order-footer, [class*='footer']");
            if (footer) {
              const fm = (footer.textContent || "").match(/[¥￥]?\s*([0-9]+\.?[0-9]*)/);
              if (fm) totalAmount = parseFloat(fm[1]) || 0.0;
            }
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
              if (idMatch) {
                pId = idMatch[1];
              }
            }
            if (!pId) {
              pId = `p_pdd_${orderId}_${nIdx}`;
            }

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
                // Card showed order total as price
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
        } catch (err) {
          console.warn("[PddAdapter] Error parsing order card:", err);
        }
      });

      return results;
    },

    async extract(payload) {
      const accountId = payload.account_id || "alansyling@gmail.com";
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
        task_id: payload.task_id || `task_pdd_${Date.now()}`,
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

    findNextPageButton() {
      const selectors = [
        "button[class*='next']",
        "a[class*='next']",
        "li.next a",
        "li.next button",
        "[class*='pagination-next']"
      ];
      for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el && el.offsetParent !== null) return el;
      }
      return null;
    },

    async autoCrawlPages(maxPages = 5, onProgress = null) {
      this.isAutoCrawling = true;
      let totalExtracted = 0;
      let pagesCount = 0;
      const seenOrderIds = new Set();

      for (let p = 1; p <= maxPages; p++) {
        if (!this.isAutoCrawling) {
          if (onProgress) onProgress("已手动停止自动翻页采集。");
          break;
        }

        pagesCount++;
        if (onProgress) onProgress(`正在解析拼多多第 ${p} 页/批次订单 DOM...`);

        const orders = this.parseOrdersOnPage();
        const freshOrders = orders.filter(o => !seenOrderIds.has(o.order_id));
        freshOrders.forEach(o => seenOrderIds.add(o.order_id));

        if (freshOrders.length > 0) {
          const batchId = `pdd_batch_auto_p${p}_${Date.now()}`;
          await core.submitBatch({
            batch_id: batchId,
            platform: "pdd",
            account_id: "alansyling@gmail.com",
            task_id: `task_auto_pdd_p${p}`,
            orders: freshOrders
          });
          totalExtracted += freshOrders.length;
          if (onProgress) onProgress(`✔ 第 ${p} 页完成！新增 ${freshOrders.length} 笔（累计入库 ${totalExtracted} 笔）`);
        } else {
          if (onProgress) onProgress(`第 ${p} 页未发现新订单`);
        }

        if (p >= maxPages) {
          if (onProgress) onProgress(`🎉 已达到设定的最大翻页数 (${maxPages} 页)，连续采集完成！累计抓取入库 ${totalExtracted} 笔订单。`);
          break;
        }

        const nextBtn = this.findNextPageButton();
        if (nextBtn) {
          if (onProgress) onProgress(`第 ${p} 页完成，正在点击下一页并等待加载...`);
          nextBtn.click();
        } else {
          if (onProgress) onProgress(`未发现下一页按钮，向下滚动加载更多订单...`);
          window.scrollBy({ top: 1200, behavior: "smooth" });
        }

        await new Promise(r => setTimeout(r, 3500));
      }

      this.isAutoCrawling = false;
      return { pages: pagesCount, total_orders: totalExtracted };
    }
  };

  core.registerAdapter("pdd", PddAdapter);

  let hudControl = null;
  if (window.top === window.self) {
    hudControl = core.mountFloatingHud({
      platform: "pdd",
      adapter: PddAdapter,
      hasExport: false
    });
  }

  // Persistent auto-extraction polling on page load
  let autoExtracted = false;
  let pollAttempts = 0;
  const maxAttempts = 10;

  async function attemptAutoExtract() {
    if (autoExtracted) return;

    try {
      const orders = PddAdapter.parseOrdersOnPage();
      if (orders && orders.length > 0) {
        autoExtracted = true;
        console.log(`[PddAdapter] Auto-extracted ${orders.length} orders on page load.`);
        const batchId = `pdd_batch_auto_${Date.now()}`;
        await core.submitBatch({
          batch_id: batchId,
          platform: "pdd",
          account_id: "alansyling@gmail.com",
          task_id: "task_auto_pdd",
          orders: orders
        });
        if (hudControl && hudControl.setStatus) {
          hudControl.setStatus("自动完成", `⚡ 页面加载自动采集成功：已提取本页 <strong>${orders.length}</strong> 笔订单并安全入库！`);
        }
        if (window.top && window.top !== window.self) {
          window.top.postMessage({ type: "UUMA_HUD_AUTO_SUCCESS", count: orders.length }, "*");
        }
        return;
      }
    } catch (e) {
      console.debug("[PddAdapter] Auto-extract check:", e.message);
    }

    pollAttempts++;
    if (pollAttempts <= maxAttempts) {
      if (hudControl && hudControl.setStatus) {
        hudControl.setStatus("检测中", `正在等待订单加载... (${pollAttempts}/${maxAttempts})`);
      }
      setTimeout(attemptAutoExtract, 1500);
    } else {
      if (hudControl && hudControl.setStatus) {
        hudControl.setStatus("就绪", "页面已就绪。如未显示订单，请确认处于【订单列表】页并向下滚动。");
      }
    }
  }

  setTimeout(attemptAutoExtract, 1200);
})();
