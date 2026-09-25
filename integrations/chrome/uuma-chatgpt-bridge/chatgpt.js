"use strict";
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const visible = element => Boolean(element && element.getClientRects().length);
const byLabel = label => [...document.querySelectorAll("button")].find(button =>
  (button.getAttribute("aria-label") || "").toLowerCase().includes(label.toLowerCase()) && visible(button));
const fail = code => { throw new Error(code); };
const currentUrl = () => {
  const url = new URL(location.href);
  if (url.origin === "https://chatgpt.com" && url.pathname.startsWith("/c/")) {
    url.search = "";
    url.hash = "";
  }
  return url.href;
};

async function waitForComposer(timeout = 15000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const composer = document.querySelector("#prompt-textarea") ||
      document.querySelector('[data-testid="prompt-textarea"]');
    if (visible(composer)) return composer;
    await pause(250);
  }
  return null;
}

function findProfileButton() {
  const selectors = [
    'button[data-testid="profile-button"]',
    'button[data-testid="accounts-profile-button"]',
    'button[data-testid*="user"]',
    'button[data-testid*="account"]',
    'nav button img',
    'nav [role="navigation"] button img',
    '[data-testid="navigation-menu-bottom"] button',
    'div[role="button"][data-testid*="profile"]'
  ];
  for (const sel of selectors) {
    try {
      const node = document.querySelector(sel);
      const btn = (node?.tagName === "BUTTON" || node?.getAttribute("role") === "button") ? node :
        node?.closest("button, [role='button']");
      if (visible(btn)) return btn;
    } catch (_) {}
  }
  for (const label of ["open profile menu", "profile", "个人资料", "账号", "帳号", "account", "user"]) {
    const btn = byLabel(label);
    if (btn) return btn;
  }
  return null;
}

function findAddButton() {
  for (const selector of [
    'button[data-testid="attach-menu-button"]',
    'button[data-testid="composer-plus-btn"]',
    'button[data-testid*="tool" i]',
    'button[data-testid*="attach" i]'
  ]) {
    const button = document.querySelector(selector);
    if (visible(button)) return button;
  }
  for (const label of ["add files and more", "add files", "add photos & files",
    "add photos and files", "open tools", "view tools", "添加文件", "附加",
    "attach", "tools", "工具"]) {
    const btn = byLabel(label);
    if (btn) return btn;
  }
  // The current ChatGPT composer renders the visible + control without a
  // stable label or test id. Resolve the nearest button just left of the
  // editable prompt area instead of depending on its presentation markup.
  const composer = document.querySelector("#prompt-textarea") ||
    document.querySelector('[data-testid="prompt-textarea"]');
  if (visible(composer)) {
    const box = composer.getBoundingClientRect();
    const candidates = [...document.querySelectorAll('button, [role="button"]')]
      .filter(visible)
      .map(element => ({element, box: element.getBoundingClientRect()}))
      .filter(item => {
        const centerY = item.box.top + item.box.height / 2;
        const label = (item.element.innerText || item.element.getAttribute("aria-label") || "")
          .trim().toLowerCase();
        return Math.abs(centerY - (box.top + box.height / 2)) < 45 &&
          item.box.right <= box.left + 30 && item.box.right >= box.left - 120 &&
          !/(send|voice|dictat|microphone)/i.test(label);
      })
      .sort((a, b) => Math.abs(a.box.right - box.left) - Math.abs(b.box.right - box.left));
    if (candidates.length) return candidates[0].element;
  }
  return null;
}

function openMenuItems() {
  const surfaces = [...document.querySelectorAll(
    '[role="menu"], [data-radix-popper-content-wrapper], [data-state="open"], [role="dialog"]'
  )].filter(visible);
  const root = surfaces.at(-1) || document;
  return [...root.querySelectorAll(
    'button, [role="menuitem"], [role="menuitemradio"], [role="option"], ' +
    '[data-radix-collection-item]'
  )].filter(visible);
}

