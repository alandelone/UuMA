/**
 * Shopee MY Order Extraction Content Script Adapter
 * Supports Shopee purchase history (/user/purchase), order details, React SPA dynamic cards, and pagination.
 */

(function () {
  const core = window.UuMAExtractionCore;
  console.log("[UuMA ShopeeAdapter] Build 2026-09-28-v2.5 active.");

  const ShopeeAdapter = {
    isPaused: false,

    pause() {
      this.isPaused = true;
    },

    resume() {
      this.isPaused = false;
    },

    findOrderRoots() {
      const currentUrl = (window.location && window.location.href) || "";
      const isDetailPage = currentUrl.includes("/user/purchase/order/");
      if (isDetailPage) {
        return [document.body];
      }

      // 1. Explicit fixture and known Shopee class matches
      const explicitSelectors = [
        ".purchase-list-page__order-card",
        ".order-card",
        "div[class*='order-card']",
        "div[class*='purchase-card']",
        "div[class*='purchaseCard']",
        "div[class*='orderCard']",
        "div[class*='purchase-list-card']",
        "div[class*='order-list-item']",
        "div[class*='order-item-card']"
      ];
      const explicitMatches = Array.from(document.querySelectorAll(explicitSelectors.join(", ")));
      const explicitValid = explicitMatches.filter(el => {
        const txt = el.textContent || "";
        return txt.length > 25 && /RM\s*[0-9]+/i.test(txt) &&
          (el.querySelector("a, img, [class*='order-item'], [class*='product-item']") || /x\s*\d+/i.test(txt));
      });
      if (explicitValid.length > 0) {
        // Discard outer containers that contain child order cards
        const deduped = explicitValid.filter(c => !explicitValid.some(other => other !== c && c.contains(other)));
        return deduped.length > 0 ? deduped : explicitValid;
      }

      // 2. Anchor-based ascent from order detail links or action buttons
      const candidateRoots = new Set();
      const patternPrice = /RM\s*[0-9]+(?:\.[0-9]{2})?/i;
      const patternKeyword = /(?:Total|Jumlah|总额|合计|实付|Buy Again|Beli Semula|再次购买|Completed|Selesai|已完成|To Ship|Untuk Dihantar|待发货|To Receive|Untuk Diterima|待收货|Cancelled|Dibatalkan|已取消|Refund|Bayaran Balik|退款|Order|Pesanan|订单|Order SN|Order ID|Pesanan ID)/i;

      // Find anchor elements: detail links, product links, or action buttons
      const anchors = Array.from(document.querySelectorAll(
        "a[href*='/user/purchase/order/'], a[href*='/product/'], a[href*='-i.'], a[href*='/order/'], a[href*='purchase'], " +
        "button, [role='button'], span, div"
      )).filter(el => {
        const t = (el.innerText || el.textContent || "").trim();
        return (el.tagName === "A" && /product|-i\.|order|purchase/.test(el.href || "")) ||
               /^(?:Buy Again|Beli Semula|再次购买|Contact Seller|Hubungi Penjual|Chat Now)$/i.test(t) ||
               /(?:Order SN|Order ID|No\.?\s*Pesanan|Pesanan ID)[：:\s]*[A-Za-z0-9]+/i.test(t);
      });

      for (const a of anchors) {
        let curr = a;
        for (let i = 0; i < 14; i++) {
          if (!curr.parentElement || curr.parentElement === document.body) break;
          curr = curr.parentElement;
          const txt = curr.textContent || "";
          if (txt.length >= 35 && txt.length <= 8000 && patternPrice.test(txt) && patternKeyword.test(txt)) {
            // Must have product item or image or quantity
            if (curr.querySelector("img, a[href*='product'], a[href*='-i.']") || /x\s*\d+/i.test(txt)) {
              candidateRoots.add(curr);
              break;
            }
          }
        }
      }

      // 3. Fallback Universal Search
      if (candidateRoots.size === 0) {
        const elements = Array.from(document.querySelectorAll("div, section, article, li, tbody"));
        for (const el of elements) {
          const txt = el.textContent || "";
          if (txt.length >= 35 && txt.length <= 8000 && patternPrice.test(txt) && patternKeyword.test(txt)) {
            if (el.querySelector("img, a[href*='product'], a[href*='-i.'], a[href*='order'], a[href*='purchase']") || /x\s*\d+/i.test(txt)) {
              candidateRoots.add(el);
            }
          }
        }
      }

      let roots = Array.from(candidateRoots);
      // Remove wrappers that contain 2 or more distinct order cards
      roots = roots.filter(c => {
        const childCount = roots.filter(other => other !== c && c.contains(other)).length;
        return childCount < 2;
      });
      // If a container contains 1 child candidate, prefer the one with product items
      roots = roots.filter(c => {
        const children = roots.filter(other => other !== c && c.contains(other));
        if (children.length === 1) {
          const child = children[0];
          const cItems = c.querySelectorAll("img, a[href*='product'], a[href*='-i.'], [class*='item']").length;
          const childItems = child.querySelectorAll("img, a[href*='product'], a[href*='-i.'], [class*='item']").length;
          if (cItems > childItems) return true;
          return false;
        }
        return true;
      });

      return roots;
    },

    parseOrdersOnPage() {
      const orderRoots = this.findOrderRoots();
      console.log(`[ShopeeAdapter] Scanning page: found ${orderRoots.length} candidate order containers.`);

      const results = [];
      const seenOrderIds = new Set();
      const currentUrl = (window.location && window.location.href) || "";
      const detailUrlMatch = currentUrl.match(/\/user\/purchase\/order\/([A-Za-z0-9]+)/);
      const isDetailPage = !!detailUrlMatch;

      orderRoots.forEach((card, idx) => {
        try {
          const cardText = card.textContent || "";

          // 1. Order ID
          let orderId = "";
          if (isDetailPage && detailUrlMatch) {
            orderId = detailUrlMatch[1];
          }

          if (!orderId) {
            const detailLink = card.querySelector("a[href*='/user/purchase/order/'], a[href*='/order/']");
            if (detailLink) {
              const lm = detailLink.href.match(/\/order\/([A-Za-z0-9]+)/);
              if (lm) orderId = lm[1];
            }
          }

          if (!orderId) {
            const idEl = card.querySelector("[class*='order-sn'], [class*='ordersn'], [class*='order-id'], [class*='orderId'], [class*='order-number']");
            if (idEl) {
              const raw = idEl.textContent.trim();
              const m = raw.match(/[A-Za-z0-9]{8,35}/);
              if (m) orderId = m[0];
            }
          }

          if (!orderId) {
            const idMatch = cardText.match(/(?:Order\s*(?:SN|ID|No\.?)|No\.?\s*Pesanan|Pesanan\s*ID|订单编号|订单号)[：:\s]*([A-Za-z0-9]{8,35})/i);
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

          // Shopee 14-16 digit order number in card text
          if (!orderId) {
            const digitsMatch = cardText.match(/\b(19\d{13,14}|2[0-9]{13,15})\b/);
            if (digitsMatch) orderId = digitsMatch[1];
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
              let hash = 0;
              for (let i = 0; i < cardText.length; i++) {
                hash = (hash << 5) - hash + cardText.charCodeAt(i);
                hash |= 0;
              }
              seed = String(Math.abs(hash)).substring(0, 8);
            }
            orderId = `SP_${idx + 1}_${seed}`;
          }

          if (seenOrderIds.has(orderId)) return;
          seenOrderIds.add(orderId);

          // 2. Status
          let status = "Completed";
          const statusEl = card.querySelector("[class*='order-status'], [class*='status-text'], [class*='status-label'], [class*='purchase-card__status'], [class*='order-state']");
          if (statusEl) {
            status = statusEl.textContent.trim();
          } else {
            const statusCandidates = [
              "Completed", "To Ship", "To Receive", "To Pay", "Cancelled", "Refund Completed", "Return Refund",
              "Selesai", "Untuk Dihantar", "Untuk Diterima", "Untuk Dibayar", "Dibatalkan", "Bayaran Balik Selesai",
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
            const headerEl = card.querySelector("[class*='header'], [class*='shop'], [class*='seller']");
            if (headerEl) {
              const headerAnchors = Array.from(headerEl.querySelectorAll("a, span, div"))
                .map(a => (a.innerText || a.textContent || "").trim())
                .filter(t => t.length >= 2 && t.length <= 40 && !/^(?:Visit\s*Shop|Chat\s*Now|Chat|进店|聊天|Shopee\s*Mall|Preferred\+?|Mall|Official\s*Store|Completed|To\s*Ship|Cancelled|Refund|Selesai|Dibatalkan)$/i.test(t));
              if (headerAnchors.length > 0) {
                shopName = headerAnchors[0];
              }
            }
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
          const shipMatch = cardText.match(/(?:Shipping\s*(?:Fee|Total)?|Penghantaran|运费)[：:\s]*RM\s*([0-9]+\.?[0-9]*)/i);
          if (shipMatch) shippingFee = parseFloat(shipMatch[1]) || 0.0;

          // 6. Order Total (Actual paid amount / 实付金额)
          let totalAmount = 0.0;

          // Priority 1: Explicit 'Order Total' / 'Jumlah Pesanan' label in text (takes precedence over item row prices)
          const orderTotalMatches = Array.from(cardText.matchAll(/(?:Order\s*Total|Total\s*Payment|Jumlah\s*Pesanan|Jumlah\s*Bayaran|实付金额|实付|合计)[\s\S]{0,60}?RM\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|[0-9]+\.?[0-9]*)/gi));
          if (orderTotalMatches.length > 0) {
            const lastMatch = orderTotalMatches[orderTotalMatches.length - 1];
            totalAmount = parseFloat(lastMatch[1].replace(/,/g, "")) || 0.0;
          }

          // Priority 2: Dedicated footer total element
          if (totalAmount <= 0) {
            const footerEl = card.querySelector(".order-footer, [class*='footer'], [class*='order-total'], [class*='orderTotal']");
            if (footerEl) {
              const fm = (footerEl.textContent || "").match(/RM\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|[0-9]+\.?[0-9]*)/i);
              if (fm) totalAmount = parseFloat(fm[1].replace(/,/g, "")) || 0.0;
            }
          }

          // 7. Items
          let itemNodes = Array.from(card.querySelectorAll(
            ".order-item, .product-item, div[class*='order-item'], div[class*='product-item'], " +
            "div[class*='purchase-card__item'], div[class*='order-content__item'], div[class*='item-card'], " +
            "div[class*='order-card__item'], div[class*='purchase-list-page__order-item']"
          ));

          if (itemNodes.length === 0) {
            // Find item rows by product images or product links or quantity elements
            const itemAnchors = Array.from(card.querySelectorAll(
              "a[href*='/product/'], a[href*='-i.'], a[href*='/item/'], img, [class*='quantity'], [class*='qty']"
            )).filter(el => {
              if (el.tagName === "IMG") {
                const w = el.naturalWidth || el.width || 0;
                const h = el.naturalHeight || el.height || 0;
                const src = el.src || "";
                if (/avatar|icon|badge|mall|logo/i.test(src) || (w > 0 && w < 28) || (h > 0 && h < 28)) return false;
                return true;
              }
              return true;
            });

            const rowSet = new Set();
            for (const a of itemAnchors) {
              let curr = a;
              for (let i = 0; i < 6; i++) {
                if (!curr.parentElement || curr.parentElement === card) break;
                curr = curr.parentElement;
                const ct = curr.textContent || "";
                if (ct.length > 15 && (/RM\s*[0-9]+/i.test(ct) || /x\s*\d+/i.test(ct))) {
                  rowSet.add(curr);
                  break;
                }
              }
            }
            let rows = Array.from(rowSet);
            itemNodes = rows.filter(r => !rows.some(other => other !== r && r.contains(other)));
          }

          if (itemNodes.length === 0) {
            const links = Array.from(card.querySelectorAll("a[href*='/product/'], a[href*='-i.'], a[href*='/order/']"));
            const parentSet = new Set();
            for (const l of links) {
              let curr = l;
              for (let i = 0; i < 4; i++) {
                if (!curr.parentElement || curr.parentElement === card) break;
                curr = curr.parentElement;
                if (curr.textContent.length > 15) {
                  parentSet.add(curr);
                  break;
                }
              }
            }
            itemNodes = Array.from(parentSet);
          }

          const items = [];
          const seenItemKeys = new Set();

          itemNodes.forEach((node, nIdx) => {
            const linkEl = node.querySelector("a[href*='/product/'], a[href*='-i.'], a[href*='/item/']");
            const nameEl = node.querySelector("[class*='item-name'], [class*='product-name'], [class*='product-title'], [class*='title'], [class*='name']");
            const specEl = node.querySelector("[class*='variation'], [class*='model'], [class*='spec'], [class*='item-variation'], [class*='option']");
            const qtyEl = node.querySelector("[class*='quantity'], [class*='item-quantity'], [class*='qty'], [class*='count']");
            const priceEl = node.querySelector("[class*='item-price'], [class*='price'], [class*='unit-price']:not([class*='original']):not([class*='strike'])");

            // 1. Variation / Spec Extraction FIRST
            let vName = "";
            if (specEl) {
              vName = specEl.textContent.trim().replace(/^(?:Variation|Variasi|Pilihan|Option|Model|Type|Jenis|Package|Pakej|Color|Colour|Warna|规格|型号|款式|颜色)[：:\s]*/i, "").trim();
            }

            const nodeText = (node.innerText || node.textContent || "");
            if (!vName) {
              const vm1 = nodeText.match(/(?:Variation|Variasi|Pilihan|Option|Package|Pakej|Colour|Color|Warna|规格|型号|款式|颜色)[：:\s]+([^\n\r\t]+?)(?=\s*(?:x\s*\d+|RM|\n|$))/i);
              if (vm1) {
                vName = vm1[1].trim();
              } else {
                const vm2 = nodeText.match(/(?:Model|Type|Jenis)[：:]\s*([^\n\r\t]+?)(?=\s*(?:x\s*\d+|RM|\n|$))/i);
                if (vm2) {
                  vName = vm2[1].trim();
                }
              }
            }

            if (!vName) {
              const textNodes = Array.from(node.querySelectorAll("p, span, div, em, small"));
              for (const el of textNodes) {
                let ct = (el.innerText || el.textContent || "").trim();
                if (!ct || ct.length < 2 || ct.length > 80) continue;
                if (/Buy\s*Again|Beli\s*Semula|Contact|Hubungi|Rate|Nilai|Refund|Shopee\s*Guarantee|Jaminan\s*Shopee|Preferred|Mall|Free\s*Shipping|Free\s*Return|Product\s*Image/i.test(ct)) continue;
                if (/^RM\s*[0-9\.\s,]+$/i.test(ct) || /^[x×\*]\s*\d+$/i.test(ct)) continue;

                const vm = ct.match(/(?:Variation|Variasi|Pilihan|Package|Color|Colour|Warna|规格|型号)[：:\s]*([^\n\r]+)/i) ||
                           ct.match(/(?:Model|Type|Jenis)[：:]\s*([^\n\r]+)/i);
                if (vm) {
                  vName = vm[1].trim();
                  break;
                } else if (/^[a-zA-Z0-9_\-\u4e00-\u9fa5\s\/\(\)\+（）【】、，\.:;]{2,60}$/.test(ct)) {
                  vName = ct;
                  break;
                }
              }
            }

            // 2. Title Extraction
            let pName = nameEl ? nameEl.textContent.trim().replace(/\s+/g, " ") : "";

            if (!pName) {
              const textAnchors = Array.from(node.querySelectorAll("a"))
                .map(a => (a.innerText || a.textContent || "").trim().replace(/\s+/g, " "))
                .filter(t => t.length > 5 && !/^(?:Product\s*Image|Image|Gambar\s*Produk|Foto|Item\s*Image|Buy\s*Again|Beli\s*Semula|Chat\s*Now)$/i.test(t));
              if (textAnchors.length > 0) {
                pName = textAnchors[0];
              }
            }

            const varPrefixMatch = nodeText.match(/(?:Variation|Variasi|Pilihan|Option)[：:\s]+/i);
            if (!pName && varPrefixMatch && varPrefixMatch.index > 8) {
              let candidateTitle = nodeText.substring(0, varPrefixMatch.index).trim().replace(/\s+/g, " ");
              candidateTitle = candidateTitle.replace(/^(?:Product\s*Image|Image)\s*/i, "").trim();
              if (candidateTitle.length >= 8) {
                pName = candidateTitle;
              }
            }

            if (!pName) {
              const textBlocks = Array.from(node.querySelectorAll("span, div, p, a, h4, h5"))
                .map(el => (el.innerText || el.textContent || "").trim().replace(/\s+/g, " "))
                .filter(t => {
                  if (t.length < 8 || t.length > 250) return false;
                  if (/^RM\s*[0-9\.\s,]+$/i.test(t)) return false;
                  if (/^[x×\*]\s*\d+$/i.test(t)) return false;
                  if (/^(?:Product\s*Image|Image|Gambar\s*Produk|Foto|Item\s*Image)$/i.test(t)) return false;
                  if (/^(?:Buy\s*Again|Beli\s*Semula|Contact\s*Seller|Hubungi\s*Penjual|Rate|Nilai|Return|Refund|Chat\s*Now)$/i.test(t)) return false;
                  if (/^(?:Completed|Selesai|To Ship|Untuk Dihantar|Cancelled|Dibatalkan)$/i.test(t)) return false;
                  if (/^(?:Variation|Variasi|Pilihan|Option|Model|Type|Color|Warna)[：:\s]*/i.test(t)) return false;
                  if (vName && t === vName) return false;
                  return true;
                });
              if (textBlocks.length > 0) {
                textBlocks.sort((a, b) => b.length - a.length);
                pName = textBlocks[0];
              }
            }

            // Filter action badge words
            if (/^(?:Buy\s*Again|Beli\s*Semula|Contact\s*Seller|Hubungi\s*Penjual|Rate|Nilai|Return\s*Refund|Batalkan\s*Pesanan)$/i.test(pName)) {
              return;
            }
            pName = pName.replace(/^(?:Preferred\+?|Shopee\s*Mall|Mall|Official\s*Store)\s*/i, "").trim();
            if (/^(?:Product\s*Image|Image|Gambar\s*Produk|Foto|Item\s*Image)$/i.test(pName)) {
              pName = "";
            }
            if (!pName) pName = `Shopee Item ${nIdx + 1}`;

            if (vName && pName && vName.includes(pName)) {
              vName = vName.replace(pName, "").replace(/^(?:Variation|Variasi|Pilihan|Option)[：:\s]*/i, "").trim();
            }

            // 3. Quantity Extraction
            let qty = 1.0;
            const multMatch = nodeText.match(/(?:^|[^\d\w])(?:x|×|\*)\s*(\d+)(?!\s*(?:mm|cm|m|g|kg|pcs|pc|v|w|a|mah|ah|hz|k|p|b|bit|mb|gb))/i);
            if (multMatch) {
              qty = parseFloat(multMatch[1]) || 1.0;
            } else if (qtyEl) {
              const qm = qtyEl.textContent.match(/x\s*([0-9]+(?:\.[0-9]+)?)/i) || qtyEl.textContent.match(/([0-9]+(?:\.[0-9]+)?)/);
              if (qm) qty = parseFloat(qm[1]) || 1.0;
            } else {
              const unitMatch = nodeText.match(/\b(\d+)\s*(?:pcs|pc|units?|buah|keping|件)\b/i);
              if (unitMatch) qty = parseFloat(unitMatch[1]) || 1.0;
            }

            // 4. Item Price Extraction (Original catalog item price)
            let originalPrice = 0.0;
            if (priceEl) {
              const pm = priceEl.textContent.match(/RM\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|[0-9]+\.?[0-9]*)/i) || priceEl.textContent.match(/([0-9]+\.?[0-9]*)/);
              if (pm) originalPrice = parseFloat(pm[1].replace(/,/g, "")) || 0.0;
            }
            if (originalPrice <= 0) {
              const nonStrikeElements = Array.from(node.querySelectorAll("*"))
                .filter(el => {
                  const tag = el.tagName.toLowerCase();
                  if (tag === "del" || tag === "s") return false;
                  const cls = (el.className || "").toString().toLowerCase();
                  if (cls.includes("strike") || cls.includes("original") || cls.includes("old-price")) return false;
                  const style = (el.getAttribute("style") || "").toLowerCase();
                  if (style.includes("line-through")) return false;
                  return true;
                });
              for (const el of nonStrikeElements) {
                if (el.children.length === 0 || el.children.length === 1) {
                  const m = (el.textContent || "").match(/RM\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|[0-9]+\.?[0-9]*)/i);
                  if (m) {
                    const candidate = parseFloat(m[1].replace(/,/g, ""));
                    if (candidate > 0) {
                      originalPrice = candidate;
                      break;
                    }
                  }
                }
              }
            }
            if (originalPrice <= 0) {
              const allNodePrices = Array.from(nodeText.matchAll(/RM\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|[0-9]+\.?[0-9]*)/gi))
                .map(m => parseFloat(m[1].replace(/,/g, "")))
                .filter(p => p > 0);
              if (allNodePrices.length > 0) {
                originalPrice = allNodePrices[allNodePrices.length - 1];
              }
            }

            let pId = "";
            let itemUrl = "";
            const validLink = linkEl || node.querySelector("a[href*='/product/'], a[href*='-i.']");
            if (validLink && validLink.href) {
              const href = validLink.href;
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
              unit_price: originalPrice,
              original_price: originalPrice,
              discount_amount: 0.0,
              line_total: Math.round(originalPrice * qty * 100) / 100,
              item_url: itemUrl,
              shop_name: shopName,
              order_time: orderTime,
              shipping_fee: shippingFee,
              order_status: status
            });
          });

          // Price derivation, discount calculation & bidirectional reconciliation
          if (items.length > 0) {
            const originalTotal = Math.round(items.reduce((sum, it) => sum + (it.original_price * it.quantity), 0) * 100) / 100;
            let discountAmount = 0.0;

            if (totalAmount > 0 && originalTotal > 0 && totalAmount < originalTotal) {
              // Order Total reflects platform/seller discount
              discountAmount = Math.round((originalTotal - totalAmount) * 100) / 100;
              const ratio = totalAmount / originalTotal;
              items.forEach(it => {
                it.unit_price = Math.round(it.original_price * ratio * 100) / 100;
                it.line_total = Math.round(it.unit_price * it.quantity * 100) / 100;
                it.discount_amount = Math.round((it.original_price * it.quantity - it.line_total) * 100) / 100;
              });
              // Ensure sum of line totals matches totalAmount exactly
              const lineSum = items.reduce((sum, it) => sum + it.line_total, 0);
              const diff = Math.round((totalAmount - lineSum) * 100) / 100;
              if (diff !== 0) {
                items[items.length - 1].line_total = Math.round((items[items.length - 1].line_total + diff) * 100) / 100;
                items[items.length - 1].unit_price = Math.round((items[items.length - 1].line_total / items[items.length - 1].quantity) * 100) / 100;
              }
            } else if (totalAmount > 0 && originalTotal <= 0) {
              const totalItemsQty = items.reduce((sum, it) => sum + (it.quantity || 1), 0);
              items.forEach(it => {
                it.unit_price = Math.round((totalAmount / (totalItemsQty || items.length)) * 100) / 100;
                it.original_price = it.unit_price;
                it.line_total = Math.round(it.unit_price * it.quantity * 100) / 100;
                it.discount_amount = 0.0;
              });
            } else if (totalAmount <= 0 && originalTotal > 0) {
              totalAmount = originalTotal;
              items.forEach(it => {
                it.line_total = Math.round(it.unit_price * it.quantity * 100) / 100;
                it.discount_amount = 0.0;
              });
            } else {
              items.forEach(it => {
                it.line_total = Math.round(it.unit_price * it.quantity * 100) / 100;
                it.discount_amount = 0.0;
              });
            }

            results.push({
              order_id: orderId,
              status: status,
              total_amount: Math.round(totalAmount * 100) / 100,
              original_amount: originalTotal > 0 ? originalTotal : Math.round(totalAmount * 100) / 100,
              discount_amount: discountAmount,
              currency: "MYR",
              shop_name: shopName,
              order_time: orderTime,
              shipping_fee: shippingFee,
              items: items
            });
          }
        } catch (err) {
          console.warn("[ShopeeAdapter] Error parsing order card:", err);
        }
      });

      return results;
    },

    async fetchOrdersViaApi(offset = 0, limit = 30) {
      if (typeof fetch !== "function") return null;
      const isShopeeDomain = window.location && window.location.hostname && window.location.hostname.includes("shopee.com");
      if (!isShopeeDomain) return null;

      const endpoints = [
        `/api/v4/order/get_order_list?limit=${limit}&offset=${offset}&list_type=3`,
        `/api/v4/order/get_order_list?limit=${limit}&offset=${offset}&list_type=7`,
        `/api/v4/order/get_order_list?limit=${limit}&offset=${offset}&list_type=8`,
        `/api/v4/order/get_order_list?limit=${limit}&offset=${offset}`,
        `/api/v4/order/get_order_list?limit=${limit}&offset=${offset}&list_type=0`,
        `/api/v4/order/get_all_order_and_item_list?limit=${limit}&offset=${offset}`
      ];
      for (const ep of endpoints) {
        try {
          const resp = await fetch(ep, { credentials: "include" });
          if (resp.ok) {
            const body = await resp.json();
            const list = body.data?.details_list || body.data?.orders || body.details_list || [];
            if (Array.isArray(list) && list.length > 0) {
              const results = [];
              for (const ord of list) {
                const orderId = String(ord.order_sn || ord.order_id || ord.info_card?.order_sn || ord.info_card?.order_id || "");
                if (!orderId) continue;

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
                  const candidateItemLists = [];
                  const groups = c.product_info?.item_groups || c.item_groups || [];
                  for (const g of groups) {
                    if (Array.isArray(g.items)) candidateItemLists.push(...g.items);
                  }
                  if (Array.isArray(c.product_info?.items)) candidateItemLists.push(...c.product_info.items);
                  if (Array.isArray(c.items)) candidateItemLists.push(...c.items);
                  if (Array.isArray(ord.items)) candidateItemLists.push(...ord.items);
                  if (Array.isArray(ord.item_list)) candidateItemLists.push(...ord.item_list);

                  for (const item of candidateItemLists) {
                    const pName = item.name || item.item_name || item.title || "";
                    if (!pName || /^(?:Product\s*Image|Image)$/i.test(pName)) continue;
                    const vName = item.model_name || item.variation_name || item.model || "";
                    const qty = Number(item.amount || item.quantity || item.count || 1);
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
                      unit_price: Math.round(uPrice * 100) / 100,
                      original_price: Math.round(uPrice * 100) / 100,
                      discount_amount: 0.0,
                      line_total: Math.round(uPrice * qty * 100) / 100,
                      item_url: itemUrl,
                      shop_name: shopName,
                      order_time: orderTime,
                      shipping_fee: shippingFee,
                      order_status: status
                    });
                  }
                }

                if (items.length > 0) {
                  results.push({
                    order_id: orderId,
                    status: status,
                    total_amount: Math.round(totalAmount * 100) / 100,
                    original_amount: Math.round(totalAmount * 100) / 100,
                    discount_amount: 0.0,
                    currency: "MYR",
                    shop_name: shopName,
                    order_time: orderTime,
                    shipping_fee: shippingFee,
                    items: items
                  });
                }
              }
              if (results.length > 0 && results.some(r => r.items && r.items.length > 0)) {
                return results;
              }
            }
          }
        } catch (e) {
          console.debug("[ShopeeAdapter] API fetch attempt failed:", e.message);
        }
      }
      return null;
    },

    async extract(payload) {
      const accountId = payload.account_id || "alansyling@gmail.com";
      const maxOrders = payload.max_orders || 100;
      console.log(`[ShopeeAdapter] Starting extraction for account: ${accountId}`);

      // Strategy 1: Anchor-based DOM Traversal FIRST (directly from rendered page)
      let orders = this.parseOrdersOnPage();

      // Strategy 2: Session API Direct Fetch (fallback only if DOM returns 0 orders)
      if (!orders || orders.length === 0) {
        orders = await this.fetchOrdersViaApi(0, maxOrders);
      }

      if (!orders || orders.length === 0) {
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
        task_id: payload.task_id || `task_shopee_${Date.now()}`,
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
        ".shopee-page-controller__next-btn:not(.shopee-button-outline--disabled)",
        ".shopee-icon-button--right:not([disabled])",
        "button[aria-label='Next Page']:not([disabled])",
        "button[aria-label='next page']:not([disabled])",
        "li.next:not(.disabled) button",
        "li.next:not(.disabled) a",
        "[class*='pagination-next']:not([class*='disabled'])"
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
        if (onProgress) onProgress(`正在解析 Shopee 第 ${p} 页订单...`);

        // DOM extraction first
        let orders = this.parseOrdersOnPage();
        if (!orders || orders.length === 0) {
          const offset = (p - 1) * 30;
          orders = await this.fetchOrdersViaApi(offset, 30);
        }

        const freshOrders = (orders || []).filter(o => !seenOrderIds.has(o.order_id));
        freshOrders.forEach(o => seenOrderIds.add(o.order_id));

        if (freshOrders.length > 0) {
          const batchId = `shopee_batch_auto_p${p}_${Date.now()}`;
          await core.submitBatch({
            batch_id: batchId,
            platform: "shopee",
            account_id: "alansyling@gmail.com",
            task_id: `task_auto_shopee_p${p}`,
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
          await new Promise(r => setTimeout(r, 2500));
        } else if (!orders || orders.length < 30) {
          if (onProgress) onProgress(`🏁 已到达最后一页。累计抓取入库 ${totalExtracted} 笔订单！`);
          break;
        } else {
          await new Promise(r => setTimeout(r, 1000));
        }
      }

      this.isAutoCrawling = false;
      return { pages: pagesCount, total_orders: totalExtracted };
    }
  };

  core.registerAdapter("shopee", ShopeeAdapter);

  let hudControl = null;
  if (window.top === window.self) {
    hudControl = core.mountFloatingHud({
      platform: "shopee",
      adapter: ShopeeAdapter,
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
      // 1. Primary: Parse DOM orders rendered on screen
      let orders = ShopeeAdapter.parseOrdersOnPage();

      // 2. Fallback: Only if DOM yields no orders
      if (!orders || orders.length === 0) {
        orders = await ShopeeAdapter.fetchOrdersViaApi(0, 30);
      }

      // Check quality: ensure real orders with items exist and not generic placeholder
      if (orders && orders.length > 0 && orders.some(o => o.items && o.items.length > 0 && o.items[0].product_name !== "Shopee Purchase Item" && o.items[0].product_name !== "Product Image")) {
        autoExtracted = true;
        console.log(`[ShopeeAdapter] Auto-extracted ${orders.length} orders on page load.`);
        const batchId = `shopee_batch_auto_${Date.now()}`;
        await core.submitBatch({
          batch_id: batchId,
          platform: "shopee",
          account_id: "alansyling@gmail.com",
          task_id: "task_auto_shopee",
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
      console.debug("[ShopeeAdapter] Auto-extract check:", e.message);
    }

    pollAttempts++;
    if (pollAttempts <= maxAttempts) {
      if (hudControl && hudControl.setStatus) {
        hudControl.setStatus("检测中", `正在等待订单加载... (${pollAttempts}/${maxAttempts})`);
      }
      setTimeout(attemptAutoExtract, 1500);
    } else {
      if (hudControl && hudControl.setStatus) {
        hudControl.setStatus("就绪", "页面已就绪。如未显示订单，请确认处于【购买历史】页并向下滚动。");
      }
    }
  }

  setTimeout(attemptAutoExtract, 1200);

  // Dynamic listener: whenever user scrolls or order cards load, auto-extract immediately
  let isChecking = false;
  async function triggerExtractDynamically() {
    if (autoExtracted || isChecking) return;
    isChecking = true;
    try {
      let orders = ShopeeAdapter.parseOrdersOnPage();
      if (!orders || orders.length === 0) {
        orders = await ShopeeAdapter.fetchOrdersViaApi(0, 30);
      }
      if (orders && orders.length > 0 && orders.some(o => o.items && o.items.length > 0 && o.items[0].product_name !== "Shopee Purchase Item" && o.items[0].product_name !== "Product Image")) {
        autoExtracted = true;
        console.log(`[ShopeeAdapter] Dynamically auto-extracted ${orders.length} orders.`);
        const batchId = `shopee_batch_auto_${Date.now()}`;
        await core.submitBatch({
          batch_id: batchId,
          platform: "shopee",
          account_id: "alansyling@gmail.com",
          task_id: "task_auto_shopee",
          orders: orders
        });
        if (hudControl && hudControl.setStatus) {
          hudControl.setStatus("自动完成", `⚡ 页面自动采集成功：已提取本页 <strong>${orders.length}</strong> 笔订单并安全入库！`);
        }
        if (window.top && window.top !== window.self) {
          window.top.postMessage({ type: "UUMA_HUD_AUTO_SUCCESS", count: orders.length }, "*");
        }
      }
    } catch (e) {
      console.debug("[ShopeeAdapter] Dynamic extract error:", e.message);
    } finally {
      isChecking = false;
    }
  }

  window.addEventListener("scroll", triggerExtractDynamically, { passive: true });
})();
