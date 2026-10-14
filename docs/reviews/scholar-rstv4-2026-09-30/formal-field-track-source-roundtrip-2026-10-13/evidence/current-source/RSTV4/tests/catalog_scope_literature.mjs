import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const context = { URL };
vm.runInNewContext(fs.readFileSync(new URL('../src/rstv4/catalog_research_overview.js', import.meta.url), 'utf8'), context);
const ui = context.RSTV4Overview;
const row = { level: 'topic', field: { field_id: 'field &1' }, topic: { topic_id: '共享主题' } };
const url = ui.literatureUrl(row, 'http://localhost/?overview_state=retained&paper=old&snapshot=old&scope_excluded=true');
const actual = new URL(url);
assert.equal(actual.searchParams.get('overview_state'), 'retained');
assert.equal(actual.searchParams.get('view'), 'all');
assert.equal(actual.searchParams.get('scope_field_id'), 'field &1');
assert.equal(actual.searchParams.get('scope_object_id'), '共享主题');
assert.equal(actual.searchParams.has('paper'), false);
assert.equal(actual.searchParams.has('snapshot'), false);
assert.equal(actual.searchParams.has('scope_excluded'), false);
const parsed = ui.scopeFromUrl(url);
assert.equal(parsed.kind, 'topic'); assert.equal(parsed.field_id, 'field &1'); assert.equal(parsed.object_id, '共享主题');
assert.equal(ui.scopeFromUrl('http://localhost/?view=all'), null);
for (const query of ['scope_kind=topic', 'scope_excluded=true', 'scope_kind=unknown&scope_field_id=f&scope_object_id=x']) {
  assert.throws(() => ui.scopeFromUrl('http://localhost/?' + query), /范围链接不完整/);
}
assert.equal(ui.literatureUrl({ level: 'paper', field: row.field, record: { manuscript_id: 'ms' } }, 'http://localhost/'), null);
assert.equal(ui.scopeFromUrl(url + '&scope_excluded=true').include_excluded, true);
const other = ui.literatureUrl({ ...row, field: { field_id: 'different' } }, url);
assert.equal(ui.scopeFromUrl(other).field_id, 'different');
const html = fs.readFileSync(new URL('../src/rstv4/catalog_web.html', import.meta.url), 'utf8');
const handlers = html.slice(html.indexOf('      function scopeReasons('), html.indexOf('      async function loadSummary('));
const elements = new Map();
const pending = [];
let requests = 0, renders = 0;
Object.assign(context, {
  location: { href: url },
  $: name => { if (!elements.has(name)) elements.set(name, { textContent: '', innerHTML: '', hidden: false }); return elements.get(name); },
  api: (path, body) => { requests++; return new Promise(resolve => pending.push({ path, body, resolve })); },
  renderTable: () => { renders++; },
  queryFilter: () => ({ type: 'rule', field: 'title', operator: 'contains', value: 'scope' }),
  activeColumns: () => ['title'],
  escapeHtml: text => String(text).replaceAll('<', '&lt;'),
  errorText: error => error.message,
});
vm.runInNewContext('let paperQueryToken=0,result=null,page=2,pageSize=50,sorts=[{field:"title",direction:"asc"}];\n' + handlers + '\nconst getResult=()=>result;', context);
const old = context.loadPapers();
assert.equal(pending[0].body.scope.object_id, '共享主题');
assert.equal(pending[0].body.page, 2);
assert.equal(pending[0].body.filter.value, 'scope');
context.location.href = other;
const fresh = context.loadPapers();
pending[1].resolve({ scope: { title: 'Fresh', paper_count: 1, excluded_count: 0, unavailable_sources: [] }, items: [{ paper_id: 'fresh' }] });
await fresh;
pending[0].resolve({ scope: { title: 'Old', paper_count: 1, excluded_count: 0, unavailable_sources: [] }, items: [{ paper_id: 'old' }] });
await old;
assert.equal(vm.runInNewContext('getResult().items[0].paper_id', context), 'fresh');
assert.equal(renders, 1);
assert.match(elements.get('scope-literature').innerHTML, /Fresh/);
context.location.href = 'http://localhost/?scope_kind=topic';
await context.loadPapers();
assert.equal(requests, 2); // Malformed scope never queries the entire Catalog.
assert.match(elements.get('paper-body').innerHTML, /范围链接不完整/);
assert.match(context.scopeReasons({ association_status: 'CANDIDATE', excluded: false, reasons: [{ kind: 'collection', name: '<unsafe>', discovery_kind: 'REFERENCE', membership_status: 'DISCOVERED', screening: null, excluded: false }] }), /&lt;unsafe>/);
const element = { classList: { toggle() {}, remove() {} }, setAttribute() {}, textContent: 'Catalog' };
const navigation = { href: url };
const nav = { URL, location: navigation, history: { pushState(a,b,destination) { navigation.href=String(destination); } },
  document: { querySelectorAll: () => [], querySelector: () => element }, $: () => element,
  scientificReview: { leave() {} }, reviewWorkflow: { leave() {} }, researchChat: { leave() {} },
  overviewList: { capture() {} }, researchWorkspaces: { cancelLoad() {} },
  loadCases: () => Promise.resolve(), loadPapers: () => Promise.resolve(), openPaper: () => Promise.resolve() };
const setView = html.slice(html.indexOf('      function setView('), html.indexOf('      function toggleOverviewNode('));
vm.runInNewContext("let view='all',page=1,paperQueryToken=0,reviewTotal=0,collectionDetailToken=0,collectionDetails=null;" + setView, nav);
await nav.setView('review_queue');
assert.equal(ui.scopeFromUrl(navigation.href).object_id, '共享主题');
await nav.setView('all');
assert.equal(ui.scopeFromUrl(navigation.href).field_id, 'field &1');
const cleared = ui.clearLiteratureScope(navigation.href);
assert.equal(ui.scopeFromUrl(cleared), null);
assert.equal(new URL(cleared).searchParams.get('overview_state'), 'retained');
assert.match(html, /if\(t\.dataset\.view\)\{history\.replaceState\(\{\},'',RSTV4Overview\.clearLiteratureScope\(location\.href\)\);setView\(t\.dataset\.view\);\}/);
process.stdout.write('11 actual scope navigation, review-return, query-handler, late-response and invalid-link checks passed\n');
