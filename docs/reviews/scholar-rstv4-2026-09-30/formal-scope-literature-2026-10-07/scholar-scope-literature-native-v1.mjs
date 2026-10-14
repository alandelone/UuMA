import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const [,, fixturePath, out] = process.argv;
const fixture = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
const requests = [];
const api = async (path, body) => {
  const response = await fetch(fixture.base + path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {});
  const data = await response.json();
  requests.push({ path, body, status: response.status, data });
  if (!response.ok) { const error = Error(data.detail); error.status = response.status; throw error; }
  return data;
};
const js = await (await fetch(fixture.base + '/catalog-research-overview.js')).text();
assert.equal(js, fs.readFileSync(fixture.source_dir + '/catalog_research_overview.js', 'utf8'));
const html = await (await fetch(fixture.base + '/')).text();
assert.equal(html, fs.readFileSync(fixture.source_dir + '/catalog_web.html', 'utf8'));
const elements = new Map();
const context = vm.createContext({ URL, api, escapeHtml: value => String(value), errorText: error => error.message,
  $: name => { if (!elements.has(name)) elements.set(name, { textContent: '', innerHTML: '', hidden: false }); return elements.get(name); },
  renderTable: () => {}, queryFilter: () => null, activeColumns: () => ['title'] });
vm.runInContext(js, context);
const overview = await api('/api/catalog/research-overview');
const count = overview.literature_counts.find(item => item.kind === 'field' && item.field_id === fixture.field_id);
assert.equal(count.paper_count, 1);
const row = { level: 'topic', field: { field_id: fixture.field_id }, topic: { topic_id: fixture.topic_id } };
const url = context.RSTV4Overview.literatureUrl(row, fixture.base + '/?overview_state=original-position');
context.location = { href: url };
const handlers = html.slice(html.indexOf('      function scopeReasons('), html.indexOf('      async function loadSummary('));
vm.runInContext('let paperQueryToken=0,result=null,page=1,pageSize=50,sorts=[{field:"updated_at",direction:"desc"}];\n' + handlers, context);
await context.loadPapers();
const result = vm.runInContext('result', context);
assert.equal(result.total, 1);
assert.equal(result.items[0].paper_id, fixture.paper_id);
assert.ok(result.items[0].scope_association.reasons.length);
assert.equal(result.scope.scope.kind, 'topic');
assert.equal(result.scope.scientific_approval, false);
assert.match(elements.get('scope-literature').innerHTML, /范围文献/);
const paper = await api('/api/catalog/papers/' + fixture.paper_id);
assert.equal(paper.paper_id, fixture.paper_id);
await assert.rejects(() => api('/api/catalog/papers/query', { scope: { kind: 'topic', field_id: 'missing', object_id: fixture.topic_id } }), error => error.status === 404);
const normal = await api('/api/catalog/papers/query', {});
assert.equal(normal.total, 1);
fs.writeFileSync(out, JSON.stringify({ status: 'PASS_SHIPPED_SCOPE_QUERY_HANDLER_AND_EXACT_PAPER', url, requests, browser_verified: false, scientific_approval: false }, null, 2), { flag: 'wx' });
process.stdout.write('Actual scope list, original paper and invalid-owner readback passed\n');
