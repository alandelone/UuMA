/* Execute the shipped controller and render functions. This is not browser acceptance. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const sandbox = {};
vm.runInNewContext(fs.readFileSync(new URL('../src/rstv4/catalog_track_decisions.js', import.meta.url), 'utf8'), sandbox);
const ui = sandbox.CatalogTrackDecisions;
const plain = value => JSON.parse(JSON.stringify(value));
const local = () => { const map = new Map(); return { map, getItem: k => map.get(k) || null, setItem: (k, v) => map.set(k, v) }; };
const ctx = (id = 't1', stamp = 'original') => ({ track: { track_id: id, field_id: 'f1' }, context_sha256: stamp,
  nodes: [{ node_id: 'g1', node_type: 'gap', status: 'APPROVED', statement: 'Original gap', payload: { evidence_ids: ['e1'], upstream_node_ids: [] } },
    { node_id: 'm1', node_type: 'method', status: 'STALE', statement: 'Stale method', payload: { evidence_ids: ['e1'], upstream_node_ids: ['g1'] } }],
  evidence: [{ evidence_id: 'e1', statement: '<Exact statement>', excerpt: 'Original located text', relation: 'SUPPORTS', paper_version_id: 'pv1', location: { unit_id: 'u1', page: 3, conditions: 'original conditions' }, selectable: true, adopted_in: [{ snapshot_id: 's1', version: 1 }] }],
  proposals: [], receipts: [] });
let count = 0, keys = 0;
async function test(name, fn) { await fn(); count++; process.stdout.write(`PASS ${name}\n`); }
const controller = (api, storage = local(), namespace = 'tab1') => ui.createController({ api, storage, namespace, makeKey: () => `request-${++keys}` });
await test('all six independent scientific types and exact evidence are rendered', async () => {
  const c = controller(async () => ctx()); await c.load('t1');
  const html = ui.render(c.state());
  for (const kind of ['gap', 'idea', 'research_question', 'hypothesis', 'method', 'claim']) assert.ok(html.includes(`value="${kind}"`));
  assert.match(html, /&lt;Exact statement&gt;/); assert.match(html, /Original located text/); assert.match(html, /pv1/); assert.match(html, /original conditions/); assert.match(html, /Snapshot v1/);
  assert.match(html, /name="statement" required/); assert.match(html, /name="rationale" required/); assert.match(html, /aria-live="polite"/);
});
await test('propose uses exact selected dependencies and never submits an approval grant', async () => {
  const attempts = []; const c = controller(async (url, body) => { if (body) { attempts.push(plain(body)); return { proposal: { status: 'PROPOSED' } }; } return ctx(); });
  await c.load('t1'); c.edit({ kind: 'idea', statement: 'New idea', rationale: 'Reason', evidence_ids: ['e1'], upstream_node_ids: ['g1'] });
  await c.propose(); assert.equal(attempts.length, 1); assert.equal(attempts[0].operation, 'PROPOSE_DECISION'); assert.equal(attempts[0].expected_context_sha256, 'original'); assert.equal(attempts[0].track_id, 't1');
  assert.deepEqual(attempts[0].proposal.upstream_node_ids, ['g1']); assert.ok(!JSON.stringify(attempts[0]).includes('grant')); assert.equal(c.state().request, null);
});
await test('unknown submission survives reload and retries exact original body', async () => {
  const store = local(), attempts = [];
  const api = async (url, body) => { if (body) { attempts.push(plain(body)); if (attempts.length === 1) throw Error('Response lost'); return {}; } return ctx(); };
  let c = controller(api, store); await c.load('t1'); c.edit({ statement: 'Frozen candidate', rationale: 'Original reason', evidence_ids: ['e1'] }); await assert.rejects(c.propose(), /Response lost/);
  assert.equal(c.edit({ statement: 'Must not replace uncertain original' }), false);
  c = controller(api, store); await c.load('t1'); await c.retry(); assert.deepEqual(attempts[0], attempts[1]); assert.equal(c.state().request, null);
});
await test('known conflict preserves draft and requires deliberate version comparison', async () => {
  let stamp = 'original', writes = 0;
  const c = controller(async (url, body) => { if (body) { writes++; stamp = 'changed'; throw Object.assign(Error('Changed science'), { status: 409 }); } return ctx('t1', stamp); });
  await c.load('t1'); c.edit({ statement: 'Keep this text', rationale: 'Keep this reason', evidence_ids: ['e1'] }); await assert.rejects(c.propose(), /Changed science/);
  assert.equal(c.state().draft.statement, 'Keep this text'); assert.ok(c.state().comparisonRequired); assert.equal(c.state().request, null); await assert.rejects(c.propose(), /比较/); assert.equal(writes, 1);
  c.compare(); assert.equal(c.state().comparisonRequired, false); assert.equal(c.state().draft.bound.context_sha256, 'changed');
});
await test('storage refusal stops before a mutation is sent', async () => {
  let writes = 0; const store = { getItem() { return null; }, setItem() { throw Error('Unavailable'); } };
  const c = controller(async (url, body) => { if (body) writes++; return ctx(); }, store); await c.load('t1'); c.edit({ statement: 'Candidate', rationale: 'Reason', evidence_ids: ['e1'] });
  await assert.rejects(c.propose(), /存储/); assert.equal(writes, 0);
});
await test('late Track context cannot overwrite a different selected Track', async () => {
  let resolve; const c = controller(async url => url.includes('/t1/') ? new Promise(r => { resolve = r; }) : ctx('t2'));
  const old = c.load('t1'); await c.load('t2'); resolve(ctx()); await old; assert.equal(c.state().trackId, 't2'); assert.equal(c.state().context.track.track_id, 't2');
});
await test('late successful mutation clears only its original Track receipt', async () => {
  let resolve; const store = local();
  const c = controller(async (url, body) => body ? new Promise(r => { resolve = r; }) : ctx(url.includes('/t2/') ? 't2' : 't1'), store);
  await c.load('t1'); c.edit({ statement: 'Track one', rationale: 'Reason', evidence_ids: ['e1'] }); const old = c.propose();
  await c.load('t2'); resolve({}); await old;
  assert.equal(c.state().context.track.track_id, 't2'); assert.equal(c.state().draft.statement, '');
  assert.equal(JSON.parse(store.getItem('tab1:t1')).request, null); assert.equal(JSON.parse(store.getItem('tab1:t1')).draft.statement, 'Track one');
});
await test('drafts are isolated between tabs', async () => {
  const store = local(), a = controller(async () => ctx(), store, 'tabA'), b = controller(async () => ctx(), store, 'tabB');
  await a.load('t1'); a.edit({ statement: 'A only' }); await b.load('t1'); b.edit({ statement: 'B only' });
  assert.equal(JSON.parse(store.getItem('tabA:t1')).draft.statement, 'A only'); assert.equal(JSON.parse(store.getItem('tabB:t1')).draft.statement, 'B only');
});
await test('replacement preserves original node and its explicit dependencies', async () => {
  const c = controller(async () => ctx()); await c.load('t1'); assert.ok(c.replace('m1'));
  assert.equal(c.state().draft.supersedes_node_id, 'm1'); assert.equal(c.state().draft.kind, 'method'); assert.deepEqual(plain(c.state().draft.upstream_node_ids), ['g1']); assert.equal(c.state().draft.rationale, '');
  assert.match(ui.render(c.state()), /原批准与成文版本保留/); c.fresh(); assert.equal(c.state().draft.supersedes_node_id, null);
});
await test('apply requires read-back authentic grant and captured basis', async () => {
  const data = ctx(), attempts = []; data.proposals = [{ proposal_id: 'p1', node_id: 'g1', kind: 'gap', statement: 'Candidate', rationale: 'Reason', payload: {}, approval_phrase: 'APPROVE p1', status: 'PROPOSED', revision: 1, grant_available: false, basis_captured: true }];
  const c = controller(async (url, body) => { if (body) attempts.push(plain(body)); return data; }); await c.load('t1'); await assert.rejects(c.apply('p1'), /真实用户/); assert.equal(attempts.length, 0);
  data.proposals[0].grant_available = true; data.proposals[0].basis_captured = false; await c.load('t1'); await assert.rejects(c.apply('p1'), /真实用户/);
  data.proposals[0].basis_captured = true; await c.load('t1'); await c.apply('p1'); assert.equal(attempts[0].operation, 'APPLY_DECISION'); assert.equal(attempts[0].proposal_id, 'p1'); assert.equal(attempts[0].expected_revision, 1);
});
await test('unknown apply result retries original action after grant is consumed', async () => {
  const data = ctx(), attempts = []; data.proposals = [{ proposal_id: 'p1', revision: 1, status: 'PROPOSED', grant_available: true, basis_captured: true }];
  const c = controller(async (url, body) => { if (!body) return data; attempts.push(plain(body)); if (attempts.length === 1) { data.proposals[0].grant_available = false; data.proposals[0].status = 'APPROVED'; throw Error('Lost apply response'); } return {}; });
  await c.load('t1'); await assert.rejects(c.apply('p1')); await c.load('t1'); await c.retry(); assert.deepEqual(attempts[0], attempts[1]);
});
await test('HTML actually loads the new controller before workspace mount', () => {
  const html = fs.readFileSync(new URL('../src/rstv4/catalog_web.html', import.meta.url), 'utf8');
  assert.ok(html.indexOf('/catalog-track-decisions.js') < html.indexOf('/catalog-research-workspaces.js'));
  const workspace = fs.readFileSync(new URL('../src/rstv4/catalog_research_workspaces.js', import.meta.url), 'utf8');
  assert.match(workspace, /CatalogTrackDecisions\?\.mount/); assert.match(workspace, /await trackDecisions.load\(data.track.track_id\)/); assert.match(workspace, /data-track-scientific/);
});
await test('actual mounted form and buttons invoke proposal and Chat node handlers', async () => {
  sandbox.crypto = { randomUUID: () => `mount-${++keys}` };
  sandbox.FormData = class { constructor(form) { this.values = form.values; } get(name) { return this.values[name]; } getAll(name) { return this.values[name] || []; } };
  const events = {}, writes = [], selected = [], status = { textContent: '' }, panel = { innerHTML: '', querySelector: () => status };
  const host = { querySelector: () => panel, addEventListener: (name, fn) => { events[name] = fn; } };
  let finish; const finished = new Promise(r => { finish = r; });
  const mounted = ui.mount({ host, storage: local(), namespace: 'mounted', api: async (url, body) => { if (body) writes.push(plain(body)); return ctx(); }, onChanged: async () => finish(), onNode: id => selected.push(id) });
  await mounted.load('t1'); assert.match(panel.innerHTML, /data-science-proposal/);
  const form = { values: { kind: 'gap', statement: 'Mounted candidate', rationale: 'Mounted rationale', evidence: ['e1'], upstream: [] } };
  events.input({ target: { closest: () => form } }); events.submit({ target: { closest: () => form }, preventDefault() {} }); await finished;
  assert.equal(writes[0].proposal.statement, 'Mounted candidate'); assert.deepEqual(writes[0].proposal.evidence_ids, ['e1']);
  events.click({ target: { closest: () => ({ dataset: { scienceNode: 'g1' }, disabled: false }) } }); assert.deepEqual(selected, ['g1']);
  mounted.leave(); assert.equal(mounted.controller.state().context, null);
});
await test('invalid selected dependencies remain removable instead of disappearing on edit', async () => {
  const data = ctx(), c = controller(async () => data); await c.load('t1');
  c.edit({ evidence_ids: ['e1', 'missing-evidence'], upstream_node_ids: ['m1', 'missing-node'] });
  data.evidence[0].selectable = false; await c.load('t1');
  const html = ui.render(c.state());
  assert.match(html, /name="evidence" value="e1" checked>/);
  assert.match(html, /name="upstream" value="m1" checked>/);
  assert.match(html, /原依据已不可用：missing-evidence/);
  assert.match(html, /data-science-remove-id="missing-node"/);
});
process.stdout.write(`${count} controlled scientific UI checks passed; browser acceptance false\n`);
