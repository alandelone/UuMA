const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(process.env.UUMA_OBSERVATORY_TEST_JS ||
  path.join(__dirname, '../src/uuma/observatory/static/app.js'), 'utf8');
const start = source.indexOf('  function getWisdomPipelineView(');
const end = source.indexOf('  // Comprehensive Brainstormer', start);
const context = vm.createContext({
  escapeHtml: value => String(value ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[c]),
  normalizeWisdomDocUrl: value => value,
});
vm.runInContext(source.slice(start, end), context);
const render = context.renderWisdomPreviewHtml;

test('missing source never invents live work, budgets, counts or a document version', () => {
  for (const expanded of [true, false]) {
    const html = render({items: [], health: 'WARNING'}, expanded);
    assert.match(html, /研究数据暂不可用/);
    assert.match(html, /研究数据读取失败/);
    assert.doesNotMatch(html, /PID 12700|Cycle #40|40 个 Cycle|v45|0\/500|实时调研中|无硬阻塞/);
    assert.doesNotMatch(html, /status-RUNNING|pipeline-pulse-dot/);
  }
});

test('zero usage stays zero and queued work is not reported as executing', () => {
  const html = render({health: 'HEALTHY', items: [{kind: 'knowledge_topic', item_id: 'topic',
    status: 'ACTIVE', title: 'Original topic', payload: {title: 'Original topic', ver_cnt: 0,
      claim_count: 0, links_cnt: 0, standalone_url: 'https://example.com/topic',
      orbit_info: {orbit_id: 'original-orbit', status: 'QUEUED', runner_live: false,
        budget_tier: 'DEEP', usage: {cycle_count: 0, sources_used: 0},
        pipeline_items: [{question_text: 'Original unresolved evidence', stage: 'QUEUED', badge: '待执行'}]}}}]}, true);
  assert.match(html, /研究已排队 · 当前无执行轮次/);
  assert.match(html, /Original unresolved evidence/);
  assert.match(html, /0 个 Cycle/);
  assert.match(html, /v0 · 0断言 · 0引据/);
  assert.doesNotMatch(html, /现场研究执行中|实时调研中/);
});

test('source timeout retains the last known records and suppresses stale running indicators', () => {
  const ws = {health: 'WARNING', items: [{kind: 'knowledge_topic', item_id: 'topic',
    status: 'ACTIVE', title: 'Saved topic', payload: {title: 'Saved topic', orbit_info: {
      orbit_id: 'original-orbit', status: 'ACTIVE', runner_live: true,
      pipeline_items: [{question_text: 'Saved evidence gap', stage: 'RUNNING', badge: '执行中'}],
    }}}]};
  const stale = render(ws, true, {is_available: false});
  assert.match(stale, /显示上次读取记录/);
  assert.match(stale, /Saved topic/);
  assert.match(stale, /Saved evidence gap/);
  assert.doesNotMatch(stale, /现场研究执行中|status-RUNNING|pipeline-pulse-dot/);
  assert.match(render(ws, true, {is_available: true}), /现场研究执行中/);
});

test('archived and orphan investigation history remains visible', () => {
  const html = render({health: 'HEALTHY', items: [
    {kind: 'knowledge_topic', item_id: 'old-topic', status: 'ARCHIVED', payload: {title: 'Retained topic',
      investigations: [{orbit_id: 'old', status: 'STOPPED', pipeline_items: [
        {question_text: 'Historical gap', stage: 'PAUSED', badge: '未完成'}]}]}},
    {kind: 'knowledge_orbit', item_id: 'orphan', payload: {orbit_info: {orbit_id: 'orphan',
      status: 'FAILED', pipeline_items: [{question_text: 'Unattached gap', stage: 'PAUSED', badge: '失败'}]}}},
  ]}, true);
  assert.match(html, /Retained topic/);
  assert.match(html, /Historical gap/);
  assert.match(html, /Unattached gap/);
  assert.match(html, /__uuma_selectItem\('orphan'\)/);
  assert.doesNotMatch(html, /实时调研中/);
});

function fleetFixture(fetch) {
  const state = {sseConnected: true, agents: [{agent_id: 'last-known'}], sources: {}};
  const counts = {render: 0};
  const c = vm.createContext({state, fetch, console: {warn() {}},
    updateMetrics() {}, renderWorkspaces() {counts.render++;}, updateBackfill() {},
    autoSelectFirstItem() {}, loadEvents() {},
  });
  vm.runInContext(source.slice(source.indexOf('  let fleetRefreshPending = null;'),
    source.indexOf('  function autoSelectFirstItem()')), c);
  return {state, counts, refresh: c.refreshFleetData};
}

test('connected event stream does not prevent recovery after an empty initial snapshot', async () => {
  let calls = 0;
  const f = fleetFixture(async () => ({ok: true, async json() {
    calls++; return {agents: calls === 1 ? [] : [{agent_id: 'wisdom-oldman', items: ['original-topic']}], sources: {}};
  }}));
  await f.refresh();
  assert.equal(f.state.agents.length, 0);
  await f.refresh();
  assert.equal(calls, 2);
  assert.equal(f.state.agents[0].items[0], 'original-topic');
});

test('overlapping refreshes share one request and failed reads preserve known records', async () => {
  let finish;
  let calls = 0;
  const gate = new Promise(resolve => {finish = resolve;});
  const f = fleetFixture(() => {calls++; return gate;});
  const first = f.refresh();
  const second = f.refresh();
  assert.equal(first, second);
  assert.equal(calls, 1);
  finish({ok: false, status: 503});
  await first;
  assert.equal(f.state.agents[0].agent_id, 'last-known');
  assert.equal(f.counts.render, 0);
});

if (process.env.UUMA_WISDOM_PANEL_SNAPSHOT) {
  test('actual owner snapshot renders all four topics and original onion evidence gaps', () => {
    const record = JSON.parse(fs.readFileSync(process.env.UUMA_WISDOM_PANEL_SNAPSHOT, 'utf8'));
    const html = render(record.workspace, true, record.source_health);
    assert.match(html, /知识主题体系 \(4 个主题\)/);
    assert.match(html, /青葱/);
    assert.match(html, /喷雾间隔/);
    assert.match(html, /营养液/);
    assert.doesNotMatch(html, /暂无排队中的调研攻关缺口|PID 12700|v45/);
  });
}
