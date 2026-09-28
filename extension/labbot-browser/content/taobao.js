/**
 * Taobao Order Extraction Content Script Adapter
 * Supports standard Taobao buyer trade lists, React/Vue dynamic cards, and export button triggers.
 */

(function () {
  const core = window.UuMAExtractionCore;
  console.log("[UuMA TaobaoAdapter] Build 2026-09-28-v2.2 active.");

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
      // 1. First priority: Target complete order tables or wrapper cards
      const selectorMatches = Array.from(document.querySelectorAll(
        "table.bought-table, .bought-wrapper-mod, div[class*='bought-wrapper'], " +
        "[class*='index-mod__order-container'], [class*='orderContainer'], " +
        "table[class*='bought'], div[class*='trade-order'], div[class*='trade-item']"
      ));

      let cards = [];
      if (selectorMatches.length > 0) {
        cards = selectorMatches.filter(el => {
          const txt = (el.innerText || el.textContent || "").trim();
          return txt.length > 30 && (txt.includes("订单号") || txt.includes("订单编号") || /\d{15,}/.test(txt) || el.querySelector("a[href*='item'], a[href*='detail']"));
        });
      }

      // 2. Semantic Text Search: Find elements containing "订单号" or "订单编号" and climb to TABLE
      if (cards.length === 0) {
        const candidateSet = new Set();
        const allSpans = Array.from(document.querySelectorAll("span, div, p, td, th, li, b, font"));
        for (const el of allSpans) {
          const txt = (el.innerText || el.textContent || "").trim();
          if (txt.includes("订单号") || txt.includes("订单编号") || txt.includes("Order ID") || txt.includes("Order SN")) {
            let curr = el;
            for (let i = 0; i < 8; i++) {
              if (!curr.parentElement || curr.parentElement === document.body) break;
              curr = curr.parentElement;
              if (
                curr.tagName === "TABLE" ||
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
        }
        cards = Array.from(candidateSet);
      }

      // 3. Anchor Search: Find product item links and climb up to the enclosing TABLE or container that has "订单号"
      if (cards.length === 0) {
        const candidateSet = new Set();
        const itemLinks = Array.from(document.querySelectorAll("a[href*='item.taobao.com'], a[href*='detail.tmall.com']"));
        for (const link of itemLinks) {
          let curr = link;
          for (let i = 0; i < 8; i++) {
            if (!curr.parentElement || curr.parentElement === document.body) break;
            curr = curr.parentElement;
            const t = (curr.innerText || curr.textContent || "").trim();
            if (curr.tagName === "TABLE" || t.includes("订单号") || t.includes("订单编号") || /\d{15,}/.test(t)) {
              candidateSet.add(curr);
              break;
            }
          }
        }
        cards = Array.from(candidateSet);
      }

      // 4. CRITICAL: Ensure every candidate card is expanded to its parent TABLE if it lacks item links
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

      // 5. Deduplicate and filter out outer wrappers that contain multiple child cards
      const uniqueCards = Array.from(new Set(expandedCards));
      return uniqueCards.filter(c => {
        const txt = (c.innerText || c.textContent || "").trim();
        if (txt.length < 30) return false;
        return !uniqueCards.some(other => other !== c && c.contains(other));
      });
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

          const cardText = card.textContent || "";

          // 2. Status
          let status = "交易成功";
          const statusElem = card.querySelector("[class*='order-status'], [class*='status'], [class*='trade-status'], [class*='state']");
          if (statusElem) {
            status = core.cleanText(statusElem);
          } else {
            for (const s of ["交易成功", "卖家已发货", "买家已付款", "等待买家付款", "交易关闭", "退款成功"]) {
              if (cardText.includes(s)) {
                status = s;
                break;
              }
            }
          }

          // Order Time
          let orderTime = "";
          const timeMatch = cardText.match(/\b(\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)\b/);
          if (timeMatch) orderTime = timeMatch[1];

          // Shop Name
          let shopName = "";
          const shopEl = card.querySelector("[class*='shop-name'], [class*='seller'], [class*='shop_name'], a[href*='shop.taobao.com'], a[href*='store.taobao.com']");
          if (shopEl) {
            shopName = core.cleanText(shopEl);
          }
          if (!shopName) {
            const shopMatch = cardText.match(/(?:店铺|掌柜|卖家)[：:\s]*([^\s\n\r]+)/);
            if (shopMatch) shopName = shopMatch[1];
          }

          // Shipping Fee
          let shippingFee = 0.0;
          const shipMatch = cardText.match(/(?:含运费|运费)[：:\s]*[¥￥]?\s*([0-9]+\.?[0-9]*)/);
          if (shipMatch) shippingFee = parseFloat(shipMatch[1]) || 0.0;

          // 3. Total amount
          let totalAmount = 0.0;
          const totalElem = card.querySelector("[class*='real-price'], [class*='total-price'], [class*='realprice'], [class*='amount'], [class*='actual-price']");
          if (totalElem) {
            totalAmount = core.parsePrice(core.cleanText(totalElem));
          } else {
            const priceMatches = cardText.match(/[¥￥]\s*([0-9]+\.?[0-9]*)/g);
            if (priceMatches && priceMatches.length > 0) {
              const numbers = priceMatches.map(p => core.parsePrice(p));
              totalAmount = Math.max(...numbers);
            }
          }

          // 4. Items with deduplication
          const rawAnchors = Array.from(card.querySelectorAll("a[href*='item.taobao.com'], a[href*='detail.tmall.com']"));
          const itemsMap = new Map();

          rawAnchors.forEach((a, aIdx) => {
            const href = a.href || "";
            let text = core.cleanText(a);

            // Filter out phantom recommendation / action badges
            if (/已购买\d+次|再次购买|去评价|追加评价|查看物流|申请售后|退款|投诉/.test(text)) {
              return;
            }
            if (text === "[交易快照]" || text === "交易快照") {
              return;
            }
            // Strip trailing [交易快照]
            text = text.replace(/\[交易快照\]/g, "").trim();

            // CRITICAL: Filter out image thumbnail anchors (which have no text or length < 2)
            if (!text || text.length < 2) {
              return;
            }

            const idMatch = href.match(/[?&]id=(\d+)/);
            const pId = idMatch ? idMatch[1] : `p_tb_${aIdx}`;

            let vName = "";
            let qty = 1.0;
            let unitPrice = 0.0;

            // 1. Direct row detection: In HTML tables, <tr> is the exact item row
            let fullRow = a.closest("tr");
            if (!fullRow) {
              fullRow = a.closest("[class*='item-mod'], [class*='item-row'], [class*='bought-item'], [class*='trade-item']");
            }
            // 2. If not a table row or known class, climb up to find multi-column item container
            if (!fullRow) {
              let curr = a.parentElement;
              for (let i = 0; i < 6; i++) {
                if (!curr || curr === card) break;
                const txt = curr.innerText || curr.textContent || "";
                if ((txt.includes("¥") || txt.includes("￥") || /[×xX*]\s*\d+/.test(txt) || /\d+\.\d{2}/.test(txt)) &&
                    (curr.children.length >= 2 || curr.querySelectorAll("td").length >= 2)) {
                  fullRow = curr;
                  break;
                }
                curr = curr.parentElement;
              }
            }
            if (!fullRow) fullRow = a.closest("tr, div, li") || a.parentElement;

            if (fullRow) {
              const tds = Array.from(fullRow.querySelectorAll("td"));

              // 1. Spec extraction with multi-layer fallback
              // Layer A: Dedicated selectors
              const specEl = fullRow.querySelector("[class*='spec'], [class*='sku'], [class*='props'], [class*='item-spec'], [class*='attr'], [class*='desc']");
              if (specEl) {
                let st = core.cleanText(specEl);
                st = st.replace(/^(?:颜色分类|规格款式|颜色|规格|型号|款式|尺码|套餐|属性)[：:\s]*/, "").trim();
                if (st && !/加入购物车|立即购买|查看物流|再次购买/.test(st)) vName = st;
              }

              // Layer B: Regex on fullRow text for standard Taobao spec keywords
              if (!vName) {
                const rowText = fullRow.innerText || fullRow.textContent || "";
                const sm = rowText.match(/(?:颜色分类|规格款式|颜色|规格|型号|款式|尺码|套餐|属性|类型|版本|配置)[：:\s]*([^\n\r\t,，;；|]+)/);
                if (sm) {
                  const candidate = sm[1].trim();
                  if (!/加入购物车|立即购买|查看物流|再次购买/.test(candidate)) {
                    vName = candidate;
                  }
                }
              }

              // Layer C: Sibling nodes scanner climbing up from anchor 'a'
              if (!vName) {
                let p = a.parentElement;
                for (let step = 0; step < 4 && p && p !== card; step++) {
                  const children = Array.from(p.querySelectorAll("p, span, div, em, small, [class*='sku'], [class*='spec'], [class*='prop']"));
                  for (const child of children) {
                    if (child === a || child.contains(a) || a.contains(child)) continue;
                    let ct = (child.innerText || child.textContent || "").trim();
                    if (!ct || ct.length < 2 || ct.length > 80) continue;
                    if (/已购买|再次购买|评价|快照|退款|投诉|物流|保险|购物车|运费险|本地退|假一赔|无理由|破损|急送|保障|包换|包退|正品/.test(ct)) continue;
                    if (ct.includes(text) || text.includes(ct)) continue;
                    if (/^[¥￥0-9\.\s]+$/.test(ct)) continue;

                    const sm = ct.match(/(?:颜色分类|规格款式|颜色|规格|型号|款式|尺码|套餐|属性)[：:\s]*([^\n\r]+)/);
                    if (sm) {
                      vName = sm[1].trim();
                      break;
                    } else if (/^[a-zA-Z0-9_\-\u4e00-\u9fa5\s\/\(\)\+（）【】、，\.]{2,60}$/.test(ct)) {
                      vName = ct;
                      break;
                    }
                  }
                  if (vName) break;
                  p = p.parentElement;
                }
              }

              // 2. Quantity extraction with multi-layer fallback
              // Priority 1: Table cells (tds)
              if (tds.length >= 3) {
                const tCount = parseFloat((tds[2].innerText || "").replace(/[^0-9.]/g, ""));
                if (tCount > 0 && tCount < 100000) qty = tCount;
              }

              // Priority 2: Scan all non-item td cells for a standalone integer
              if (qty <= 1.0 && tds.length > 0) {
                const itemTd = a.closest("td");
                for (const td of tds) {
                  if (td === itemTd) continue;
                  const t = (td.innerText || "").trim();
                  if (/^\d{1,4}$/.test(t)) {
                    const n = parseInt(t, 10);
                    if (n > 1 && n < 10000) {
                      qty = n;
                      break;
                    }
                  }
                }
              }

              // Priority 3: Dedicated count class
              if (qty <= 1.0) {
                const qtyEl = fullRow.querySelector("[class*='quantity'], [class*='count'], [class*='num'], [class*='number']");
                if (qtyEl) {
                  const q = parseFloat(core.cleanText(qtyEl).replace(/[^0-9.]/g, ""));
                  if (q > 0 && q < 100000) qty = q;
                }
              }

              // Priority 4: Chinese unit (20件)
              if (qty <= 1.0) {
                const rowText = fullRow.innerText || fullRow.textContent || "";
                const jianMatch = rowText.match(/(\d+)\s*件/);
                if (jianMatch) {
                  qty = parseFloat(jianMatch[1]);
                }
              }

              // Priority 5: Multiplier symbol (×20, x20, *20) - exclude dimensions like 48X48mm, 50*50cm
              if (qty <= 1.0) {
                const rowText = fullRow.innerText || fullRow.textContent || "";
                const multMatch = rowText.match(/(?:^|[^\d\w])[\u00d7*xX]\s*(\d+)(?!\s*(?:mm|cm|m|g|kg|寸|v|V|w|W|a|A|mah|ah|hz|k|p|P))/);
                if (multMatch) {
                  qty = parseFloat(multMatch[1]);
                }
              }

              // Priority 6: Standalone integer leaf text
              if (qty <= 1.0) {
                const leaves = Array.from(fullRow.querySelectorAll("span, div, p, em"));
                for (const leaf of leaves) {
                  if (leaf.children.length === 0) {
                    const lt = (leaf.innerText || "").trim();
                    if (/^\d{1,4}$/.test(lt)) {
                      const n = parseInt(lt, 10);
                      if (n > 1 && n < 10000) {
                        qty = n;
                        break;
                      }
                    }
                  }
                }
              }

              // 3. Unit Price extraction
              const priceEl = fullRow.querySelector("[class*='unit-price'], [class*='item-price'], [class*='price']");
              if (priceEl) {
                const up = core.parsePrice(core.cleanText(priceEl));
                if (up > 0) unitPrice = up;
              }
              if (unitPrice <= 0 && tds.length >= 2) {
                const tPrice = core.parsePrice(tds[1].innerText || "");
                if (tPrice > 0) unitPrice = tPrice;
              }
              if (unitPrice <= 0 && tds.length > 0) {
                const itemTd = a.closest("td");
                for (const td of tds) {
                  if (td === itemTd) continue;
                  const t = (td.innerText || "").trim();
                  const m = t.match(/^[¥￥]?\s*([0-9]+\.[0-9]{2})$/);
                  if (m) {
                    unitPrice = parseFloat(m[1]);
                    break;
                  }
                }
              }
              if (unitPrice <= 0) {
                const pMatches = Array.from(fullRow.querySelectorAll("span, p, div, em, td"))
                  .map(el => {
                    const t = (el.innerText || "").trim();
                    const m = t.match(/^[¥￥]\s*([0-9]+\.?[0-9]*)$/) || t.match(/^([0-9]+\.[0-9]{2})$/);
                    return m ? parseFloat(m[1]) : 0;
                  })
                  .filter(p => p > 0);
                if (pMatches.length > 0) {
                  if (qty > 1 && totalAmount > 0) {
                    const candidate = pMatches.find(p => p < totalAmount);
                    unitPrice = candidate || pMatches[0];
                  } else {
                    unitPrice = pMatches[0];
                  }
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
          orders_extracted: 0,
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
    },

    findNextPageButton() {
      const selectors = [
        "li.pagination-next:not(.pagination-disabled) a",
        "li.pagination-next:not(.pagination-disabled) button",
        "button.pagination-next:not(:disabled)",
        "a.pagination-next",
        "li.next-page:not(.disabled) a",
        "li.next-page:not(.disabled) button",
        ".rc-pagination-next:not(.rc-pagination-disabled) button",
        ".rc-pagination-next:not(.rc-pagination-disabled) a",
        "li[title='下一页']:not(.disabled) a",
        "li[title='下一页']:not(.disabled) button",
        "[class*='pagination-next']:not([class*='disabled'])",
        "[class*='pagination'] [title='下一页']"
      ];
      for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el && el.offsetParent !== null) return el;
      }

      const allClickables = Array.from(document.querySelectorAll("button, a, span, li"));
      for (const el of allClickables) {
        const txt = (el.innerText || el.textContent || "").trim();
        if (txt === "下一页" || txt === "下一頁") {
          const isDisabled = el.classList.contains("disabled") ||
                             el.classList.contains("pagination-disabled") ||
                             el.getAttribute("aria-disabled") === "true" ||
                             el.disabled ||
                             (el.parentElement && (el.parentElement.classList.contains("disabled") || el.parentElement.classList.contains("pagination-disabled")));
          if (!isDisabled && el.offsetParent !== null) {
            return el;
          }
        }
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
        if (onProgress) onProgress(`正在解析第 ${p} 页订单 DOM...`);

        const orders = this.parseOrdersOnPage();
        const freshOrders = orders.filter(o => !seenOrderIds.has(o.order_id));
        freshOrders.forEach(o => seenOrderIds.add(o.order_id));

        if (freshOrders.length > 0) {
          const batchId = `taobao_batch_auto_p${p}_${Date.now()}`;
          await core.submitBatch({
            batch_id: batchId,
            platform: "taobao",
            account_id: "alansyling@gmail.com",
            task_id: `task_auto_p${p}`,
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
        if (!nextBtn) {
          if (onProgress) onProgress(`🏁 已到达最后一页（未找到可用的【下一页】按钮）。累计抓取入库 ${totalExtracted} 笔订单！`);
          break;
        }

        if (onProgress) onProgress(`第 ${p} 页完成，正在点击【下一页】并等待加载...`);
        nextBtn.click();

        await new Promise(r => setTimeout(r, 3500));
      }

      this.isAutoCrawling = false;
      return { pages: pagesCount, total_orders: totalExtracted };
    }
  };

  core.registerAdapter("taobao", TaobaoAdapter);

  let hudControl = null;
  if (window.top === window.self) {
    hudControl = core.mountFloatingHud({
      platform: "taobao",
      adapter: TaobaoAdapter,
      hasExport: true
    });
  }

  // Persistent auto-extraction polling on page load
  let autoExtracted = false;
  let pollAttempts = 0;
  const maxAttempts = 10;

  async function attemptAutoExtract() {
    if (autoExtracted) return;

    try {
      const orders = TaobaoAdapter.parseOrdersOnPage();
      if (orders && orders.length > 0) {
        autoExtracted = true;
        console.log(`[TaobaoAdapter] Auto-extracted ${orders.length} orders on page load.`);
        const batchId = `taobao_batch_auto_${Date.now()}`;
        await core.submitBatch({
          batch_id: batchId,
          platform: "taobao",
          account_id: "alansyling@gmail.com",
          task_id: "task_auto_taobao",
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
      console.debug("[TaobaoAdapter] Auto-extract check:", e.message);
    }

    pollAttempts++;
    if (pollAttempts <= maxAttempts) {
      if (hudControl && hudControl.setStatus) {
        hudControl.setStatus("检测中", `正在等待订单加载... (${pollAttempts}/${maxAttempts})`);
      }
      setTimeout(attemptAutoExtract, 1500);
    } else {
      if (hudControl && hudControl.setStatus) {
        const hasExport = TaobaoAdapter.findExportButton() !== null;
        hudControl.setStatus("就绪", hasExport
          ? "页面已就绪。已识别到【导出订单】按钮，可点击【⚡ 抓取本页】或【📋 导出官方Excel】。"
          : "页面已就绪。如未显示订单，请确认处于【已买到的宝贝】列表页并点击【⚡ 抓取本页】。");
      }
    }
  }

  setTimeout(attemptAutoExtract, 1200);
})();
