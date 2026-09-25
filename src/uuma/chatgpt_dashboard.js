"use strict";
let csrf = "";
const el = (tag, text) => { const x = document.createElement(tag); if (text) x.textContent = text; return x; };
async function api(path, body) {
  const response = await fetch(path, {method: body === undefined ? "GET" : "POST",
    headers: {"Content-Type": "application/json", "X-Bridge-CSRF": csrf},
    body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
    error.status = response.status;
    throw error;
  }
  return data;
}
function showError(error, target = "#notice") {
  const unauthorized = error.status === 401;
  const message = unauthorized
    ? "This page is not authorized. Open ChatGPT Bridge from the Desktop or Start menu, then use Add account there."
    : error.message;
  document.querySelector(target).textContent = message;
  document.querySelector("#notice").textContent = message;
  if (unauthorized) document.querySelectorAll("form input, form select, form button")
    .forEach(control => { control.disabled = true; control.dataset.locked = "true"; });
}
function button(label, action) {
  const b = el("button", label); b.type = "button";
  b.onclick = async () => { b.disabled = true; try { await action(); await refresh(); }
    catch(e) { showError(e); } finally { b.disabled = false; } };
  return b;
}
async function connectExtension(alias) {
  const pairing = await api("/human/accounts/" + encodeURIComponent(alias) +
    "/extension-pair", {});
  const acknowledged = await new Promise(resolve => {
    let settled = false;
    const finish = value => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      clearInterval(retry);
      window.removeEventListener("message", onMessage);
      resolve(value);
    };
    function onMessage(event) {
      if (event.data?.type === "UUMA_CHATGPT_PAIR_ACK") {
        finish(Boolean(event.data.ok));
      }
    }
    window.addEventListener("message", onMessage);
    const send = () => window.postMessage(
      {type: "UUMA_CHATGPT_PAIR", ...pairing}, location.origin
    );
    const retry = setInterval(send, 250);
    const timer = setTimeout(() => finish(false), 5000);
    send();
  });
  if (!acknowledged) throw new Error("Extension did not respond in this Chrome profile.");
  await new Promise(resolve => setTimeout(resolve, 600));
}
async function refresh() {
  const data = await api("/human/state"); csrf = data.csrf;
  document.querySelector("#notice").textContent = data.accounts.length ? "" : "Add your first account to begin setup.";
  const accounts = document.querySelector("#accounts"); accounts.replaceChildren();
  data.accounts.forEach(a => {
    const row = el("div"); row.className = "row";
    row.append(el("strong", a.alias + " · " + a.status), el("p", a.identity + " / " + a.workspace));
    row.append(el("small", "Verified capabilities: " + JSON.parse(a.capabilities).join(", ")));
    const confirmed = JSON.parse(a.confirmed_capabilities || "[]");
    const deepConfirmed = confirmed.includes("deep_research");
    row.append(button(
      deepConfirmed ? "Remove Deep Research confirmation" : "Confirm Deep Research access",
      () => api("/human/accounts/" + encodeURIComponent(a.alias) + "/capabilities", {
        capability: "deep_research", enabled: !deepConfirmed
      })
    ));
    const browserLine = el("p");
    const profile = el("select"); profile.setAttribute("aria-label", a.alias + " Chrome profile");
    const dedicated = el("option", "Dedicated UuMA browser");
    dedicated.value = ""; profile.append(dedicated);
    data.chrome_profiles.forEach(item => {
      const suffix = item.email ? " / " + item.email : "";
      const option = el("option", `${item.directory} / ${item.name}${suffix}`);
      option.value = item.directory; profile.append(option);
    });
    profile.value = a.chrome_profile || "";
    browserLine.append(el("span", "Chrome profile "), profile,
      button("Save browser", () => api("/human/accounts/" + encodeURIComponent(a.alias) +
        "/browser", {profile: profile.value})));
    row.append(browserLine);
    if (a.chrome_profile) {
      row.append(el("small", "Normal Chrome is for human or extension control. UuMA never copies its cookies."));
      row.append(button("Open selected Chrome profile", () => api("/human/accounts/" +
        encodeURIComponent(a.alias), {action: "open"})));
      if (a.extension_connected) {
        const badge = el("span", "🟢 Extension connected");
        badge.className = "badge-connected";
        row.append(badge);
        row.append(button("Verify extension connection", async () => {
          window.postMessage({type: "UUMA_CHATGPT_WAKE"}, location.origin);
          await api("/human/accounts/" + encodeURIComponent(a.alias), {action: "verify"});
          for (let i = 0; i < 8; i++) {
            await new Promise(r => setTimeout(r, 1000));
            const state = await api("/human/state");
            const acc = state.accounts.find(x => x.alias === a.alias);
            if (acc && acc.action === null) break;
          }
        }));
      } else {
        const guide = el("div"); guide.className = "extension-guide";
        guide.append(el("strong", "Extension Connection Required for " + a.chrome_profile));
        const list = el("ol");
        const s1 = el("li"); s1.append(el("span", "Click \"Open selected Chrome profile\" above to launch " + a.chrome_profile + "."));
        const s2 = el("li"); s2.append(el("span", "In " + a.chrome_profile + ", navigate to "), el("code", "chrome://extensions"), el("span", ", turn on Developer mode, and click Load unpacked."));
        const s3 = el("li"); s3.append(el("span", "Select folder: "), el("code", data.extension_path), el("span", " "));
        const copyBtn = el("button", "Copy path"); copyBtn.type = "button"; copyBtn.className = "btn-sm";
        copyBtn.onclick = async () => {
          try {
            await navigator.clipboard.writeText(data.extension_path);
            copyBtn.textContent = "Copied!";
            setTimeout(() => { copyBtn.textContent = "Copy path"; }, 2000);
          } catch (_) { prompt("Extension path:", data.extension_path); }
        };
        s3.append(copyBtn);
        const s4 = el("li"); s4.append(el("span", "Make sure ChatGPT is logged in as " + a.identity + " in " + a.chrome_profile + "."));
        const s5 = el("li"); s5.append(el("span", "Open this dashboard inside " + a.chrome_profile + " (click \"Open dashboard in " + a.chrome_profile + "\" below), then click \"Connect UuMA Chrome extension\"."));
        list.append(s1, s2, s3, s4, s5); guide.append(list);
        const openDashBtn = button("Open dashboard in " + a.chrome_profile, () => api("/human/accounts/" +
          encodeURIComponent(a.alias) + "/open-dashboard", {}));
        const connectBtn = button("Connect UuMA Chrome extension", () => connectExtension(a.alias));
        guide.append(openDashBtn, connectBtn);
        row.append(guide);
      }
    } else {
      row.append(button("Open browser for human sign-in", () => api("/human/accounts/" +
        encodeURIComponent(a.alias), {action: "open"})),
      button("Verify completed sign-in", () => api("/human/accounts/" +
        encodeURIComponent(a.alias), {action: "verify"})));
    }
    row.append(button(a.enabled ? "Disable" : "Enable", () => api("/human/accounts/" +
      encodeURIComponent(a.alias), {action: a.enabled ? "disable" : "enable"})));
    accounts.append(row);
  });
  const routes = document.querySelector("#routes"); routes.replaceChildren();
  Object.entries(data.permissions).forEach(([agent, modes]) => {
    const row = el("div", agent + " · " + modes.join(", ")); row.className = "row";
    const select = el("select"); select.setAttribute("aria-label", agent + " account");
    const unassigned = el("option", "Unassigned"); unassigned.value = ""; select.append(unassigned);
    data.accounts.forEach(a => { const option = el("option", a.alias); option.value = a.alias; select.append(option); });
    select.value = data.routes.find(r => r.agent === agent)?.account || "";
    row.append(select, button("Save", () => api("/human/routes", {agent, account: select.value}))); routes.append(row);
  });
  if (data.accounts.length === 1) routes.prepend(el("p", "Only one account is registered, so main is the only assignable account. Choose Unassigned to disable an agent route."));
  const threads = document.querySelector("#threads"); threads.replaceChildren();
  data.threads.forEach(t => { const p = el("p", `${t.agent} / ${t.project} / ${t.thread} · ${t.account} `);
    p.append(el("code", t.url)); threads.append(p); });
  const requests = document.querySelector("#requests"); requests.replaceChildren();
  data.requests.forEach(r => {
    const item = el("details"), summary = el("summary", `${r.agent} / ${r.project} · ${r.mode} · ${r.status}`);
    item.append(summary, el("p", r.id), el("p", r.error || ""), el("pre", r.payload.prompt));
    if (r.result?.answer) item.append(el("pre", r.result.answer));
    if (r.url) item.append(el("p", r.url));
    if (["PAUSED", "NEEDS_REVIEW"].includes(r.status)) item.append(button("Resume observation", () => api(`/human/requests/${r.id}`, {action:"resume"})));
    if (!["COMPLETED", "FAILED", "CANCELLED"].includes(r.status)) item.append(button("Cancel", () => api(`/human/requests/${r.id}`, {action:"cancel"})));
    requests.append(item);
  });
}
for (const [id, path] of [["add-account", "/human/accounts"], ["bind-thread", "/human/threads"]]) {
  document.getElementById(id).onsubmit = async event => { event.preventDefault();
    const submit = event.submitter;
    const original = submit?.textContent;
    if (submit) { submit.disabled = true; submit.textContent = id === "add-account" ? "Adding…" : "Saving…"; }
    if (id === "add-account") document.querySelector("#add-account-notice").textContent = "";
    try { await api(path, Object.fromEntries(new FormData(event.target))); await refresh(); }
    catch(e) { showError(e, id === "add-account" ? "#add-account-notice" : "#notice"); }
    finally { if (submit && submit.dataset.locked !== "true") { submit.disabled = false; submit.textContent = original; } }
  };
}
(async () => {
  try {
    const token = new URLSearchParams(location.hash.slice(1)).get("token");
    const connect = new URLSearchParams(location.search).get("connect");
    history.replaceState(null, "", "/");
    if (token) csrf = (await api("/human/login", {token})).csrf;
    if (connect) await connectExtension(connect);
    // Wake an already-paired extension after the on-demand bridge is restarted.
    // The content script ignores this message in browsers where the extension is absent.
    window.postMessage({type: "UUMA_CHATGPT_WAKE"}, location.origin);
    await refresh();
    setInterval(async () => {
      if (document.querySelector("input:focus,select:focus,details[open]")) return;
      window.postMessage({type: "UUMA_CHATGPT_WAKE"}, location.origin);
      try { await refresh(); } catch(e) { showError(e); }
    }, 10000);
  } catch(e) { showError(e); }
})();
