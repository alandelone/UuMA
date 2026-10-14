import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const sandbox = { URLSearchParams };
vm.runInNewContext(fs.readFileSync(new URL('../src/rstv4/catalog_experiments.js', import.meta.url), 'utf8'), sandbox);
const ui = sandbox.CatalogExperiments, plain = v => JSON.parse(JSON.stringify(v));
const storage = () => { const map = new Map(); return { getItem: k => map.get(k) || null, setItem: (k, v) => map.set(k, v), map }; };
const ctx = (id = 't1', stamp = 'original') => ({ context_sha256: stamp, python_executable: 'python', science: { track: { research_type: 'engineering_system' }, nodes: [{ node_id: 'm1', node_type: 'method', statement: 'Approved method', status: 'APPROVED' }] }, projects: [], plans: [], runs: [], project_types: { engineering_system: ['requirements', 'system_design', 'implementation', 'validation'] } });
let n = 0, keys = 0;
const controller = (api, store = storage(), namespace = 'test') => ui.createController({ api, storage: store, namespace, makeKey: () => `request-${++keys}` });
async function test(name, fn) { await fn(); process.stdout.write(`PASS ${name}\n`); n++; }
const fileList = { cwd: 'workspace', exists: true, files: [{ path: 'script.py', sha256: 'original-script', size: 22 }, { path: 'data.csv', sha256: 'input', size: 12 }] };
await test('complete plan UI and Project metadata use actual Method and files', async () => {
  const c = controller(async path => path.includes('experiment-files') ? fileList : ctx());
  await c.load('t1'); await c.readFiles();
  const html = ui.render(c.state());
  for (const name of ['goals', 'location', 'data', 'time', 'type_payload', 'script_path', 'input_files', 'environment', 'artifact_paths']) assert.ok(html.includes(`name="${name}"`));
  assert.match(html, /Approved method/); assert.match(html, /original-script/);
  assert.match(html, /name=.executable/);
});
await test('preview binds exact selection and unchanged form preserves manifest', async () => {
  let submitted;
  const c = controller(async (path, body) => {
    if (path.includes('experiment-files')) return fileList;
    if (path.includes('experiment-manifest')) { submitted = plain(body); return { manifest_sha256: 'frozen' }; }
    if (body) return { object_id: 'plan' };
    return ctx();
  });
  await c.load('t1'); await c.readFiles(); c.edit({ method_node_id: 'm1', script_path: 'script.py', input_files: ['data.csv'] });
  await c.preview(); c.edit({ script_path: 'script.py' }); assert.equal(c.state().manifest.manifest_sha256, 'frozen');
  assert.deepEqual(submitted.plan.argv, ['python', 'script.py']); assert.deepEqual(submitted.input_files, ['data.csv']);
  c.edit({ executable: 'selected-python' }); await c.preview(); assert.equal(submitted.plan.argv[0], 'selected-python');
  c.edit({ arguments: '["--changed"]' }); assert.equal(c.state().manifest, null);
});
await test('uncertain request survives refresh and retries same body', async () => {
  const store = storage(), requests = []; let fail = true;
  const api = async (path, body) => { if (body) { requests.push(plain(body)); if (fail) throw Error('Offline after submission'); return { object_id: 'run1' }; } return { ...ctx(), plans: [{ plan_id: 'p1', revision: 1, status: 'APPROVED', reviewed_manifest: {}, run_id: null }] }; };
  const c = controller(api, store); await c.load('t1'); await assert.rejects(c.planAction('START_PLAN', 'p1')); assert.ok(c.state().request);
  const restored = controller(api, store); await restored.load('t1'); fail = false; await restored.retry();
  assert.deepEqual(requests[0], requests[1]); assert.equal(restored.state().request, null);
});
await test('late start completion retains original Track receipt without replacing other draft', async () => {
  let release;
  const store = storage(), c = controller(async (path, body) => body ? new Promise(r => { release = r; }) : { ...ctx(path.includes('t2') ? 't2' : 't1'), plans: [{ plan_id: 'p1', revision: 1, status: 'APPROVED', reviewed_manifest: {} }] }, store);
  await c.load('t1'); const pending = c.planAction('START_PLAN', 'p1'); await c.load('t2'); release({ object_id: 'r1' }); await pending;
  assert.equal(c.state().trackId, 't2'); assert.equal(c.state().request, null);
  await c.load('t1'); assert.equal(c.state().request, null);
});
await test('storage failure prevents submitting execution', async () => {
  let posts = 0; const c = controller(async (path, body) => { if (body) posts++; return { ...ctx(), plans: [{ plan_id: 'p1', revision: 1, status: 'APPROVED', reviewed_manifest: {} }] }; }, { getItem: () => null, setItem: () => { throw Error('Full'); } });
  await c.load('t1'); await assert.rejects(c.planAction('START_PLAN', 'p1')); assert.equal(posts, 0);
});
await test('changed context requires explicit comparison; grant availability does not mint approval', async () => {
  let stamp = 'original'; const c = controller(async () => ({ ...ctx('t1', stamp), plans: [{ plan_id: 'p1', revision: 1, status: 'PROPOSED', reviewed_manifest: {}, grant_available: false, argv: ['python'], proposal_id: 'proposal', approval_phrase: 'APPROVE proposal' }] }));
  await c.load('t1'); stamp = 'changed'; await c.load('t1'); assert.equal(c.state().comparisonRequired, true);
  c.compare(); assert.equal(c.state().comparisonRequired, false);
  assert.throws(() => c.planAction('APPLY_PLAN', 'p1'), /批准/); assert.match(ui.render(c.state()), /data-exp-apply="p1" disabled/);
});
await test('RUNNING means saved state and does not offer another execution', async () => {
  const c = controller(async () => ({ ...ctx(), plans: [{ plan_id: 'p1', revision: 1, status: 'APPROVED', reviewed_manifest: {}, run_id: 'r1', argv: ['python'] }], runs: [{ run_id: 'r1', status: 'RUNNING', detail: { plan_id: 'p1', cwd: 'workspace' } }] }));
  await c.load('t1'); const html = ui.render(c.state()); assert.match(html, /data-exp-start="p1" disabled/); assert.match(html, /尚未确认进程/); assert.ok(!html.includes('data-exp-result='));
});
await test('late file lookup cannot change selected owner directory', async () => {
  let release; const c = controller(async path => path.includes('experiment-files') ? new Promise(r => { release = r; }) : ctx());
  await c.load('t1'); const pending = c.readFiles(); c.edit({ working_directory: 'new-directory' }); release(fileList); await pending; assert.equal(c.state().files, null);
});
await test('Project creation preserves a separate plan and unsent result draft', async () => {
  const c = controller(async (path, body) => body ? { object_id: 'project' } : ctx());
  await c.load('t1'); c.edit({ script_path: 'kept.py', results: { r1: { statement: 'Unsent result', metric_key: 'value' } }, project: { ...c.state().draft.project, slug: 'created', title: 'Created' } });
  await c.createProject(); assert.equal(c.state().draft.script_path, 'kept.py'); assert.equal(c.state().draft.results.r1.statement, 'Unsent result');
});
await test('changing the selected directory invalidates original file choices', async () => {
  const c = controller(async path => path.includes('experiment-files') ? fileList : ctx());
  await c.load('t1'); await c.readFiles(); c.edit({ working_directory: 'new-dir' }); assert.equal(c.state().files, null);
});
await test('unavailable input and script choices remain visible and can be deliberately removed', async () => {
  const c = controller(async path => path.includes('experiment-files') ? { cwd: 'new-dir', exists: true, files: [] } : ctx());
  await c.load('t1'); c.edit({ method_node_id: 'm1', script_path: 'old-script.py', input_files: ['old-data.csv'], arguments: '["kept"]' });
  await c.readFiles(); const html = ui.render(c.state()); assert.match(html, /old-script.py · 原选择尚未核实/); assert.match(html, /明确移除此输入选择/);
  c.removeInput('old-data.csv'); assert.deepEqual(plain(c.state().draft.input_files), []); assert.equal(c.state().draft.method_node_id, 'm1'); assert.equal(c.state().draft.arguments, '["kept"]');
});
process.stdout.write(`PASS ${n} experiment controller scenarios\n`);
