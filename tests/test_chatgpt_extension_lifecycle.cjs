"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const {test} = require("node:test");

const source = fs.readFileSync(path.join(__dirname,
  "../integrations/chrome/uuma-chatgpt-bridge/background.js"), "utf8");
const flush = () => new Promise(resolve => setImmediate(resolve));
function gate() {
  let resolve;
  const promise = new Promise(done => {resolve = done;});
  return {promise, resolve};
}
async function setup() {
  const state = {accounts: {work: "fixture-token"}, reads: 0, timers: new Map(),
    polls: [], results: [], sends: 0, tabReply: gate()};
  let timerId = 0;
  const context = {
    console: {log() {}, warn() {}, error() {}},
    setTimeout, clearTimeout,
    setInterval(callback, delay) {state.timers.set(++timerId, {callback, delay}); return timerId;},
    clearInterval(id) {state.timers.delete(id);},
    chrome: {
      storage: {local: {
        async get() {state.reads++; return {accounts: {...state.accounts}};},
        async set({accounts}) {state.accounts = accounts;},
      }},
      runtime: {onMessage: {addListener() {}}, onStartup: {addListener() {}},
        onInstalled: {addListener() {}}},
      tabs: {
        async query() {return [{id: 7, status: "complete", url: "https://chatgpt.com/"}];},
        async sendMessage() {state.sends++; return state.tabReply.promise;},
      },
    },
    async fetch(url, options) {
      if (url.endsWith("/extension/result")) {
        state.results.push(JSON.parse(options.body));
        return {ok: true};
      }
      const pending = gate();
      state.polls.push({...pending, body: JSON.parse(options.body)});
      return pending.promise;
    },
  };
  vm.createContext(context);
  vm.runInContext(source + "\nglobalThis.api={wake,loops,execute};", context);
  await flush();
  return {state, api: context.api};
}

test("paired idle polling refreshes extension activity without a dashboard", async () => {
  const {state} = await setup();
  assert.equal(state.polls.length, 1);
  assert.equal(state.timers.size, 1);
  const timer = [...state.timers.values()][0];
  assert.equal(timer.delay, 20_000);
  const before = state.reads;
  timer.callback(); await flush();
  assert.equal(state.reads, before + 1);
  assert.equal(state.polls.length, 1);
});

test("repeated wakes do not duplicate pollers or activity timers", async () => {
  const {state, api} = await setup();
  await api.wake(); await api.wake(); await flush();
  assert.equal(state.polls.length, 1);
  assert.equal(state.timers.size, 1);
});

test("rejected pairing stops polling and releases the activity timer", async () => {
  const {state, api} = await setup();
  state.polls[0].resolve({status: 403}); await flush();
  assert.equal(api.loops.size, 0);
  assert.equal(state.timers.size, 0);
});

test("superseded token cannot remove the replacement poller or its timer", async () => {
  const {state, api} = await setup();
  state.accounts.work = "rotated-fixture-token";
  await api.wake(); await flush();
  assert.equal(state.polls.length, 2);
  state.polls[0].resolve({status: 401}); await flush();
  assert.equal(api.loops.get("work"), "rotated-fixture-token");
  assert.equal(state.timers.size, 1);
});

test("activity continues through a long page command and reports its result once", async () => {
  const {state} = await setup();
  state.polls[0].resolve({ok: true, status: 200, async json() {
    return {id: "fixture-command", action: "verify", payload: {}};
  }});
  await flush();
  assert.equal(state.sends, 1);
  const before = state.reads;
  [...state.timers.values()][0].callback(); await flush();
  assert.equal(state.reads, before + 1);
  assert.equal(state.results.length, 0);
  state.tabReply.resolve({ok: true, value: {ready: true}}); await flush();
  assert.equal(state.results.length, 1);
  assert.equal(state.results[0].command_id, "fixture-command");
  assert.equal(state.sends, 1);
  assert.equal(state.polls.length, 2);
});

test("no stored pair means no background activity or network requests", async () => {
  const {state, api} = await setup();
  state.polls[0].resolve({status: 401}); await flush();
  state.accounts = {}; await api.wake(); await flush();
  assert.equal(state.timers.size, 0);
  assert.equal(state.polls.length, 1);
});

test("lost send acknowledgement never reloads and resubmits a prompt", async () => {
  const {state, api} = await setup();
  const operation = api.execute({id: "uncertain-send", action: "send", payload: {}});
  state.tabReply.resolve({then(_resolve, reject) {reject(new Error("Reply lost"));}});
  await assert.rejects(operation, /SUBMISSION_UNCERTAIN/);
  assert.equal(state.sends, 1);
  assert.equal(state.results.length, 0);
});
