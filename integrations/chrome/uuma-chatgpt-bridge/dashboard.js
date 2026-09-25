"use strict";
window.addEventListener("message", event => {
  if (event.source !== window ||
      (event.origin !== "http://127.0.0.1:8787" && event.origin !== "http://localhost:8787")) return;
  try {
    if (typeof chrome === "undefined" || !chrome.runtime || !chrome.runtime.id) return;
    if (event.data?.type === "UUMA_CHATGPT_PAIR") {
      chrome.runtime.sendMessage({type: "pair", value: event.data}, reply => {
        try {
          if (chrome.runtime?.lastError) return;
          window.postMessage({type: "UUMA_CHATGPT_PAIR_ACK", ok: Boolean(reply?.ok)}, event.origin);
        } catch (_) {}
      });
    } else if (event.data?.type === "UUMA_CHATGPT_WAKE") {
      chrome.runtime.sendMessage({type: "wake"});
    }
  } catch (_) {}
});
