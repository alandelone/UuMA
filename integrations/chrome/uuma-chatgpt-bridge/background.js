"use strict";
const loops = new Map();
const bridge = "http://127.0.0.1:8787";

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function chatTab(create = false) {
  let tabs = await chrome.tabs.query({url: "https://chatgpt.com/*"});
  if (!tabs.length && create) {
    const tab = await chrome.tabs.create({url: "https://chatgpt.com/", active: true});
    return tab;
  }
  return tabs[0];
}
async function readyTab(url) {
  let tab = await chatTab(true);
  if (!tab || !tab.id) throw new Error("CHATGPT_TAB_UNAVAILABLE");
  if (tab.status !== "complete") {
    await new Promise(resolve => {
      const listener = (id, change) => {
        if (id === tab.id && change.status === "complete") {
          chrome.tabs.onUpdated.removeListener(listener); resolve();
        }
      };
      chrome.tabs.onUpdated.addListener(listener);
    });
  }
  if (url && tab.url !== url) {
    tab = await chrome.tabs.update(tab.id, {url, active: true});
    await new Promise(resolve => {
      const listener = (id, change) => {
        if (id === tab.id && change.status === "complete") {
          chrome.tabs.onUpdated.removeListener(listener); resolve();
        }
      };
      chrome.tabs.onUpdated.addListener(listener);
    });
  }
  return tab;
}
async function execute(command) {
  console.log("[UuMA Bridge] Executing command:", command.action, command.payload);
  const requested = command.payload?.url;
  const tab = await readyTab(requested);
  if (command.action === "open") {
    await chrome.tabs.update(tab.id, {active: true});
    return {url: tab.url};
  }
  let reply;
  try {
    reply = await chrome.tabs.sendMessage(tab.id, command);
  } catch (err) {
    console.warn("[UuMA Bridge] tabs.sendMessage failed, reloading ChatGPT tab and retrying...", err);
    await chrome.tabs.reload(tab.id);
    await new Promise(resolve => {
      const listener = (id, change) => {
        if (id === tab.id && change.status === "complete") {
          chrome.tabs.onUpdated.removeListener(listener); resolve();
        }
      };
      chrome.tabs.onUpdated.addListener(listener);
    });
    await sleep(2000);
    reply = await chrome.tabs.sendMessage(tab.id, command);
  }
  if (!reply?.ok) throw new Error(reply?.error || "EXTENSION_COMMAND_FAILED");
  return reply.value;
}
async function poll(alias, token) {
  if (loops.get(alias) === token) return;
  // A freshly paired token supersedes any in-flight loop using the old token.
  loops.set(alias, token);
  console.log("[UuMA Bridge] Starting poll loop for", alias);
  try {
    while (loops.get(alias) === token) {
      let response;
      try {
        response = await fetch(bridge + "/extension/poll", {method: "POST",
          headers: {"Content-Type": "application/json"}, body: JSON.stringify({alias, token})});
      } catch (_) { await sleep(2000); continue; }
      if (response.status === 401 || response.status === 403) return;
      if (!response.ok) { await sleep(3000); continue; }
      const command = await response.json();
      if (!command) continue;
      console.log("[UuMA Bridge] Received command from server:", command.action, command.id);
      let result;
      try { result = {ok: true, value: await execute(command)}; }
      catch (error) {
        console.error("[UuMA Bridge] Execution error:", error);
        result = {ok: false, error: error?.message || "EXTENSION_COMMAND_FAILED"};
      }
      try {
        await fetch(bridge + "/extension/result", {method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({alias, token, command_id: command.id, result})});
        console.log("[UuMA Bridge] Reported result for", command.id);
      } catch (err) {
        console.error("[UuMA Bridge] Failed to report result:", err);
      }
    }
  } finally {
    if (loops.get(alias) === token) loops.delete(alias);
    console.warn("[UuMA Bridge] Poll loop ended for", alias);
  }
}
async function wake() {
  const {accounts = {}} = await chrome.storage.local.get("accounts");
  Object.entries(accounts).forEach(([alias, token]) => poll(alias, token));
}
chrome.runtime.onMessage.addListener((message, _sender, respond) => {
  if (message.type === "pair") {
    chrome.storage.local.get("accounts").then(({accounts = {}}) => {
      accounts[message.value.alias] = message.value.token;
      return chrome.storage.local.set({accounts});
    }).then(wake).then(() => respond({ok: true}));
    return true;
  }
  if (message.type === "wake") wake();
  return false;
});
chrome.runtime.onStartup.addListener(wake);
chrome.runtime.onInstalled.addListener(wake);
wake();
