/**
 * UuMA Lab Bot Extension Service Worker
 * Coordinates native messaging host communication, task leases, and content script extraction.
 */

const NATIVE_HOST_NAME = "com.uuma.labbot";
let nativePort = null;
let currentTask = null;
let leaseTimer = null;
let commandPollTimer = null;

// Connect to native messaging host
function connectNativeHost() {
  if (nativePort) return nativePort;

  try {
    nativePort = chrome.runtime.connectNative(NATIVE_HOST_NAME);

    nativePort.onMessage.addListener((message) => {
      console.log("[ServiceWorker] Received from native host:", message);
      handleNativeMessage(message);
    });

    nativePort.onDisconnect.addListener(() => {
      const err = chrome.runtime.lastError ? chrome.runtime.lastError.message : "Disconnected";
      console.warn("[ServiceWorker] Native host disconnected:", err);
      nativePort = null;
      stopTimers();
      chrome.storage.local.set({ hostStatus: "DISCONNECTED", hostError: err });
    });

    chrome.storage.local.set({ hostStatus: "CONNECTED", hostError: null });
    startTimers();
    return nativePort;
  } catch (err) {
    console.error("[ServiceWorker] Failed to connect native host:", err);
    chrome.storage.local.set({ hostStatus: "ERROR", hostError: err.message });
    return null;
  }
}

// Send message to native host
function sendNativeRequest(action, payload = {}) {
  const port = connectNativeHost();
  if (!port) {
    return Promise.reject(new Error("Native host port is not connected."));
  }

  const requestId = "req_" + Date.now() + "_" + Math.random().toString(36).substring(2, 8);
  const message = {
    protocol_version: "1.0",
    request_id: requestId,
    action: action,
    payload: payload
  };

  port.postMessage(message);
  return Promise.resolve(requestId);
}

function startTimers() {
  stopTimers();
  // Poll commands every 5 seconds
  commandPollTimer = setInterval(pollPendingCommand, 5000);
  // Initial check
  pollPendingCommand();
}

function stopTimers() {
  if (commandPollTimer) clearInterval(commandPollTimer);
  if (leaseTimer) clearInterval(leaseTimer);
  commandPollTimer = null;
  leaseTimer = null;
}

function pollPendingCommand() {
  if (currentTask) return;
  sendNativeRequest("claim_command", { ttl_seconds: 60 });
}

function handleNativeMessage(msg) {
  if (!msg || !msg.success) return;

  const result = msg.result;
  if (result && result.command && result.command.command_id) {
    const cmd = result.command;
    currentTask = {
      task_id: cmd.task_id,
      command_id: cmd.command_id,
      fencing_token: cmd.fencing_token,
      lease_token: cmd.lease_token,
      action: cmd.action,
      payload: cmd.payload
    };
    chrome.storage.local.set({ currentTask });

    // Start lease renewal timer (every 25s for a 60s lease)
    if (leaseTimer) clearInterval(leaseTimer);
    leaseTimer = setInterval(renewActiveLease, 25000);

    // Dispatch command to relevant tabs
    dispatchCommandToTabs(cmd);
  }
}

function renewActiveLease() {
  if (!currentTask || !currentTask.lease_token) return;
  sendNativeRequest("renew_lease", {
    task_id: currentTask.task_id,
    lease_token: currentTask.lease_token,
    fencing_token: currentTask.fencing_token,
    ttl_seconds: 60
  });
}

function matchesPlatform(url, platform) {
  if (!url) return false;
  if (platform === "taobao") return url.includes("taobao.com") || url.includes("tmall.com");
  if (platform === "shopee") return url.includes("shopee.com.my");
  if (platform === "pdd") return url.includes("pinduoduo.com") || url.includes("yangkeduo.com");
  return false;
}

