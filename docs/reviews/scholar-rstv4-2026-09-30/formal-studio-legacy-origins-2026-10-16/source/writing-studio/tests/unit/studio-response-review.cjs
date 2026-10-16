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
const text = (value) => Array.isArray(value) ? value.map(text).join('') : typeof value === 'string' || typeof value === 'number' ? String(value) : value?.props ? text(value.props.children) : '';
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
  const downloads = { exports: {} };
  const downloadSource = fs.readFileSync(path.join(__dirname, '../../lib/studio-downloads.ts'), 'utf8');
  const downloadCode = ts.transpileModule(downloadSource, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  // Resolve the shipped pure URL helper; no file request or browser download runs here.
  vm.runInNewContext(downloadCode, { module: downloads, exports: downloads.exports, URL, Request, Response, fetch });
  const requireMock = (name) => {
    if (name === 'react') return hooks;
    if (name === 'react/jsx-runtime') return { jsx: (type, props, key) => ({ type, props, key }), jsxs: (type, props, key) => ({ type, props, key }) };
    if (name === '@/lib/studio-api') return { studioApi: api, ApiError, API_BASE: 'http://declared-fixture/api' };
    if (name === '@/lib/studio-downloads') return downloads.exports;
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

  const origin = { manuscript_id: 'ms-frozen', generated_version_id: 'version-frozen', generated_version_number: 2,
    input_revision: 2, section_id: 'original-section', section_title: 'Original section', paragraph_id: 'original-paragraph',
    paragraph_purpose: 'Full original purpose', intent_id: 'intent-original', intent_label: 'Original intent label',
    thought_id: 'thought-one', thought_text: 'First full thought.\nOriginal qualification 😀.',
    intent_thoughts: [{ thought_id: 'thought-one', text: 'First full thought.\nOriginal qualification 😀.' },
      { thought_id: 'thought-two', text: 'Second full thought.\nA different qualification.' }] };
  const frozen = { ...reviewContext, state: { ...reviewContext.state, manuscript_id: 'ms-frozen', generated_version_id: 'version-frozen' },
    evidence: [{ ...reviewContext.evidence[0], thought_id: 'thought-one', origins: [origin] },
      { ...reviewContext.evidence[0], evidence_id: 'shared-second', thought_id: 'thought-two', origins: [{ ...origin, thought_id: 'thought-two', thought_text: origin.intent_thoughts[1].text }] }] };
  const sourceComponent = all(child.render(), (node) => typeof node.type === 'function' && node.type.name === 'FrozenOrigin')[0].type;
  const source = runtime(sourceComponent, { row: frozen.evidence[0], context: frozen });
  assert(text(source.tree).includes(origin.thought_text));
  assert(text(source.tree).includes(origin.intent_thoughts[1].text));
  assert(text(source.tree).includes('固定成文 v2 · 作者原稿 r2'));
  assert.equal(all(source.tree, (node) => node.type === 'li' && node.props['aria-current'] === 'true').length, 1);
  assert.equal(all(source.tree, (node) => node.type === 'Checkbox' || node.type === 'Input' || node.type === 'Textarea').length, 0);
  const secondSource = runtime(sourceComponent, { row: frozen.evidence[1], context: frozen });
  assert.notEqual(text(named(source.tree, 'summary')), text(named(secondSource.tree, 'summary')));
  for (const invalid of [{ ...origin, manuscript_id: 'foreign' }, { ...origin, generated_version_id: 'later-version' },
    { ...origin, input_revision: 99 }, { ...origin, thought_id: 'another-thought' },
    { ...origin, intent_thoughts: [] }]) {
    const rejected = runtime(sourceComponent, { row: { ...frozen.evidence[0], origins: [invalid] }, context: frozen });
    assert(text(rejected.tree).includes('未记录可验证的固定版本原思想'));
    assert.equal(all(rejected.tree, (node) => node.type === 'details').length, 0);
  }
  assert(text(runtime(sourceComponent, { row: reviewContext.evidence[0], context: frozen }).tree).includes('未记录可验证的固定版本原思想'));
  console.log('PASS Shared sentences expose distinct full frozen Thoughts and Intent context; invalid or legacy origins stay unavailable');

  const historicalCheck = { check_id: 'fixed-check', created_at: '2026-10-15T00:00:00Z', outcome: 'MODIFIED', context: frozen,
    request: { claims: [{ start: 0, end: 5, text: 'Claim', evidence_ids: ['real-change'] }] } };
  const historyComponent = all(child.render(), (node) => typeof node.type === 'function' && node.type.name === 'ResponseHistory')[0].type;
  const historyTree = runtime(historyComponent, { history: [historicalCheck] }).tree;
  const historicalSource = all(historyTree, (node) => typeof node.type === 'function' && node.type.name === 'FrozenOrigin')[0];
  assert.equal(historicalSource.props.context, historicalCheck.context);
  assert(text(runtime(historicalSource.type, historicalSource.props).tree).includes(origin.thought_text));
  console.log('PASS Historical source view reads its original stored context without consulting the active editor');

  const layoutContext = { ...reviewContext, baseline_available: true, baseline_to_target_diff: '',
    evidence: [{ evidence_id: 'layout-real', change_id: 'margin-change', status: 'LAYOUT_ONLY',
      change_kind: 'PRESENTATION', supports_scientific_text_modification: false, changed_text: '',
      final_page: 1, final_line: 4 }] };
  let layoutRequest;
  const layoutReview = runtime(dialog.type, { ...dialog.props, context: layoutContext, disabled: false,
    onConfirm: async (request) => { layoutRequest = request; } });
  all(layoutReview.render(), (node) => node.type === 'input' && node.props.type === 'radio')[1].props.onChange();
  named(layoutReview.render(), 'Textarea').props.onSelect({ currentTarget: { selectionStart: 3, selectionEnd: 17 } });
  button(layoutReview, '加入所选修改声明').props.onClick();
  assert.equal(all(layoutReview.render(), (node) => node.type === 'Checkbox')[0].props.disabled, false);
  all(layoutReview.render(), (node) => node.type === 'Checkbox')[0].props.onCheckedChange(true);
  all(layoutReview.render(), (node) => node.type === 'Checkbox').at(-1).props.onCheckedChange(true);
  assert.equal(button(layoutReview, '作者确认并保存核对记录').props.disabled, false);
  button(layoutReview, '作者确认并保存核对记录').props.onClick();
  assert.equal(layoutRequest.outcome, 'PRESENTATION_MODIFIED');
  assert.equal(layoutRequest.claims.length, 1);
  assert.equal(layoutRequest.claims[0].evidence_ids[0], 'layout-real');
  all(layoutReview.render(), (node) => node.type === 'input' && node.props.type === 'radio')[0].props.onChange();
  assert.equal(all(layoutReview.render(), (node) => node.type === 'fieldset' && text(node.props.children).includes('修改声明 1')).length, 0);
  assert.equal(button(layoutReview, '作者确认并保存核对记录').props.disabled, true);
  const layoutHistory = runtime(historyComponent, { history: [{ ...historicalCheck, outcome: 'PRESENTATION_MODIFIED',
    context: layoutContext, request: { claims: layoutRequest.claims } }] });
  assert(text(layoutHistory.tree).includes('作者确认仅排版修改'));
  assert(text(layoutHistory.tree).includes('仅排版位置变化，正文、引用与素材未变'));
  assert(!text(layoutHistory.tree).includes('作者确认不修改及理由'));
  console.log('PASS Presentation acknowledgement uses its own evidence type without a prose diff; switching outcomes clears claims');

  const fixedRecordHash = 'a'.repeat(64), fixedAuthorHash = 'b'.repeat(64), fixedContextHash = 'c'.repeat(64);
  const legacyContext = { ...frozen, context_sha256: fixedContextHash,
    state: { ...frozen.state, comment_id: 'comment-a', generated_record_sha256: fixedRecordHash, current_author_document_sha256: fixedAuthorHash },
    evidence: [{ ...frozen.evidence[0], origins: undefined }] };
  const legacyCheck = JSON.parse(JSON.stringify({ ...historicalCheck, context: legacyContext }));
  const originalLegacyBytes = JSON.stringify(legacyCheck);
  const legacyHistory = runtime(historyComponent, { manuscriptId: 'ms-frozen', commentId: 'comment-a', history: [legacyCheck] });
  const legacyNode = all(legacyHistory.tree, (node) => typeof node.type === 'function' && node.type.name === 'LegacyOriginReadback')[0];
  assert(legacyNode, 'Only legacy rows without a stored snapshot expose explicit source readback');
  const completeReadback = { status: 'RECONSTRUCTED_FROM_FIXED_INPUT', check_id: legacyCheck.check_id,
    evidence_id: 'real-change', original_context_sha256: fixedContextHash,
    source: { manuscript_id: 'ms-frozen', generated_version_id: 'version-frozen', generated_version_number: 2,
      input_revision: 2, generated_record_sha256: fixedRecordHash, author_document_sha256: fixedAuthorHash }, origins: [origin] };
  const readAttempts = [];
  c.api.responseReviewOrigins = (...ids) => new Promise((resolve, reject) => readAttempts.push({ ids, resolve, reject }));
  const legacyRead = runtime(legacyNode.type, legacyNode.props);
  assert.equal(readAttempts.length, 0, 'Readback is explicit, never automatic while opening old history');
  const readButton = button(legacyRead, '回查当时固定版本的原思想');
  readButton.props.onClick(); readButton.props.onClick();
  assert.equal(readAttempts.length, 1, 'Repeated pointer activation during loading must keep one read');
  assert.deepEqual(readAttempts[0].ids, ['ms-frozen', 'comment-a', 'fixed-check', 'real-change']);
  assert(button(legacyRead, '正在补查当时固定输入…').props.disabled);
  readAttempts[0].resolve(completeReadback); await tick();
  assert(text(legacyRead.render()).includes('从当时固定输入补查 · 成文 v2 / 原稿 r2'));
  const recoveredOrigin = all(legacyRead.tree, (node) => typeof node.type === 'function' && node.type.name === 'FrozenOriginContent')[0];
  assert(text(runtime(recoveredOrigin.type, recoveredOrigin.props).tree).includes(origin.thought_text));
  assert(text(runtime(recoveredOrigin.type, recoveredOrigin.props).tree).includes(origin.intent_thoughts[1].text));
  assert.equal(JSON.stringify(legacyCheck), originalLegacyBytes, 'Supplemental results must not mutate historical context/evidence/request');
  assert.equal(all(legacyRead.tree, (node) => node.type === 'Checkbox' || node.type === 'Textarea' || node.type === 'Input').length, 0);
  legacyRead.unmount();
  console.log('PASS Legacy readback is an explicit single GET, labels its fixed input and preserves the exact historical record');

  for (const invalid of [
    { ...completeReadback, check_id: 'different-check' },
    { ...completeReadback, evidence_id: 'different-evidence' },
    { ...completeReadback, original_context_sha256: 'd'.repeat(64) },
    { ...completeReadback, status: 'CURRENT_EDITOR' },
    { ...completeReadback, source: undefined },
    ...Object.entries({ manuscript_id: 'another-manuscript', generated_version_id: 'latest-version', generated_version_number: 3,
      input_revision: 99, generated_record_sha256: 'e'.repeat(64), author_document_sha256: 'f'.repeat(64) })
      .map(([key, value]) => ({ ...completeReadback, source: { ...completeReadback.source, [key]: value } })),
    { ...completeReadback, origins: [{ ...origin, intent_thoughts: [...origin.intent_thoughts, origin.intent_thoughts[0]] }] },
    { ...completeReadback, origins: [{ ...origin, intent_label: null }] },
    { ...completeReadback, origins: [] },
  ]) {
    c.api.responseReviewOrigins = async () => invalid;
    const refused = runtime(legacyNode.type, legacyNode.props);
    button(refused, '回查当时固定版本的原思想').props.onClick(); await tick();
    assert(button(refused, '重试补查当时固定版本的原思想'));
    assert.equal(all(refused.render(), (node) => typeof node.type === 'function' && node.type.name === 'FrozenOriginContent').length, 0);
    assert(!text(refused.tree).includes(origin.thought_text)); refused.unmount();
  }
  const missingHash = runtime(legacyNode.type, { ...legacyNode.props,
    check: { ...legacyCheck, context: { ...legacyCheck.context, state: { ...legacyCheck.context.state, generated_record_sha256: undefined } } } });
  c.api.responseReviewOrigins = async () => completeReadback;
  button(missingHash, '回查当时固定版本的原思想').props.onClick(); await tick();
  assert(button(missingHash, '重试补查当时固定版本的原思想')); missingHash.unmount();
  console.log('PASS Supplemental origins reject wrong check/evidence/context/owner/version/revision/hashes and malformed full Intent data');

  let retryAttempt = 0;
  c.api.responseReviewOrigins = async () => {
    retryAttempt++;
    if (retryAttempt === 1) throw new Error('Declared connection failure');
    if (retryAttempt === 2) return { ...completeReadback, status: 'AMBIGUOUS', reason: 'AMBIGUOUS_ORIGINAL_THOUGHT', origins: [] };
    return { ...completeReadback, status: 'STORED_SNAPSHOT' };
  };
  const retryRead = runtime(legacyNode.type, legacyNode.props);
  button(retryRead, '回查当时固定版本的原思想').props.onClick(); await tick();
  button(retryRead, '重试补查当时固定版本的原思想').props.onClick(); await tick();
  assert(text(retryRead.render()).includes('无法唯一确定当时的原思想，不能推定来源。'));
  button(retryRead, '重试补查当时固定版本的原思想').props.onClick(); await tick();
  assert(text(retryRead.render()).includes('从原核对快照读取'));
  assert.equal(JSON.stringify(legacyCheck), originalLegacyBytes); retryRead.unmount();
  console.log('PASS Read errors and ambiguous old sources remain retryable without blocking or rewriting historical replies');

  for (const [reason, explanation] of [
    ['MISSING_FIXED_SOURCE_IDENTITY', '缺少当时的固定版本资料'],
    ['RECORDED_EVIDENCE_UNAVAILABLE', '依据资料不完整'],
    ['ORIGINAL_PROVENANCE_UNAVAILABLE', '原始来源资料不完整'],
    ['RECORDED_REALIZATION_UNAVAILABLE', '缺少当时的成文对应资料'],
    ['ORIGINAL_THOUGHT_UNAVAILABLE', '固定原稿中的思想资料不可用'],
    ['ORIGINAL_CONTEXT_INTEGRITY_FAILED', '原核对记录的摘要不一致'],
    ['FROZEN_RECORD_MISMATCH', '固定版本的摘要不一致'],
    ['FROZEN_TEXT_MISMATCH', '固定版本的正文核对不一致'],
    ['FROZEN_AUTHOR_INPUT_MISMATCH', '固定作者原稿核对不一致'],
    ['RECORDED_REALIZATION_MISMATCH', '当时的成文对应核对不一致'],
    ['STORED_ORIGIN_MISMATCH', '已保存的固定来源核对不一致'],
    ['AMBIGUOUS_RECORDED_EVIDENCE', '无法唯一确定当时的成文依据'],
    ['AMBIGUOUS_ORIGINAL_THOUGHT', '无法唯一确定当时的原思想'],
    ['UNKNOWN_INTERNAL_REASON_CODE', '当时的固定来源暂时无法核对，请稍后重试。'],
    ['constructor', '当时的固定来源暂时无法核对，请稍后重试。'],
    ['Internal storage path C:/private/original.db', '当时的固定来源暂时无法核对，请稍后重试。'],
  ]) {
    c.api.responseReviewOrigins = async () => ({ ...completeReadback,
      status: reason.startsWith('AMBIGUOUS_') ? 'AMBIGUOUS' : 'UNAVAILABLE', reason, origins: [] });
    const explained = runtime(legacyNode.type, legacyNode.props);
    button(explained, '回查当时固定版本的原思想').props.onClick(); await tick();
    assert(text(explained.render()).includes(explanation));
    assert(!text(explained.tree).includes(reason), 'Internal reason strings must not appear in the user-facing explanation');
    assert(button(explained, '重试补查当时固定版本的原思想'));
    assert.equal(JSON.stringify(legacyCheck), originalLegacyBytes); explained.unmount();
  }
  console.log('PASS Known readback failures have concise Chinese explanations; unknown internal details remain hidden and retryable');

  const pendingReads = [];
  c.api.responseReviewOrigins = (...ids) => new Promise((resolve) => pendingReads.push({ ids, resolve }));
  const raced = runtime(legacyNode.type, legacyNode.props);
  button(raced, '回查当时固定版本的原思想').props.onClick();
  const nextRow = { ...legacyNode.props.row, evidence_id: 'next-evidence' };
  const nextCheck = { ...legacyCheck, check_id: 'next-check', context: { ...legacyCheck.context, context_sha256: 'd'.repeat(64), evidence: [nextRow] } };
  raced.props = { ...legacyNode.props, row: nextRow, check: nextCheck }; raced.render();
  button(raced, '回查当时固定版本的原思想').props.onClick();
  pendingReads[1].resolve({ ...completeReadback, check_id: 'next-check', evidence_id: 'next-evidence', original_context_sha256: 'd'.repeat(64) }); await tick();
  const nextResult = JSON.stringify(raced.render());
  pendingReads[0].resolve(completeReadback); await tick();
  assert.equal(JSON.stringify(raced.render()), nextResult, 'A late previous check must not replace the current check source');
  raced.unmount();
  const detached = runtime(legacyNode.type, legacyNode.props);
  button(detached, '回查当时固定版本的原思想').props.onClick(); detached.unmount();
  const detachedState = JSON.stringify(detached.slots);
  pendingReads[2].resolve(completeReadback); await tick();
  assert.equal(JSON.stringify(detached.slots), detachedState, 'Unmounted readback ignores late network results');
  console.log('PASS Switching historical checks and unmounting suppress late source results');

  const apiModule = { exports: {} }, observedRequests = [];
  const apiSource = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../../lib/studio-api.ts'), 'utf8'),
    { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInNewContext(apiSource, { module: apiModule, exports: apiModule.exports, process: { env: { NEXT_PUBLIC_RSTV4_API: 'http://declared-fixture/api' } },
    Headers, FormData, require: (name) => { assert.equal(name, './studio-downloads'); return { studioFileUrl: () => { throw new Error('No download expected'); } }; },
    fetch: async (url, init) => { observedRequests.push({ url, init }); return { ok: true, json: async () => completeReadback }; } });
  await apiModule.exports.studioApi.responseReviewOrigins('ms/a', 'comment ?', 'check/#', 'evidence +');
  assert.equal(observedRequests[0].url, 'http://declared-fixture/api/manuscripts/ms%2Fa/comments/comment%20%3F/response-checks/check%2F%23/origins/evidence%20%2B');
  assert.equal(observedRequests[0].init.method, 'GET');
  assert.equal(observedRequests[0].init.cache, 'no-store');
  assert.equal(observedRequests[0].init.body, undefined);
  console.log('PASS The shipped supplemental-origin client uses an encoded read-only no-store GET and sends no body');
})().catch((error) => { console.error(error); process.exitCode = 1; });
