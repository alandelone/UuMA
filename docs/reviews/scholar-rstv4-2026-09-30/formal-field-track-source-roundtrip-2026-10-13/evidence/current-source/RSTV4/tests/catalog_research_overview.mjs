/* Controlled execution of the shipped list and editor. No browser/visual claim. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(__dirname, '../src/rstv4/catalog_research_overview.js'), 'utf8');
let uuid = 0;
const context = { URL, Set, Map, crypto: { randomUUID: () => `request-${++uuid}` },
  FormData: class { constructor(form) { this.form = form; } entries() { return Object.entries(this.form.values); } } };
vm.runInNewContext(source, context);
const ui = context.RSTV4Overview;
const plain = value => JSON.parse(JSON.stringify(value));
const data = () => ({ workspace_id: 'workspace-a', fields: [{ field_id: 'f1', name: 'Energy' }, { field_id: 'f2', name: 'Justice' }],
  topics: [{ topic_id: 't1', name: 'Trading' }], field_topics: [{ field_id: 'f1', topic_id: 't1' }, { field_id: 'f2', topic_id: 't1' }],
  tracks: [{ track_id: 'r1', field_id: 'f1', primary_topic_id: 't1', title: 'First' }, { track_id: 'r2', field_id: 'f2', primary_topic_id: 't1', title: 'Second' }],
  questions: [{ node_id: 'q1', track_id: 'r1', statement: 'Question 1' }, { node_id: 'q2', track_id: 'r1', statement: 'Question 2' }],
  manuscripts: [{ manuscript_id: 'm1', track_id: 'r1', title: 'Linked' }, { manuscript_id: 'm2', track_id: 'r1', title: 'Independent' }],
  manuscript_questions: [{ manuscript_id: 'm1', node_id: 'q1' }, { manuscript_id: 'm1', node_id: 'q2' }] });
function storage() { const values = new Map(); return { getItem: id => values.get(id) || null, setItem: (id, value) => values.set(id, value), removeItem: id => values.delete(id), values }; }
function element() { return { events: {}, disabled: false, textContent: '', addEventListener(name, fn) { this.events[name] = fn; }, setAttribute(name, value) { this[name] = value; } }; }
function listSetup(location = { href: 'http://127.0.0.1:8885/', origin: 'http://127.0.0.1:8885' }, local = storage()) {
  const doc = { activeElement: null }, viewport = { ...element(), scrollY: 0, scrollTo(x, y) { this.scrollY = y; }, scrollBy(x, y) { this.scrollY += y; }, requestAnimationFrame(fn) { fn(); } };
  let rendered = [];
  const tree = { ...element(), ownerDocument: doc, closest() { return null; }, querySelectorAll(selector) { return selector === '.overview-row' ? rendered : rendered.filter(r => r.link).map(r => r.link); },
    set innerHTML(value) {
      rendered = JSON.parse(`[${value.split('}{').join('},{')}]`).map(row => {
        const toggle = element(), el = { ...element(), dataset: { node: row.key }, hidden: false, getAttribute(name) { return name === 'role' ? 'treeitem' : this[name]; },
          closest() { return this; }, focus() { doc.activeElement = this; }, scrollIntoView() {},
          getBoundingClientRect() { const top = rendered.filter(r => !r.hidden).indexOf(this) * 60 - viewport.scrollY; return { top, bottom: top + 60 }; },
          querySelector() { return toggle; } };
        if (row.level === 'paper') el.link = { dataset: { manuscriptId: row.record.manuscript_id, trackId: row.track.track_id }, href: '' };
        return el;
      });
    } };
  const history = { state: {}, replaceState(state, unused, url) { this.state = state; location.href = String(url); } };
  const list = ui.createList({ tree, renderRow: row => JSON.stringify(row), storage: local, location, history, viewport });
  return { list, tree, doc, viewport, location, local, rows: () => rendered };
}

let passed = 0;
function test(name, fn) { fn(); passed++; process.stdout.write(`PASS ${name}\n`); }
test('global hierarchy, shared Topic and manuscript ownership have stable identities', () => {
  const original = ui.buildRows(data()), changed = data(); changed.fields.reverse(); changed.manuscripts.reverse();
  const reordered = ui.buildRows(changed);
  assert.deepEqual(original.map(r => r.key).sort(), reordered.map(r => r.key).sort());
  assert.equal(new Set(original.map(r => r.key)).size, original.length);
  assert.equal(original.filter(r => r.level === 'topic').length, 2);
  const linked = original.filter(r => r.level === 'paper' && r.record.manuscript_id === 'm1');
  assert.equal(linked.length, 2); assert.ok(linked.every(r => r.track.track_id === 'r1' && r.depth === 5));
  const unlinked = original.find(r => r.record.manuscript_id === 'm2');
  assert.equal(unlinked.parent, ui.key('track', 'r1')); assert.equal(unlinked.depth, 4);
});
test('folding a Field hides every descendant while all other Fields remain', () => {
  const rows = ui.buildRows(data()), visible = ui.visibleRows(rows, new Set([ui.key('field', 'f1')]));
  assert.equal(visible.filter(r => r.field.field_id === 'f1').length, 1);
  assert.equal(visible.filter(r => r.level === 'field').length, 2);
  assert.ok(visible.some(r => r.record.track_id === 'r2'));
});
test('deleted and malformed navigation state cannot select a neighboring object', () => {
  const rows = ui.buildRows(data()), known = ui.key('field', 'f1');
  const state = ui.reconcileState(rows, { collapsed: [known, 'deleted'], focus: 'deleted', anchor: 'deleted', offset: 'bad', scroll: -3 });
  assert.deepEqual(plain(state), { collapsed: [known], focus: '', anchor: '', offset: 0, scroll: 0 });
  assert.deepEqual(plain(ui.reconcileState(rows, { collapsed: 'bad' }).collapsed), []);
});
test('actual keyboard handler expands, enters a child, returns to parent and reaches End', () => {
  const s = listSetup(); s.list.load(data()); const field = ui.key('field', 'f1'); s.list.toggle(field);
  let target = s.rows().find(r => r.dataset.node === field), prevented = false;
  const press = key => s.tree.events.keydown({ target, key, preventDefault() { prevented = true; } });
  press('ArrowRight'); assert.equal(target['aria-expanded'], 'true'); assert.ok(prevented);
  press('ArrowRight'); assert.equal(s.doc.activeElement.dataset.node, ui.key('topic', 'f1', 't1'));
  target = s.doc.activeElement; press('ArrowLeft'); assert.equal(target['aria-expanded'], 'false');
  press('ArrowLeft'); assert.equal(s.doc.activeElement.dataset.node, field);
  target = s.doc.activeElement; press('End'); assert.equal(s.doc.activeElement.dataset.node, ui.key('track', 'r2'));
});
test('actual list preserves folds, focus and viewport anchor through refresh and return', () => {
  const s = listSetup(); s.list.load(data()); s.viewport.scrollY = 75;
  const field = ui.key('field', 'f2'); s.list.toggle(field);
  const before = JSON.parse(new URL(s.location.href).searchParams.get('overview_state'));
  const changed = data(); changed.fields.reverse(); s.list.load(changed);
  assert.equal(s.rows().find(r => r.dataset.node === field)['aria-expanded'], 'false');
  assert.ok(s.rows().find(r => r.dataset.node === ui.key('track', 'r2')).hidden);
  assert.equal(s.doc.activeElement.dataset.node, field);
  const anchor = s.rows().find(r => r.dataset.node === before.anchor);
  assert.equal(anchor.getBoundingClientRect().top, before.offset);
  const fresh = listSetup({ ...s.location }, s.local); fresh.list.load(changed);
  assert.equal(fresh.rows().find(r => r.dataset.node === field)['aria-expanded'], 'false');
  assert.equal(fresh.doc.activeElement.dataset.node, field);
  assert.equal(fresh.rows().find(r => r.dataset.node === before.anchor).getBoundingClientRect().top, before.offset);
  const link = fresh.rows().find(r => r.link).link, url = new URL(link.href);
  assert.equal(url.searchParams.get('manuscript'), 'm1'); assert.equal(url.searchParams.get('track'), 'r1');
  assert.equal(new URL(url.searchParams.get('return')).origin, 'http://127.0.0.1:8885');
});
test('a different Catalog database cannot inherit previous folds', () => {
  const s = listSetup(); s.list.load(data()); s.list.toggle(ui.key('field', 'f1'));
  const other = data(); other.workspace_id = 'workspace-b'; s.list.load(other);
  assert.equal(s.rows().find(r => r.dataset.node === ui.key('field', 'f1'))['aria-expanded'], 'true');
});
test('returning from another view restores overview position without capturing that view', () => {
  const s = listSetup(); s.list.load(data()); s.viewport.scrollY = 125; s.list.capture();
  const before = JSON.parse(new URL(s.location.href).searchParams.get('overview_state'));
  s.viewport.scrollY = 0;
  s.list.load(data(), false);
  assert.equal(s.rows().find(r => r.dataset.node === before.anchor).getBoundingClientRect().top, before.offset);
  assert.equal(s.viewport.scrollY, 125);
});

function editorSetup(local = storage(), fetchAction = async body => body, draftNamespace = 'controlled-tab') {
  const message = element(), submit = element(), close = element(), title = element(), form = { ...element(), values: {}, querySelector() { return submit; } };
  let controls = [], comparison;
  const body = { ...element(), set innerHTML(value) {
    form.values = {};
    for (const match of value.matchAll(/<(input|textarea|select) name="([^"]+)"[^>]*>([\s\S]*?)<\/\1>|<input name="([^"]+)" value="([^"]*)"[^>]*>/g)) {
      const name = match[2] || match[4]; form.values[name] = match[5] || (match[1] === 'textarea' ? match[3] : '');
    }
    controls = Object.keys(form.values).map(name => ({ name, disabled: false }));
  }, querySelectorAll() { return controls; }, append(node) { comparison = node; } };
  const dialog = { ...element(), open: false, showModal() { this.open = true; }, close() { this.open = false; },
    querySelector(selector) { return ({ form, '[data-editor-body]': body, '[role="status"]': message, h2: title, '[data-editor-close]': close })[selector]; },
    ownerDocument: { createElement() { const button = element(); return { querySelector() { return button; }, remove() { comparison = null; } }; } } };
  let latest = { workspace_id: 'workspace-a', fields: [{ field_id: 'f1', name: 'Energy' }], field_topics: [], topics: [] };
  const saved = [], editor = ui.createEditor({ dialog, storage: local, getData: () => latest, onSaved: async value => saved.push(value), fetchAction, escapeHtml: value => String(value), draftNamespace });
  return { editor, form, dialog, local, saved, controls: () => controls, message, submit, close,
    compare: () => comparison?.querySelector('button').events.click(), latest: value => { latest = value; } };
}
async function asyncTests() {
  const attempts = [];
  const s = editorSetup(storage(), async body => { attempts.push(plain(body)); if (attempts.length === 1) throw new Error('connection lost'); return { object_id: 'f-new' }; });
  s.editor.open('CREATE_FIELD'); s.form.values = { name: 'New Field', description: 'Local draft' }; s.form.events.input();
  s.close.events.click(); s.editor.open('CREATE_FIELD'); assert.equal(s.form.values.name, 'New Field');
  await s.form.events.submit({ preventDefault() {} }); assert.equal(attempts.length, 1); assert.ok(s.controls().every(input => input.disabled));
  s.close.events.click(); s.editor.open('CREATE_FIELD'); await s.form.events.submit({ preventDefault() {} });
  assert.deepEqual(attempts[0], attempts[1]); assert.equal(s.saved.length, 1); assert.equal(s.dialog.open, false);
  assert.equal(s.local.values.size, 0); passed++; process.stdout.write('PASS actual editor preserves draft and retries the exact uncertain request\n');

  const conflict = editorSetup(storage(), async () => { const e = new Error('changed on server'); e.status = 409; throw e; });
  const old = { field: { field_id: 'f1', name: 'Old', description: 'Before', metadata_digest: 'old' } };
  conflict.editor.open('EDIT_FIELD', old); conflict.form.values.name = 'My draft'; conflict.form.events.input();
  await conflict.form.events.submit({ preventDefault() {} }); assert.match(conflict.message.textContent, /草稿仍在/);
  conflict.close.events.click(); conflict.editor.open('EDIT_FIELD', { field: { ...old.field, name: 'Other editor', metadata_digest: 'new' } });
  assert.ok(conflict.submit.disabled); assert.equal(conflict.form.values.name, 'My draft');
  conflict.compare(); assert.equal(conflict.submit.disabled, false);
  const draft = JSON.parse([...conflict.local.values.values()][0]); assert.equal(draft.expected_digest, 'new');
  passed++; process.stdout.write('PASS actual conflict retains draft and requires explicit comparison before rebasing\n');

  const failStorage = storage(); failStorage.setItem = () => { throw new Error('storage denied'); };
  let calls = 0;
  const denied = editorSetup(failStorage, async () => { calls++; });
  denied.editor.open('CREATE_FIELD'); denied.form.values = { name: 'No storage', description: '' };
  await denied.form.events.submit({ preventDefault() {} }); assert.equal(calls, 0); assert.match(denied.message.textContent, /无法保存提交凭据/);
  passed++; process.stdout.write('PASS unavailable storage blocks an untraceable create request\n');

  const shared = storage(), first = editorSetup(shared, undefined, 'tab-one'), second = editorSetup(shared, undefined, 'tab-two');
  first.editor.open('CREATE_FIELD'); first.form.values = { name: 'First tab', description: '' }; first.form.events.input();
  second.editor.open('CREATE_FIELD'); second.form.values = { name: 'Second tab', description: '' }; second.form.events.input();
  const reload = editorSetup(shared, undefined, 'tab-one'); reload.editor.open('CREATE_FIELD');
  assert.equal(reload.form.values.name, 'First tab'); assert.equal(shared.values.size, 2);
  passed++; process.stdout.write('PASS two tab namespaces preserve independent drafts across reload\n');
}
asyncTests().then(() => process.stdout.write(`${passed} controlled overview scenarios passed\n`)).catch(error => { process.stderr.write(`${error.stack}\n`); process.exitCode = 1; });