function dispatchCommandToTabs(cmd) {
  const platform = cmd.payload.platform || "shopee";

  chrome.tabs.query({}, (tabs) => {
    const matchingTabs = (tabs || []).filter(t => matchesPlatform(t.url, platform));

    if (matchingTabs.length === 0) {
      console.warn("[ServiceWorker] No matching tabs open for platform:", platform);
      sendNativeRequest("report_checkpoint", {
        task_id: cmd.task_id,
        lease_token: cmd.lease_token,
        fencing_token: cmd.fencing_token,
        checkpoint: { note: `Waiting for ${platform} tab to be opened by user` },
        status: "WAITING_FOR_BROWSER"
      });
      currentTask = null;
      if (leaseTimer) clearInterval(leaseTimer);
      return;
    }

    // Target the first matching tab
    const tabId = matchingTabs[0].id;
    chrome.tabs.sendMessage(tabId, {
      type: "EXECUTE_COMMAND",
      command: cmd
    }, (response) => {
      if (chrome.runtime.lastError) {
        console.log("[ServiceWorker] Content script not active on tab, injecting dynamically...", chrome.runtime.lastError.message);
        const scriptFile = platform === "taobao" ? "content/taobao.js" : (platform === "pdd" ? "content/pdd.js" : "content/shopee.js");
        if (chrome.scripting) {
          chrome.scripting.executeScript({
            target: { tabId: tabId },
            files: ["content/core.js", scriptFile]
          }, () => {
            setTimeout(() => {
              chrome.tabs.sendMessage(tabId, { type: "EXECUTE_COMMAND", command: cmd }, (retryRes) => {
                console.log("[ServiceWorker] Post-injection response:", retryRes);
              });
            }, 600);
          });
        }
      } else {
        console.log("[ServiceWorker] Content script response:", response);
      }
    });
  });
}


// Listen to messages from content scripts or popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "START_TASK") {
    sendNativeRequest("create_task", {
      platform: message.platform,
      account_id: message.account_id
    })
      .then((reqId) => {
        pollPendingCommand();
        sendResponse({ success: true, request_id: reqId });
      })
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  }

  if (message.type === "SUBMIT_BATCH") {
    // Content script submitting extracted batch
    sendNativeRequest("submit_batch", message.batch)
      .then((reqId) => {
        if (currentTask) {
          sendNativeRequest("report_checkpoint", {
            task_id: currentTask.task_id,
            lease_token: currentTask.lease_token,
            fencing_token: currentTask.fencing_token,
            checkpoint: { batch_id: message.batch.batch_id, orders_count: (message.batch.orders || []).length },
            status: "COMPLETED"
          });
          currentTask = null;
          if (leaseTimer) clearInterval(leaseTimer);
        }
        sendResponse({ success: true, request_id: reqId });
      })
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  }


  if (message.type === "REPORT_CHECKPOINT") {
    if (!currentTask) {
      sendResponse({ success: false, error: "No active task." });
      return;
    }
    sendNativeRequest("report_checkpoint", {
      task_id: currentTask.task_id,
      lease_token: currentTask.lease_token,
      fencing_token: currentTask.fencing_token,
      checkpoint: message.checkpoint,
      status: message.status || null
    })
      .then((reqId) => sendResponse({ success: true, request_id: reqId }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  }

  if (message.type === "GET_STATUS") {
    chrome.storage.local.get(["hostStatus", "hostError", "currentTask"], (items) => {
      sendResponse(items);
    });
    return true;
  }
});

// Auto-connect immediately on service worker boot, installation, and browser startup
chrome.runtime.onInstalled.addListener(() => {
  connectNativeHost();
});

chrome.runtime.onStartup.addListener(() => {
  connectNativeHost();
});

// When target tabs finish loading, re-check pending commands immediately
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && tab.url) {
    if (tab.url.includes("taobao.com") || tab.url.includes("shopee.com.my") || tab.url.includes("pinduoduo.com") || tab.url.includes("yangkeduo.com")) {
      pollPendingCommand();
    }
  }
});

// Immediate initial connection attempt
connectNativeHost();


