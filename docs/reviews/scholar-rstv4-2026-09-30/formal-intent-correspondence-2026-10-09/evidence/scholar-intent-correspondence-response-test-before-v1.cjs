/* Controlled async tests execute the shipped component; no browser/visual claim. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

let active;
const sameDeps = (a, b) => a && b && a.length === b.length && a.every((item, i) => Object.is(item, b[i]));
const hooks = {
  useRef(value) { const n = active.index++; active.slots[n] ??= { current: value }; return active.slots[n]; },
  useState(value) { const r = active, n = r.index++; if (!(n in r.slots)) r.slots[n] = value; return [r.slots[n], (next) => { r.slots[n] = typeof next === 'function' ? next(r.slots[n]) : next; r.dirty = true; }]; },
  useEffect(fn, deps) { const r = active, n = r.index++; if (!sameDeps(r.slots[n]?.deps, deps)) r.effects.push(() => { r.slots[n]?.cleanup?.(); r.slots[n] = { deps, cleanup: fn() }; }); },
};
function runtime(component, props) {
  const r = { slots: [], effects: [], index: 0, dirty: false, tree: null, props };
  r.render = () => {
    for (let pass = 0; pass < 12; pass++) {
      r.index = 0; r.dirty = false; active = r; r.tree = component(r.props); active = null;
      const effects = r.effects.splice(0); effects.forEach((effect) => effect());
      if (!r.dirty) return r.tree;
    }
    throw new Error('Unexpected render loop');
  };
  r.unmount = () => r.slots.forEach((slot) => slot?.cleanup?.());
  r.render(); return r;
}
function all(tree, predicate) {
  if (Array.isArray(tree)) return tree.flatMap((item) => all(item, predicate));
  if (!tree || typeof tree !== 'object') return [];
  return [...(predicate(tree) ? [tree] : []), ...all(tree.props?.children, predicate)];
}
const named = (tree, name) => all(tree, (node) => node.type === name)[0];
const text = (value) => Array.isArray(value) ? value.map(text).join('') : typeof value === 'string' ? value : value?.props ? text(value.props.children) : '';
const button = (r, label) => all(r.render(), (node) => node.type === 'Button' && text(node.props.children) === label)[0];
const tick = async () => { for (let i = 0; i < 40; i++) await Promise.resolve(); };
function storage() {
  const target = {};
  Object.defineProperties(target, {
    getItem: { value: (key) => target[key] ?? null }, setItem: { value: (key, value) => { target[key] = String(value); } },
    removeItem: { value: (key) => { delete target[key]; } },
  });
  return target;
}
function setup() {
  const localStorage = storage(), sessionStorage = storage();
  const api = {}, attempts = [], timers = new Map();
  let timer = 0, uuid = 0;
  class ApiError extends Error { constructor(status) { super('declared API failure'); this.status = status; } }
  const file = path.join(__dirname, '../../components/studio-response-review.tsx');
  const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText;
  const module = { exports: {} };
  const requireMock = (name) => {
    if (name === 'react') return hooks;
    if (name === 'react/jsx-runtime') return { jsx: (type, props, key) => ({ type, props, key }), jsxs: (type, props, key) => ({ type, props, key }) };
    if (name === '@/lib/studio-api') return { studioApi: api, ApiError, API_BASE: 'http://declared-fixture/api' };
    if (name.startsWith('@/components/ui/')) return Object.fromEntries(['Button', 'Checkbox', 'Dialog', 'DialogContent', 'DialogDescription', 'DialogTitle', 'Input', 'Textarea'].map((name) => [name, name]));
    throw new Error(`Unexpected import ${name}`);
  };
  vm.runInNewContext(code, { module, exports: module.exports, require: requireMock, localStorage, sessionStorage,
    crypto: { randomUUID: () => `fixture-uuid-${++uuid}` }, setTimeout: (fn) => { timers.set(++timer, fn); return timer; }, clearTimeout: (id) => timers.delete(id), Intl, Date });
  let server = { comment_id: 'comment-a', display_label: '#1', edited_text: 'Fixture reviewer opinion', status: 'PENDING', author_decision: 'Original reason', response_text: 'Original reply', content_sha256: 'content-0', response_verification: { status: 'NOT_REVIEWED' }, changes: [] };
  const context = () => ({ context_sha256: 'fixed-context', state: { response_text: server.response_text, author_decision: server.author_decision, current_author_revision: 2, generated_input_revision: 2, round_number: 1 }, baseline_version_number: 1, target_version_number: 2, baseline_to_target_diff: '-one\n+two', evidence: [], history: [], verification: server.response_verification });
  api.comments = async () => [server]; api.responseReview = async () => context();
  api.responseReviewHistory = async () => ({ history: [] });
  api.updateComment = (id, changes) => new Promise((resolve, reject) => attempts.push({ id, changes, resolve: (reply) => { server = reply; resolve(reply); }, reject }));
  const props = { manuscriptId: 'manuscript-a', comment: server, archived: false, onReload: async () => {} };
  const mount = (extra = {}) => runtime(module.exports.StudioResponseReview, { ...props, ...extra });
  return { api, attempts, localStorage, sessionStorage, ApiError, context, mount, get server() { return server; }, set server(value) { server = value; } };
}

(async () => {
  const a = setup(), r = a.mount();
  named(r.render(), 'Textarea').props.onChange({ target: { value: 'First keystrokes' } });
  assert(Object.values(a.localStorage).some((value) => value.includes('First keystrokes')), 'Typing must immediately preserve a local checkpoint');
  named(r.render(), 'Textarea').props.onBlur();
  assert.equal(a.attempts.length, 1);
  named(r.render(), 'Textarea').props.onChange({ target: { value: 'Newer keystrokes during save' } });
  a.attempts[0].resolve({ ...a.server, response_text: 'First keystrokes', content_sha256: 'content-1' }); await tick();
  assert.equal(a.attempts.length, 2);
  assert.equal(a.attempts[1].changes.response_text, 'Newer keystrokes during save');
  assert.equal(a.attempts[1].changes.expected_content_sha256, 'content-1');
  a.attempts[1].resolve({ ...a.server, response_text: 'Newer keystrokes during save', content_sha256: 'content-2' }); await tick();
  assert.equal(named(r.render(), 'Textarea').props.value, 'Newer keystrokes during save'); r.unmount();
  console.log('PASS Serialized saves retain newer keystrokes and advance the actual CAS basis');

  const b = setup(), conflicted = b.mount();
  named(conflicted.render(), 'Textarea').props.onChange({ target: { value: 'Local retained reply' } });
  named(conflicted.render(), 'Textarea').props.onBlur();
  b.server = { ...b.server, response_text: 'Other page reply', content_sha256: 'content-foreign' };
  b.attempts[0].reject(new b.ApiError(409)); await tick();
  assert.equal(named(conflicted.render(), 'Textarea').props.value, 'Local retained reply');
  assert(button(conflicted, '保留本地文字，再保存'));
  button(conflicted, '保留本地文字，再保存').props.onClick(); button(conflicted, '保存回复').props.onClick();
  assert.equal(b.attempts[1].changes.expected_content_sha256, 'content-foreign');
  b.attempts[1].resolve({ ...b.server, response_text: 'Local retained reply', content_sha256: 'content-rebased' }); await tick(); conflicted.unmount();
  console.log('PASS Conflicting page edits require an explicit comparison before replacing the reply');

  const c = setup(), beforeUnmount = c.mount();
  named(beforeUnmount.render(), 'Textarea').props.onChange({ target: { value: 'Recovered unsaved reply' } }); beforeUnmount.unmount();
  const recovered = c.mount(); assert.equal(named(recovered.render(), 'Textarea').props.value, 'Recovered unsaved reply');
  let reviewedSavedReply;
  c.api.responseReview = async () => { reviewedSavedReply = c.server.response_text; return c.context(); };
  button(recovered, '核对回复').props.onClick(); assert.equal(c.attempts.length, 1);
  assert.equal(reviewedSavedReply, undefined, 'The review must not read an unsaved reply');
  c.attempts[0].resolve({ ...c.server, response_text: 'Recovered unsaved reply', content_sha256: 'content-recovered' }); await tick();
  assert.equal(reviewedSavedReply, 'Recovered unsaved reply');
  let dialog = all(recovered.render(), (node) => typeof node.type === 'function' && node.type.name === 'ResponseCheckDialog')[0];
  assert(dialog, text(recovered.tree));
  const finalRequest = { request_id: 'unchanged-author-confirmation-id', context_sha256: 'fixed-context', outcome: 'EXPLAINED_NO_CHANGE', claims: [], acknowledged_all_assertions: true };
  const submitted = [];
  c.api.confirmResponseReview = async (ms, comment, request) => { submitted.push(request); throw new Error('Uncertain transport after submit'); };
  await dialog.props.onConfirm(finalRequest); recovered.unmount();
  const afterDisconnect = c.mount();
  assert(button(afterDisconnect, '重试原核对提交'));
  c.api.confirmResponseReview = async (ms, comment, request) => { submitted.push(request); return { check_id: 'check-original', idempotent_replay: true, comment: { ...c.server, status: 'VERIFY', response_verification: { status: 'STALE' } }, history: [] }; };
  button(afterDisconnect, '重试原核对提交').props.onClick(); await tick();
  assert.equal(JSON.stringify(submitted[0]), JSON.stringify(submitted[1]));
  assert.equal(named(afterDisconnect.render(), 'select').props.value, 'VERIFY');
  afterDisconnect.unmount();
  console.log('PASS Unmount restores drafts, review waits for save, and an uncertain submit retries its original decision');

  const d = setup(), archived = d.mount({ archived: true });
  d.api.responseReview = async () => { throw new Error('Compiled PDF is unavailable'); };
  button(archived, '查看核对历史').props.onClick(); await tick();
  assert.equal(d.attempts.length, 0);
  assert(named(archived.render(), 'Dialog').props.open, 'Archived replies must expose history without reading the compiled PDF');
  archived.unmount();
  console.log('PASS Archived opinions expose review history without modifying their reply');

  const reviewContext = { ...c.context(), state: { ...c.context().state, response_text: '😀 We changed it.' }, evidence: [{ evidence_id: 'real-change', change_id: 'edit-a', status: 'GENERATED_TEXT_CHANGED', changed_text: 'Two toolbars.', final_page: 1, final_line: 4 }, { evidence_id: 'retained', change_id: 'edit-a', status: 'EXACT_BASELINE_TEXT_RETAINED', changed_text: 'No study.' }] };
  let accepted;
  const child = runtime(dialog.type, { ...dialog.props, context: reviewContext, disabled: false, onConfirm: async (request) => { accepted = request; } });
  named(child.render(), 'Textarea').props.onSelect({ currentTarget: { selectionStart: 3, selectionEnd: 17 } });
  button(child, '加入所选修改声明').props.onClick();
  const boxes = all(child.render(), (node) => node.type === 'Checkbox');
  assert.equal(boxes[1].props.disabled, true, 'Retained text cannot be selected as actual modified evidence');
  boxes[0].props.onCheckedChange(true); all(child.render(), (node) => node.type === 'Checkbox').at(-1).props.onCheckedChange(true);
  button(child, '作者确认并保存核对记录').props.onClick();
  assert.equal(accepted.claims[0].offset_unit, 'utf16'); assert.equal(accepted.claims[0].start, 3);
  assert.equal(accepted.claims[0].text, 'We changed it.'); assert.deepEqual(Array.from(accepted.claims[0].evidence_ids), ['real-change']);
  child.unmount();
  console.log('PASS Actual dialog retains Unicode selection offsets and rejects retained evidence');
})().catch((error) => { console.error(error); process.exitCode = 1; });
