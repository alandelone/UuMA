/* Execute shipped history helpers; deterministic fixtures, no browser claim. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const file = path.resolve(__dirname, '../../lib/studio-discussion-history.ts');
const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const sandbox = { exports: {} };
vm.runInNewContext(code, sandbox, { filename: file });
const { historyFilter, matchesHistory, legacySelection } = sandbox.exports;
const own = (value) => JSON.parse(JSON.stringify(value));
let passed = 0;
function check(name, fn) { fn(); passed++; console.log(`PASS ${name}`); }
const message = { anchor_type: 'thought', anchor_id: 'stable', anchor_revision: 2, quoted: {} };
check('current object excludes another revision and another kind with the same ID', () => {
  const selected = { type: 'thought', id: 'stable' };
  assert.equal(matchesHistory(message, selected, 2), true);
  assert.equal(matchesHistory({ ...message, anchor_revision: 1 }, selected, 2), false);
  assert.equal(matchesHistory({ ...message, anchor_type: 'intent' }, selected, 2), false);
});
check('generated filter distinguishes two versions with the same author revision', () => {
  const selected = { type: 'generated_paragraph', id: 'anchor', anchorRevision: 1, quote: { generated_version_id: 'old-version' } };
  const row = { anchor_type: selected.type, anchor_id: selected.id, anchor_revision: 1, quoted: { source: { generated_version_id: 'old-version' } } };
  assert.deepEqual(own(historyFilter(selected, 9)), { anchor_type: selected.type, anchor_revision: 1, generated_version_id: 'old-version' });
  assert.equal(matchesHistory(row, selected, 9), true);
  assert.equal(matchesHistory({ ...row, quoted: { source: { generated_version_id: 'new-version' } } }, selected, 9), false);
});
const original = { message_id: 'old-independent-message', quote: { text: '😀', start: 4, end: 6, offset_unit: 'utf16', annotation: 'Original annotation', object_text: 'Old 😀 text', source: { manuscript_id: 'owned', anchor_type: 'thought', anchor_id: 'stable', anchor_revision: 1, label: 'Original thought' } } };
check('legacy author context preserves exact ID revision Unicode quote and annotation', () => {
  const before = JSON.stringify(original), selected = legacySelection(original, 'owned');
  assert.equal(selected.id, 'stable'); assert.equal(selected.anchorRevision, 1);
  assert.deepEqual(own(selected.quote), original.quote);
  assert.equal(JSON.stringify(original), before);
});
check('another manuscript cannot supply the legacy binding', () => {
  assert.throws(() => legacySelection(original, 'another'), /不属于/);
});
check('legacy generated context uses its verified immutable version and anchor', () => {
  const context = { ...original, quote: { ...original.quote, source: { ...original.quote.source, anchor_type: 'generated_paragraph', anchor_id: 'original-anchor', generated_version_id: 'original-version', author_revision_known: false, anchor_revision: 0 } }, generated: { generated_version_id: 'original-version' }, block: { anchor_id: 'original-anchor' } };
  const selected = legacySelection(context, 'owned');
  assert.equal(selected.quote.generated_version_id, 'original-version');
  assert.equal(selected.id, 'original-anchor'); assert.equal(selected.anchorRevision, 0);
  assert.equal(selected.authorRevisionKnown, false);
});
check('damaged generated object cannot be redirected to a neighboring anchor', () => {
  const context = { ...original, quote: { ...original.quote, source: { ...original.quote.source, anchor_type: 'generated_paragraph', generated_version_id: 'original-version' } }, generated: { generated_version_id: 'another-version' }, block: { anchor_id: 'neighbor' } };
  assert.throws(() => legacySelection(context, 'owned'), /不可用/);
});
console.log(`${passed} controlled Studio history helper checks passed`);