function setComposerText(composer, value) {
  composer.focus();
  composer.textContent = value;
  composer.dispatchEvent(new InputEvent("input", {
    bubbles: true, inputType: "insertText", data: value
  }));
}

async function selectDeepResearchBySlash(composer) {
  if (!visible(composer)) return false;
  setComposerText(composer, "/Deepresearch");
  await pause(600);
  const candidates = [...document.querySelectorAll(
    '[role="option"], [role="menuitem"], [role="menuitemradio"], [data-radix-collection-item]'
  )].filter(visible);
  const option = candidates.find(element =>
    /deep[\s_-]?research/i.test(element.innerText || element.textContent || "")
  );
  if (!option) {
    setComposerText(composer, "");
    return false;
  }
  option.click();
  await pause(250);
  if (/\/Deepresearch/i.test(composer.textContent || "")) setComposerText(composer, "");
  return true;
}

async function getSessionUser() {
  try {
    const res = await fetch("/api/auth/session");
    if (res.ok) {
      const data = await res.json();
      if (data?.user?.email) return data.user;
    }
  } catch (_) {}
  return null;
}

async function verify(payload) {
  console.log("[UuMA Bridge chatgpt.js] verify called with", payload);
  // Method 1: Ask ChatGPT's own session endpoint (most reliable, zero DOM fragility)
  const sessionUser = await getSessionUser();
  if (sessionUser?.email) {
    console.log("[UuMA Bridge chatgpt.js] Verified via /api/auth/session:", sessionUser.email);
    if (payload.identity && sessionUser.email.toLowerCase() !== payload.identity.toLowerCase()) {
      console.log("[UuMA Bridge chatgpt.js] Email mismatch:", sessionUser.email, "vs", payload.identity);
      fail("WRONG_ACCOUNT");
    }
    return true;
  }

  // Method 2: DOM Profile button
  let profile = findProfileButton();
  if (!profile) {
    const sidebar = document.querySelector('button[aria-label*="sidebar" i], button[aria-label*="侧边栏" i]');
    if (sidebar && visible(sidebar)) {
      sidebar.click();
      await pause(350);
      profile = findProfileButton();
    }
  }
  if (profile) {
    profile.click(); await pause(400);
    const menu = document.querySelector('[role="menu"]') ||
                 document.querySelector('[data-radix-popper-content-wrapper]') ||
                 document.querySelector('div[data-state="open"]');
    const text = menu ? (menu.innerText || menu.textContent || "") : (document.body.innerText || "");
    console.log("[UuMA Bridge chatgpt.js] Profile menu text length:", text.length);
    document.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape", bubbles: true}));
    const emails = [...text.matchAll(/[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}/g)].map(match => match[0].toLowerCase());
    if (emails.length && !emails.includes(payload.identity.toLowerCase())) {
      console.log("[UuMA Bridge chatgpt.js] Email mismatch:", emails, "expected:", payload.identity);
      fail("WRONG_ACCOUNT");
    }
    if (payload.workspace.toLowerCase() !== "personal" &&
        !text.toLowerCase().split(/\r?\n/).map(x => x.trim()).includes(payload.workspace.toLowerCase())) {
      fail("WORKSPACE_UNVERIFIED");
    }
    return true;
  }

  // Method 3: Check if page shows login/signup buttons
  const buttons = [...document.querySelectorAll("button, a")].filter(visible);
  const loginBtn = buttons.find(b => {
    const txt = (b.innerText || b.getAttribute("aria-label") || "").trim().toLowerCase();
    return /^(log in|login|sign in|登录|登入)$/i.test(txt);
  });
  if (loginBtn) {
    console.log("[UuMA Bridge chatgpt.js] Login button visible on page");
    fail("AUTH_REQUIRED");
  }

  // Method 4: If prompt textarea is visible and no login button exists
  const composer = document.querySelector("#prompt-textarea") || document.querySelector('[data-testid="prompt-textarea"]');
  if (visible(composer)) {
    console.log("[UuMA Bridge chatgpt.js] Verified via visible composer without login button");
    return true;
  }

  console.log("[UuMA Bridge chatgpt.js] Could not verify authentication status");
  fail("AUTH_REQUIRED");
}
function findDeepResearchButton() {
  const selectors = [
    'button[data-testid*="deep-research"]',
    'button[data-testid*="deep_research"]',
    'button[aria-label*="deep research" i]',
    'button[aria-label*="深度研究" i]',
    '[role="button"][data-testid*="deep"]'
  ];
  for (const sel of selectors) {
    try {
      const el = document.querySelector(sel);
      if (visible(el)) return el;
    } catch (_) {}
  }
  return null;
}

