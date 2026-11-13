"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const {test} = require("node:test");
const source = fs.readFileSync(path.join(__dirname,
  "../integrations/chrome/uuma-chatgpt-bridge/chatgpt.js"), "utf8");

function fixture({missing = false, ambiguous = false, noChip = false, disabled = false} = {}) {
  const state = {menu: false, sent: 0, selected: 0, submittedText: null, clock: 0};
  const element = text => ({innerText: text, textContent: text,
    getClientRects: () => [{}], getAttribute: () => null, closest: () => null});
  const composer = {...element(""), focus() {}, dispatchEvent() {}};
  const add = {...element(""), getAttribute: name => name === "aria-label" ? "Add files and more" : null,
    click() {state.menu = true;}};
  const option = {...element("Deep research Get a detailed report"), disabled,
    click() {state.selected++; state.menu = false;
      if (!noChip) composer.textContent = "Deep research " + composer.textContent;}};
  const send = {...element(""), getAttribute: name => name === "aria-label" ? "Send" : null,
    click() {state.sent++; state.submittedText = composer.textContent;
      location.pathname = "/c/real-report"; location.href = "https://chatgpt.com/c/real-report";}};
  const location = {href: "https://chatgpt.com/", pathname: "/", origin: "https://chatgpt.com"};
  const document = {
    querySelector(selector) {
      if (selector === 'button[data-testid="send-button"]') return send;
      return null;
    },
    querySelectorAll(selector) {
      if (selector.startsWith("#prompt-textarea,")) return [composer];
      if (selector === "button") return [add, send,
        ...(state.menu && !missing ? [option, ...(ambiguous ? [{...option}] : [])] : [])];
      return [];
    },
  };
  class Clock extends Date {static now() {state.clock += 100; return state.clock;}}
  const context = vm.createContext({document, location, URL, console, Date: Clock,
    setTimeout: callback => {callback();},
    InputEvent: class {constructor(type, options) {this.type = type; Object.assign(this, options);}},
    chrome: {runtime: {onMessage: {addListener() {}}}},
  });
  vm.runInContext(source, context);
  return {state, composer, send: prompt => {
    context.payload = {prompt, request_id: "fixture-deep"};
    return vm.runInContext("send(payload)", context);
  }};
}

test("Deep Research selects native chip after filling and submits once", async () => {
  const f = fixture();
  const result = await f.send("/Deepresearch [UuMA consultation fixture-deep] Allium fistulosum evidence");
  assert.equal(f.state.selected, 1);
  assert.equal(f.state.sent, 1);
  assert.equal(result.mode_selection_verified, true);
  assert.equal(result.mode, "deep_research");
  assert.match(f.state.submittedText, /^Deep research \[UuMA consultation fixture-deep\]/);
  assert.doesNotMatch(f.state.submittedText, /\/Deepresearch/);
});

test("plain ordinary prompt does not select a research mode", async () => {
  const f = fixture();
  await f.send("[UuMA consultation fixture-search] Ordinary bounded search");
  assert.equal(f.state.selected, 0);
  assert.equal(f.state.sent, 1);
});

test("missing research tool cannot silently send an ordinary prompt", async () => {
  const f = fixture({missing: true});
  await assert.rejects(f.send("/Deepresearch Located evidence"), /CAPABILITY_UNAVAILABLE/);
  assert.equal(f.state.sent, 0);
});

test("disabled research option cannot be submitted", async () => {
  const f = fixture({disabled: true});
  await assert.rejects(f.send("/Deepresearch Located evidence"), /CAPABILITY_UNAVAILABLE/);
  assert.equal(f.state.sent, 0);
});

test("ambiguous research options fail without selecting or sending", async () => {
  const f = fixture({ambiguous: true});
  await assert.rejects(f.send("/Deepresearch Located evidence"), /RESEARCH_MODE_AMBIGUOUS/);
  assert.equal(f.state.selected, 0);
  assert.equal(f.state.sent, 0);
});

test("clicking without activating the native chip cannot submit", async () => {
  const f = fixture({noChip: true});
  await assert.rejects(f.send("/Deepresearch Located evidence"), /RESEARCH_MODE_UNVERIFIED/);
  assert.equal(f.state.sent, 0);
});
