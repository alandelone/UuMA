import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const moduleRecord = { exports: {} };
const source = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../../lib/catalog-return.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
vm.runInNewContext(source, { module: moduleRecord, exports: moduleRecord.exports, URL, URLSearchParams });
const { catalogReturnUrl } = moduleRecord.exports;
const base = 'http://127.0.0.1:8885/';
const target = new URL(base); target.searchParams.set('overview_state', JSON.stringify({ workspace: 'known', collapsed: ['real-id'], scroll: 123 })); target.searchParams.set('track', 'owned');
const search = new URLSearchParams({ return: target.href, track: 'fallback' }).toString();
assert.equal(catalogReturnUrl(search, base), target.href);
for (const candidate of ['https://example.com/', 'http://127.0.0.1:8875/', 'http://localhost:8885/',
  'http://user:password@127.0.0.1:8885/', `${base}evil`, `${base}?view=all`, `${base}#external`, 'javascript:alert(1)', 'bad URL']) {
  assert.equal(catalogReturnUrl(new URLSearchParams({ return: candidate, track: 'fallback' }).toString(), base), `${base}?track=fallback`);
}
assert.equal(catalogReturnUrl('from=catalog&track=original', 'http://127.0.0.1:8875/'), 'http://127.0.0.1:8875/?track=original');
process.stdout.write('11 Catalog return origin/context cases passed\n');
