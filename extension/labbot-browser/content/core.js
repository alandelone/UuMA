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

