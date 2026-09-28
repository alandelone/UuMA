/**
 * UuMA Lab Bot - Core Content Script Framework
 * Provides base abstractions, DOM helpers, and IPC with service worker.
 */

window.UuMAExtractionCore = {
  adapters: {},

  registerAdapter(platform, adapter) {
    this.adapters[platform] = adapter;
    console.log(`[UuMA Core] Registered adapter for: ${platform}`);
  },

  submitBatch(batch) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({
        type: "SUBMIT_BATCH",
        batch: batch
      }, (response) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else if (response && response.success) {
          resolve(response);
        } else {
          reject(new Error((response && response.error) || "Batch submission failed"));
        }
      });
    });
  },

  reportCheckpoint(checkpoint, status = null) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({
        type: "REPORT_CHECKPOINT",
        checkpoint: checkpoint,
        status: status
      }, (response) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve(response);
        }
      });
    });
  },

  cleanText(element) {
    if (!element) return "";
    return element.textContent.replace(/\s+/g, " ").trim();
  },

  parsePrice(text) {
    if (!text) return 0.0;
    const cleaned = text.replace(/[^0-9.]/g, "");
    const val = parseFloat(cleaned);
    return isNaN(val) ? 0.0 : val;
  },

  mountFloatingHud(config) {
    if (window.top !== window.self) return null;
    if (document.getElementById("uuma-hud-root")) return null;

    const adapter = config.adapter;
    const hud = document.createElement("div");
    hud.id = "uuma-hud-root";
    hud.style.cssText = `
      position: fixed;
      bottom: 24px;
      right: 24px;
      width: 290px;
      background: #0f172a;
      color: #f8fafc;
      border: 1px solid #334155;
      border-radius: 10px;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4), 0 8px 10px -6px rgba(0, 0, 0, 0.3);
      z-index: 2147483647;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 12px;
      overflow: hidden;
      transition: all 0.2s ease;
    `;

    hud.innerHTML = `
      <div id="uuma-hud-header" style="display:flex; justify-content:space-between; align-items:center; padding:8px 12px; background:#1e293b; border-bottom:1px solid #334155; user-select:none; cursor:pointer;">
        <div style="display:flex; align-items:center; gap:6px;">
          <span style="font-size:14px;">🤖</span>
          <strong style="color:#38bdf8; font-size:12px;">UuMA 采集助手</strong>
        </div>
        <div style="display:flex; align-items:center; gap:6px;">
          <span id="uuma-hud-badge" style="font-size:10px; background:#0284c7; color:#fff; padding:2px 6px; border-radius:4px;">检测中</span>
          <span id="uuma-hud-toggle-btn" style="color:#94a3b8; font-size:13px; font-weight:bold; cursor:pointer;">−</span>
        </div>
      </div>
      <div id="uuma-hud-body" style="padding:10px 12px; display:flex; flex-direction:column; gap:8px;">
        <div style="display:flex; gap:6px;">
          <button id="uuma-hud-btn-extract" style="flex:1; background:#0284c7; color:#fff; border:none; border-radius:6px; padding:6px 4px; font-size:11px; font-weight:600; cursor:pointer;">⚡ 抓取本页</button>
          <button id="uuma-hud-btn-autopage" style="flex:1.2; background:#2563eb; color:#fff; border:none; border-radius:6px; padding:6px 4px; font-size:11px; font-weight:600; cursor:pointer;">⏩ 自动连抓多页</button>
        </div>
        <button id="uuma-hud-btn-stop" style="display:none; background:#ef4444; color:#fff; border:none; border-radius:6px; padding:6px; font-size:11px; font-weight:600; cursor:pointer;">⏹ 停止翻页采集</button>
        ${config.hasExport ? '<button id="uuma-hud-btn-export" style="background:#ff5000; color:#fff; border:none; border-radius:6px; padding:6px; font-size:11px; font-weight:600; cursor:pointer;">📋 点击淘宝【导出订单】</button>' : ''}
        <div id="uuma-hud-log" style="background:#020617; border:1px solid #1e293b; border-radius:6px; padding:6px 8px; font-size:11px; color:#cbd5e1; max-height:80px; overflow-y:auto; line-height:1.4;">
          正在初始化并检测订单卡片...
        </div>
      </div>
    `;

    document.body.appendChild(hud);

    const logEl = hud.querySelector("#uuma-hud-log");
    const badgeEl = hud.querySelector("#uuma-hud-badge");
    const bodyEl = hud.querySelector("#uuma-hud-body");
    const btnToggle = hud.querySelector("#uuma-hud-toggle-btn");
    const btnExtract = hud.querySelector("#uuma-hud-btn-extract");
    const btnAutoPage = hud.querySelector("#uuma-hud-btn-autopage");
    const btnStop = hud.querySelector("#uuma-hud-btn-stop");
    const btnExport = hud.querySelector("#uuma-hud-btn-export");

    let isCollapsed = false;
    hud.querySelector("#uuma-hud-header").addEventListener("click", () => {
      isCollapsed = !isCollapsed;
      bodyEl.style.display = isCollapsed ? "none" : "flex";
      btnToggle.textContent = isCollapsed ? "+" : "−";
    });

    const setStatus = (status, text) => {
      if (badgeEl) {
        badgeEl.textContent = status;
        badgeEl.style.transition = "all 0.25s ease";
        if (status === "自动完成" || status === "完成" || status === "成功") {
          badgeEl.style.background = "#16a34a"; // Vivid Green
          badgeEl.style.color = "#ffffff";
          badgeEl.style.fontWeight = "bold";
          badgeEl.style.boxShadow = "0 0 8px rgba(22, 163, 74, 0.6)";
        } else if (status === "检测中" || status === "抓取中" || status === "翻页中") {
          badgeEl.style.background = "#0284c7"; // Blue
          badgeEl.style.color = "#ffffff";
          badgeEl.style.fontWeight = "bold";
          badgeEl.style.boxShadow = "none";
        } else if (status === "错误" || status === "失败") {
          badgeEl.style.background = "#ef4444"; // Red
          badgeEl.style.color = "#ffffff";
          badgeEl.style.fontWeight = "bold";
          badgeEl.style.boxShadow = "none";
        } else if (status === "未检出" || status === "提示" || status === "已停止") {
          badgeEl.style.background = "#d97706"; // Amber
          badgeEl.style.color = "#ffffff";
          badgeEl.style.fontWeight = "normal";
          badgeEl.style.boxShadow = "none";
        } else {
          badgeEl.style.background = "#334155"; // Neutral gray for '就绪'
          badgeEl.style.color = "#94a3b8";
          badgeEl.style.fontWeight = "normal";
          badgeEl.style.boxShadow = "none";
        }
      }
      if (text && logEl) {
        logEl.innerHTML = text;
        logEl.scrollTop = logEl.scrollHeight;
      }
    };

    window.addEventListener("message", (ev) => {
      if (ev.data && ev.data.type === "UUMA_HUD_AUTO_SUCCESS") {
        setStatus("自动完成", `⚡ 页面自动采集成功：已提取 <strong>${ev.data.count}</strong> 笔订单并安全入库！`);
      }
    });

    btnExtract.addEventListener("click", async () => {
      btnExtract.disabled = true;
      setStatus("抓取中", "正在抓取当前页面 DOM 订单...");
      try {
        const res = await adapter.extract({ task_id: "task_hud_" + Date.now() });
        const count = res.orders_extracted !== undefined ? res.orders_extracted : (res.extracted_count || 0);
        if (count > 0) {
          setStatus("成功", `✔ 本页抓取完成！共 <strong>${count}</strong> 笔订单已回传入库 (lab.db)`);
        } else {
          setStatus("未检出", res.note || "未在当前页面检测到展开的订单卡片。");
        }
      } catch (err) {
        setStatus("错误", `<span style="color:#f87171;">抓取失败: ${err.message}</span>`);
      } finally {
        btnExtract.disabled = false;
      }
    });

    btnAutoPage.addEventListener("click", async () => {
      if (!adapter.autoCrawlPages) {
        setStatus("不支持", "当前平台暂未配置自动连续翻页。");
        return;
      }
      btnAutoPage.disabled = true;
      btnExtract.disabled = true;
      btnStop.style.display = "block";
      setStatus("翻页中", "开始自动连续翻页采集...");

      try {
        const res = await adapter.autoCrawlPages(5, (progressText) => {
          setStatus("翻页中", progressText);
        });
        setStatus("完成", `🎉 翻页采集完成！共处理 <strong>${res.pages}</strong> 页，提取 <strong>${res.total_orders}</strong> 笔订单入库。`);
      } catch (err) {
        setStatus("错误", `<span style="color:#f87171;">翻页出错: ${err.message}</span>`);
      } finally {
        btnAutoPage.disabled = false;
        btnExtract.disabled = false;
        btnStop.style.display = "none";
      }
    });

    btnStop.addEventListener("click", () => {
      if (adapter.isAutoCrawling) {
        adapter.isAutoCrawling = false;
        setStatus("已停止", "用户已中断自动翻页。");
      }
    });

    if (btnExport && adapter.clickExportButton) {
      btnExport.addEventListener("click", () => {
        const res = adapter.clickExportButton();
        if (res.success) {
          setStatus("导出中", "✔ " + res.message);
        } else {
          setStatus("提示", res.error);
        }
      });
    }

    return { setStatus };
  }
};