async function capabilities(payload) {
  await verify(payload);
  const composer = await waitForComposer();
  const caps = ["chat"];

  // 1. Check direct buttons on page
  if (findDeepResearchButton()) {
    caps.push("deep_research");
  }

  // 2. Check attach / tools menu
  try {
    const add = findAddButton();
    if (add) {
      add.click(); await pause(300);
      const items = openMenuItems();
      const text = items.map(x => (x.innerText || x.textContent || x.getAttribute("aria-label") || "").trim());
      console.log("[UuMA Bridge chatgpt.js] Tools menu items:", text);
      if (text.some(value => /(Web search|Search|网页搜索|搜索)/i.test(value))) caps.push("search");
      if (text.some(value => /(deep[\s_-]?research|深度研究)/i.test(value)) && !caps.includes("deep_research")) {
        caps.push("deep_research");
      }
      document.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape", bubbles: true}));
    }
  } catch (_) {}

  // 3. Check model dropdown menu if deep_research not yet found
  if (!caps.includes("deep_research")) {
    try {
      const modelBtn = document.querySelector('button[data-testid*="model"]') ||
                       [...document.querySelectorAll("button")].find(b => visible(b) && /gpt-4|plus|pro/i.test(b.innerText || ""));
      if (modelBtn) {
        modelBtn.click(); await pause(300);
        const modelItems = [...document.querySelectorAll('[role="menuitem"], [role="option"]')];
        const modelTexts = modelItems.map(x => (x.innerText || x.textContent || "").trim());
        console.log("[UuMA Bridge chatgpt.js] Model menu items:", modelTexts);
        if (modelTexts.some(value => /(deep[\s_-]?research|深度研究)/i.test(value))) {
          caps.push("deep_research");
        }
        document.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape", bubbles: true}));
      }
    } catch (_) {}
  }

  // ChatGPT also exposes Deep Research through its documented slash command.
  // Selecting the suggestion proves access without sending a prompt or using quota.
  if (!caps.includes("deep_research") && await selectDeepResearchBySlash(composer)) {
    caps.push("deep_research");
  }

  if (!caps.includes("search")) {
    caps.push("search");
  }
  console.log("[UuMA Bridge chatgpt.js] Capabilities:", caps);
  return {capabilities: caps, url: currentUrl()};
}
async function prepare(payload) {
  await verify(payload);
  if (payload.parent_id && !payload.url) fail("CONVERSATION_UNAVAILABLE");
  const composer = await waitForComposer();
  if (!visible(composer)) fail("COMPOSER_UNAVAILABLE");
  if (payload.mode !== "chat") {
    let activated = false;
    // Direct button (e.g. Deep research icon)
    if (payload.mode === "deep_research") {
      const direct = findDeepResearchButton();
      if (direct) {
        direct.click(); await pause(250); activated = true;
      }
    }
    // Tools / attach menu
    if (!activated) {
      const add = findAddButton();
      if (add) {
        add.click(); await pause(300);
        const pattern = payload.mode === "search" ? /(Web search|Search|网页搜索|搜索)/i : /(deep[\s_-]?research|深度研究)/i;
        const items = openMenuItems();
        const option = items.find(x => pattern.test(x.innerText || x.textContent || ""));
        if (option && visible(option)) {
          option.click(); await pause(200); activated = true;
        } else {
          document.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape", bubbles: true}));
        }
      }
    }
    // Model menu
    if (!activated && payload.mode === "deep_research") {
      const modelBtn = document.querySelector('button[data-testid*="model"]') ||
                       [...document.querySelectorAll("button")].find(b => visible(b) && /gpt-4|plus|pro/i.test(b.innerText || ""));
      if (modelBtn) {
        modelBtn.click(); await pause(300);
        const modelItems = [...document.querySelectorAll('[role="menuitem"], [role="option"]')];
        const option = modelItems.find(x => /(deep[\s_-]?research|深度研究)/i.test(x.innerText || x.textContent || ""));
        if (option && visible(option)) {
          option.click(); await pause(200); activated = true;
        } else {
          document.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape", bubbles: true}));
        }
      }
    }
    if (!activated && payload.mode === "deep_research") {
      activated = await selectDeepResearchBySlash(composer);
    }
    if (!activated && payload.mode !== "search") fail("CAPABILITY_UNAVAILABLE");
  }
  return {url: currentUrl()};
}
async function send(payload) {
  const composer = await waitForComposer();
  if (!visible(composer)) fail("COMPOSER_UNAVAILABLE");
  setComposerText(composer, payload.prompt);
  await pause(200);
  const testIdBtn = document.querySelector('button[data-testid="send-button"]');
  const button = (visible(testIdBtn) && !testIdBtn.disabled) ? testIdBtn :
    (byLabel("send prompt") || byLabel("send message") || byLabel("send") || byLabel("发送"));
  if (!button || button.disabled) fail("SEND_UNVERIFIED");
  button.click();
  for (let index = 0; index < 40 && !location.pathname.startsWith("/c/"); index++) await pause(250);
  return {url: currentUrl()};
}
async function observe(payload) {
  await verify(payload);
  const users = [...document.querySelectorAll('[data-message-author-role="user"]')];
  const marker = `[UuMA consultation ${payload.request_id}]`;
  if (!users.some(node => node.innerText.includes(marker)) || !users.at(-1)?.innerText.includes(marker)) {
    fail("CONVERSATION_CHANGED");
  }
  if ([...document.querySelectorAll("button")].some(button =>
    /^(Stop|Stop generating)/i.test(
      (button.innerText || button.getAttribute("aria-label") || "").trim()
    ))) {
    return {pending: true, url: currentUrl()};
  }
  const answers = [...document.querySelectorAll('[data-message-author-role="assistant"]')];
  if (!answers.length) return {pending: true, url: currentUrl()};
  const answer = answers.at(-1); const text = answer.innerText.trim();
  if (!text) return {pending: true, url: currentUrl()};
  // Completion is confirmed by the bridge only after this text stays unchanged for
  // five seconds. Requiring ChatGPT's optional Copy control made finished answers
  // depend on a presentation detail that changes between page versions.
  const citations = [...answer.querySelectorAll("a[href]")].map(link => ({title: link.innerText, url: link.href}))
    .filter(link => /^https?:/.test(link.url));
  return {pending: false, answer: text, citations, conversation_url: currentUrl(),
    needs_input: text.includes("UUMA_NEEDS_INPUT")};
}
chrome.runtime.onMessage.addListener((command, _sender, respond) => {
  (async () => {
    const payload = command.payload || {};
    if (command.action === "verify") return capabilities(payload);
    if (command.action === "prepare") return prepare(payload);
    if (command.action === "send") return send(payload);
    if (command.action === "observe") return observe(payload);
    if (command.action === "stop") {
      const stop = [...document.querySelectorAll("button")].find(button => /^Stop/i.test(button.innerText));
      if (stop) stop.click(); return {url: currentUrl()};
    }
    if (command.action === "locate") return {url: currentUrl()};
    fail("UNKNOWN_EXTENSION_COMMAND");
  })().then(value => respond({ok: true, value}),
    error => respond({ok: false, error: error?.message || "EXTENSION_COMMAND_FAILED"}));
  return true;
});