// Listen for execution commands from service worker
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "EXECUTE_COMMAND") {
    const cmd = message.command;
    const platform = (cmd.payload && cmd.payload.platform) || "shopee";
    const adapter = window.UuMAExtractionCore.adapters[platform];

    if (!adapter) {
      sendResponse({ success: false, error: `No adapter registered for platform: ${platform}` });
      return;
    }

    if (cmd.action === "EXTRACT") {
      adapter.extract(cmd.payload)
        .then((res) => sendResponse({ success: true, result: res }))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;
    } else if (cmd.action === "AUTO_CRAWL") {
      if (adapter.autoCrawlPages) {
        adapter.autoCrawlPages(cmd.payload.max_pages || 5, (status) => {
          console.log("[AutoCrawl Progress]", status);
        })
          .then((res) => sendResponse({ success: true, result: res }))
          .catch((err) => sendResponse({ success: false, error: err.message }));
        return true;
      } else {
        sendResponse({ success: false, error: "Adapter does not support auto crawl." });
      }
    } else if (cmd.action === "PAUSE") {
      if (adapter.pause) adapter.pause();
      sendResponse({ success: true, paused: true });
    } else if (cmd.action === "RESUME") {
      if (adapter.resume) adapter.resume();
      sendResponse({ success: true, resumed: true });
    } else if (cmd.action === "CLICK_EXPORT") {
      if (adapter.clickExportButton) {
        const res = adapter.clickExportButton();
        sendResponse({ success: res.success, result: res });
      } else {
        sendResponse({ success: false, error: "Current adapter does not support export button click." });
      }
      return true;
    }
  }
});

