/* Execute the shipped module and handlers with a controlled DOM. No browser claim. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source = fs.readFileSync(new URL('../src/rstv4/catalog_research_workspaces.js', import.meta.url), 'utf8');
let uuid = 0;
const context = { URL, Intl, crypto: { randomUUID: () => `request-${++uuid}` }, FormData: class {
  constructor(form) { this.form = form; } get(name) { return this.form.values[name]; } getAll(name) { return this.form.values[name] || []; }
} };
vm.runInNewContext(source, context);
const ui = context.RSTV4ResearchWorkspaces, plain = value => JSON.parse(JSON.stringify(value));
const key = (kind, value) => JSON.stringify([kind, value]);
const decode = value => value.replaceAll('&quot;', '"').replaceAll('&#39;', "'").replaceAll('&lt;', '<').replaceAll('&gt;', '>').replaceAll('&amp;', '&');
const element = () => ({ events: {}, disabled: false, textContent: '', dataset: {}, focused: false,
  addEventListener(name, fn) { this.events[name] = fn; }, setAttribute(name, value) { this[name] = value; },
  classList: { toggle() {}, remove() {}, add() {} }, focus() { this.focused = true; }, scrollIntoView() { this.scrolled = true; }, closest() { return this; },
  hasAttribute(name) { return Object.hasOwn(this.dataset, name.replace(/^data-/, '').replace(/-([a-z])/g, (_, c) => c.toUpperCase())); } });
const storage = () => { const values = new Map(); return { values, getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) }; };
const savedSource = () => ({ paper_id: 'paper', title: '<Original paper>', paper_version: 2, paper_version_id: 'pv2', skeleton_id: 's3', version: 3, pdf_digest: 'pdf-sha', parsed_digest: 'raw-sha', extractor_model: 'actual-extractor', prompt_version: 'actual-contract', context_sha256: 'source-context',
  units: [{ unit_id: 'u1', raw_text: 'Exact original sentence', seq_idx: 4, page_idx: 3, section: 'Introduction', layer1: { coref_resolved: 'Exact original sentence' }, layer2: { role: 'context' }, layer3: { intent: 'Research_Gap' }, layer4: 'Problem_Gap', content_digest: 'unit-sha' }],
  triplets: [{ triplet_id: 'tr1', unit_id: 'u1', subject: 'Field term', predicate: 'supports', object: 'field term' }] });
const fieldData = () => { const source = savedSource(), candidate = { candidate_id: 'c1', build_id: 'b1', unit_id: 'u1', status: 'PROPOSED', statement: 'Candidate statement', excerpt: 'Exact original sentence', revision: 1, relation: 'SUPPORTS' };
  const gap = { candidate_gap_id: 'g1', build_id: 'b1', statement: 'Candidate gap', status: 'PROPOSED', revision: 1, rationale: 'Source rationale', conditions_json: '["under original conditions"]' };
  return { field: { field_id: 'f1', name: 'Selected Field' }, sources: [source], candidates: [{ record: candidate, source, context_sha256: 'candidate-old' }], candidate_gaps: [{ record: gap, references: [{ kind: 'candidate', record: candidate }], context_sha256: 'gap-old' }], evidence: [], citations: [], tracks: [], snapshots: [], selected_snapshot: null,
    builds: [{ build_id: 'b1', status: 'EXTRACTING_EVIDENCE', revision: 1, context_sha256: 'build-old', sources: [source], papers: [{ status: 'IMPORTED' }], evidence_candidates: [candidate], candidate_gaps: [gap], retrieval_scope: { source: 'EXISTING_PAPERSKELETON' } }], projection: { outbox: [] } }; };
function setup(fetch, local = storage(), namespace = 'tab-one') {
  const form = { ...element(), values: {}, querySelector: () => submit }, submit = element(), status = element(), close = element(), title = element();
  let html = '', controls = [], comparison, selections = [];
  const body = { ...element(), get innerHTML() { return html; }, set innerHTML(value) { html = value; const match = value.match(/<textarea[^>]*>([\s\S]*?)<\/textarea>/); form.values.rationale = match ? decode(match[1]) : ''; controls = match ? [element()] : []; }, querySelectorAll: () => controls, append(node) { comparison = node; } };
  const doc = { createElement() { const button = element(); return { ...element(), querySelector: () => button, remove() { comparison = null; } }; } };
  const detailClose = element(), detail = { ...element(), hidden: true, innerHTML: '', querySelector: () => detailClose };
  const host = { ...element(), ownerDocument: doc, prepended: [], prepend(node) { this.prepended.push(node); }, innerHTML: '', querySelector: () => detail, querySelectorAll: () => selections };
  Object.defineProperty(host, 'innerHTML', { get() { return this.html || ''; }, set(value) { this.html = value; selections = [...value.matchAll(/data-research-select="([^"]+)"/g)].map(match => ({ ...element(), dataset: { researchSelect: decode(match[1]) } })); } });
  const dialog = { ...element(), ownerDocument: doc, open: false, showModal() { this.open = true; }, close() { this.open = false; }, querySelector: selector => ({ form, '[data-fieldkg-action-body]': body, '[role="status"]': status, h2: title, '[data-fieldkg-action-close]': close })[selector] };
  const location = { href: 'http://127.0.0.1:8885/?view=fieldkg&field=f1&overview_state=preserved', origin: 'http://127.0.0.1:8885' };
  const history = { state: {}, replaceState(state, unused, url) { this.state = state; location.href = String(url); } };
  const request = fetch || (async () => fieldData());
  const work = ui.createWorkspace({ host, dialog, storage: local, location, history, request, overviewCapture() {}, returnOverview() {}, openPaper() {}, draftNamespace: namespace });
  const click = dataset => host.events.click({ target: { ...element(), dataset } });
  return { work, host, detail, detailClose, location, form, submit, body, dialog, status, close, local, click, controls: () => controls, selections: () => selections, compare: () => comparison?.querySelector().events.click() };
}
let passed = 0;
async function test(name, fn) { await fn(); passed++; process.stdout.write(`PASS ${name}\n`); }
await test('actual graph preserves identities, original terms and scoped citations', () => {
  const f = fieldData(), model = ui.graphModel(f.sources, [...f.candidates, { record: { ...f.candidates[0].record, candidate_id: 'c2' } }], f.candidate_gaps, [{ citation_id: 'foreign', citing_paper_id: 'paper', cited_paper_id: 'another-field' }]);
  assert.equal(model.nodes.filter(node => node.kind === 'candidate').length, 2);
  assert.equal(model.nodes.filter(node => node.kind === 'concept').length, 2);
  assert.equal(new Set(model.nodes.map(node => node.key)).size, model.nodes.length);
  assert.ok(model.edges.some(edge => edge.key === key('triplet', 'tr1') && edge.source === key('unit', 'u1')));
  assert.ok(!model.edges.some(edge => edge.key === key('citation', 'foreign')));
});
await test('snapshot graph uses frozen sources, evidence, references and citations', () => {
  const f = fieldData(), snapshot = { sources: f.sources, manifest: { reviewed_candidates: f.candidates.map(c => c.record), gap_references: { g1: f.candidate_gaps[0].references }, citations: [{ citation_id: 'fixed-citation', citing_paper_id: 'paper', cited_paper_id: 'paper' }] }, frozen_candidate_gaps: [f.candidate_gaps[0].record], frozen_evidence: [{ evidence_id: 'e1', statement: 'Frozen', location_json: '{"unit_id":"u1"}' }] };
  const model = ui.snapshotGraph(snapshot);
  assert.ok(model.edges.some(edge => edge.key === key('gap-reference', ['g1', 'c1'])));
  assert.ok(model.edges.some(edge => edge.key === key('citation', 'fixed-citation')));
  assert.equal(model.nodes.find(node => node.kind === 'evidence').record.location.unit_id, 'u1');
});
await test('unclassified source Intent is shown as incomplete rather than empty success', async () => {
  const f = fieldData(); f.builds[0].semantic_coverage = { complete: false, unclassified_units: [{ skeleton_id: 's3', unit_id: 'u1', raw_text: 'Exact original sentence', layer3: { communicative_intent: 'Old descriptive interpretation' } }] };
  const s = setup(async () => f); await s.work.show('fieldkg');
  assert.match(s.host.innerHTML, /来源语义未完成/); assert.match(s.host.innerHTML, /Old descriptive interpretation/);
  assert.match(s.host.innerHTML, /选择原解析版本并重新深读/); assert.match(s.host.innerHTML, /不能密封/);
});
await test('nine Build stages distinguish recorded artifacts and unknown runs', () => {
  const stages = plain(ui.buildStages(fieldData().builds[0]));
  assert.equal(stages.length, 9); assert.equal(stages.filter(stage => stage.current).length, 1);
  assert.match(stages.find(stage => stage.key === 'FORGING_FIELDKG').detail, /运行未记录/);
  assert.match(stages.find(stage => stage.key === 'DOWNLOADING').detail, /未记录/);
});
await test('actual source detail preserves raw page, versions, layers, selection and keyboard close', async () => {
  const s = setup(); await s.work.show('fieldkg'); s.work.nodeDetail(key('candidate', 'c1'));
  assert.match(s.detail.innerHTML, /Exact original sentence/); assert.match(s.detail.innerHTML, /Paper v2/); assert.match(s.detail.innerHTML, /Skeleton v3/);
  assert.match(s.detail.innerHTML, /页标记：3/); assert.match(s.detail.innerHTML, /layer4/); assert.match(s.detail.innerHTML, /未知/);
  assert.ok(s.detailClose.focused); assert.equal(new URL(s.location.href).searchParams.get('research_object'), key('candidate', 'c1'));
  s.detail.onkeydown({ key: 'Escape', preventDefault() {} }); assert.ok(s.detail.hidden); assert.ok(!new URL(s.location.href).searchParams.has('research_object'));
  assert.ok(s.selections().some(el => el.focused && el['aria-pressed'] === 'false'));
});
await test('frozen detail cannot substitute later Living source text', async () => {
  const f = fieldData(), fixed = savedSource(); f.sources[0].units[0].raw_text = 'Later Living source';
  f.selected_snapshot = { sources: [fixed], manifest: { reviewed_candidates: [f.candidates[0].record] }, frozen_candidate_gaps: [], frozen_evidence: [], version: 1, content_digest: 'fixed', digest_matches: true, members_match: true, source_records_available: true, adoptions: [], members: [] };
  const s = setup(async () => f); await s.work.show('fieldkg'); s.work.nodeDetail(key('candidate', 'c1'));
  assert.match(s.detail.innerHTML, /Exact original sentence/); assert.doesNotMatch(s.detail.innerHTML, /Later Living source/);
});
await test('late Field response cannot overwrite a newly selected Field', async () => {
  let resolve;
  const s = setup(async endpoint => endpoint.includes('/f1/') ? new Promise(r => { resolve = r; }) : { ...fieldData(), field: { field_id: 'f2', name: 'Second Field' } });
  const old = s.work.show('fieldkg'); s.location.href = s.location.href.replace('field=f1', 'field=f2'); await s.work.show('fieldkg'); resolve(fieldData()); await old;
  assert.match(s.host.innerHTML, /Second Field/); assert.doesNotMatch(s.host.innerHTML, /<h1>Selected Field/);
});
await test('failed read never displays success or mutates research', async () => {
  const s = setup(async () => { throw new Error('Missing fixed record'); }); await s.work.show('fieldkg');
  assert.match(s.host.innerHTML, /role="alert"/); assert.match(s.host.innerHTML, /Missing fixed record/); assert.doesNotMatch(s.host.innerHTML, /进入审阅/);
});
await test('source chooser read failure is visible and does not create a Build', async () => {
  let actions = 0;
  const s = setup(async (endpoint, payload) => { if (payload) actions++; if (endpoint.endsWith('/skeletons')) throw new Error('Source unavailable'); return fieldData(); });
  await s.work.show('fieldkg'); await s.click({ buildCreate: '' });
  assert.equal(actions, 0); assert.match(s.host.prepended[0].textContent, /Source unavailable/); assert.equal(s.host.prepended[0].role, 'alert');
});
await test('late source chooser cannot appear under a different Field', async () => {
  let resolve;
  const s = setup(async endpoint => endpoint.endsWith('/skeletons') ? new Promise(r => { resolve = r; }) : fieldData());
  await s.work.show('fieldkg'); const opening = s.click({ buildCreate: '' });
  s.location.href = s.location.href.replace('field=f1', 'field=f2'); await s.work.show('fieldkg'); resolve({ sources: [savedSource()] }); await opening;
  assert.equal(s.host.prepended.length, 0);
});
await test('actual confirmation retains reason and retries exactly the uncertain original decision', async () => {
  const attempts = [], f = fieldData();
  const s = setup(async (endpoint, payload) => { if (!payload) return f; attempts.push(plain(payload)); if (attempts.length === 1) throw new Error('Connection lost'); return {}; });
  await s.work.show('fieldkg'); await s.click({ reviewKey: key('candidate', 'c1'), reviewDecision: 'ACCEPTED' });
  s.form.values.rationale = 'Located source'; s.form.events.input(); s.close.events.click();
  await s.click({ reviewKey: key('candidate', 'c1'), reviewDecision: 'ACCEPTED' }); assert.equal(s.form.values.rationale, 'Located source');
  await s.form.events.submit({ preventDefault() {} }); assert.ok(s.controls().every(el => el.disabled)); s.close.events.click();
  await s.click({ reviewKey: key('candidate', 'c1'), reviewDecision: 'REJECTED' }); assert.match(s.body.innerHTML, /将核对原提交：REVIEW_CANDIDATE ACCEPTED/);
  await s.form.events.submit({ preventDefault() {} }); assert.deepEqual(attempts[0], attempts[1]); assert.equal(attempts[1].decision, 'ACCEPTED');
  assert.equal(s.local.values.size, 0); assert.equal(s.dialog.open, false);
});
await test('known conflict retains draft and demands comparison before using the new version', async () => {
  const f = fieldData(), attempts = [], s = setup(async (endpoint, payload) => { if (!payload) return f; attempts.push(plain(payload)); if (attempts.length === 1) { const e = new Error('Context changed'); e.status = 409; throw e; } return {}; });
  await s.work.show('fieldkg'); await s.click({ reviewKey: key('candidate', 'c1'), reviewDecision: 'ACCEPTED' }); s.form.values.rationale = 'My reason'; s.form.events.input();
  await s.form.events.submit({ preventDefault() {} }); assert.match(s.status.textContent, /草稿仍在/); s.close.events.click();
  f.candidates[0].context_sha256 = 'candidate-new'; await s.work.show('fieldkg'); await s.click({ reviewKey: key('candidate', 'c1'), reviewDecision: 'ACCEPTED' });
  assert.ok(s.submit.disabled); assert.equal(s.form.values.rationale, 'My reason'); await s.form.events.submit({ preventDefault() {} }); assert.equal(attempts.length, 1);
  s.compare(); assert.equal(s.submit.disabled, false); await s.form.events.submit({ preventDefault() {} }); assert.equal(attempts[1].expected_context_sha256, 'candidate-new'); assert.equal(attempts[1].rationale, 'My reason');
});
await test('changing an unsubmitted decision cannot silently submit the prior opposite decision', async () => {
  const attempts = [], s = setup(async (endpoint, payload) => { if (payload) attempts.push(plain(payload)); return fieldData(); });
  await s.work.show('fieldkg'); await s.click({ reviewKey: key('candidate', 'c1'), reviewDecision: 'ACCEPTED' }); s.form.values.rationale = 'Draft'; s.form.events.input(); s.close.events.click();
  await s.click({ reviewKey: key('candidate', 'c1'), reviewDecision: 'REJECTED' }); assert.ok(s.submit.disabled); s.compare(); await s.form.events.submit({ preventDefault() {} });
  assert.equal(attempts[0].decision, 'REJECTED');
});
await test('unavailable local storage blocks an untraceable request', async () => {
  const local = storage(); local.setItem = () => { throw new Error('Denied'); }; let calls = 0;
  const s = setup(async (endpoint, payload) => { if (payload) calls++; return fieldData(); }, local);
  await s.work.show('fieldkg'); await s.click({ buildReady: 'b1' }); await s.form.events.submit({ preventDefault() {} });
  assert.equal(calls, 0); assert.match(s.status.textContent, /无法保存提交凭据/);
});
await test('Track shows independent milestones, Projects, manuscripts and no approval controls', async () => {
  const t = { track: { track_id: 'track1', field_id: 'f1', title: 'Owned Track', revision: 2, status: 'ACTIVE', scope: 'Actual scope', research_type: 'conceptual_framework' }, field: { name: 'Selected Field' }, nodes: [], edges: [], available_snapshots: [{ snapshot_id: 's1', version: 1, status: 'SEALED', content_digest: 'fixed' }], adoptions: [], milestones: [{ milestone: 'METHOD', status: 'APPROVED' }, { milestone: 'EXPERIMENT', status: 'BLOCKED', blocker: 'Actual blocker' }], decisions: [], projects: [{ project_id: 'p1', title: 'Owned Project', status: 'ACTIVE', type_payload: { goal: 'Original goal' } }], plans: [], runs: [], evidence: [], manuscripts: [{ manuscript_id: 'ms1', track_id: 'track1', title: 'Owned manuscript', workflow_stage: 'DRAFTING', writing_status: 'UNSTARTED', needs_scientific_review: 1 }], submission_events: [] };
  const s = setup(async () => t); s.location.href = 'http://127.0.0.1:8885/?view=track&track=track1&field=f1&overview_state=preserved'; await s.work.show('track');
  assert.match(s.host.innerHTML, /Actual blocker/); assert.match(s.host.innerHTML, /Original goal/); assert.match(s.host.innerHTML, /manuscript=ms1/); assert.match(s.host.innerHTML, /DRAFTING/);
  assert.doesNotMatch(s.host.innerHTML, /current_phase|data-approve/); assert.match(s.host.innerHTML, /明确采用此版本/);
  assert.equal(new URL(s.work.researchUrl('fieldkg', 'f1', null, 's1')).searchParams.get('overview_state'), 'preserved');
});
await test('historical unit location focuses the exact source and rejects a different owner', async()=>{const s=setup();await s.work.show('fieldkg');assert.equal(s.work.locateTarget({module:'FIELDKG',field_id:'f1',object_kind:'unit',object_id:'u1'}),true);assert.equal(s.selections().find(item=>item.dataset.researchSelect===key('unit','u1')).focused,true);assert.match(s.detail.innerHTML,/Exact original sentence/);assert.equal(s.work.locateTarget({module:'FIELDKG',field_id:'other',object_kind:'unit',object_id:'u1'}),false);assert.equal(s.work.locateTarget({module:'FIELDKG',field_id:'f1',object_kind:'unit',object_id:'missing'}),false);});
await test('concept and relationship locations preserve the real case sensitive graph keys', async()=>{const s=setup();await s.work.show('fieldkg');assert.equal(s.work.locateTarget({module:'FIELDKG',field_id:'f1',object_kind:'concept',object_id:'Field term'}),true);assert.equal(s.selections().find(item=>item.dataset.researchSelect===key('term','Field term')).focused,true);assert.equal(s.work.locateTarget({module:'FIELDKG',field_id:'f1',object_kind:'relationship',object_id:key('triplet','tr1')}),true);assert.equal(s.selections().find(item=>item.dataset.researchSelect===key('triplet','tr1')).focused,true);});
await test('a frozen source cannot be highlighted in a different Living or Snapshot view', async()=>{const s=setup();await s.work.show('fieldkg');assert.equal(s.work.locateTarget({module:'FIELDKG',field_id:'f1',snapshot_id:'old-snapshot',object_kind:'unit',object_id:'u1'}),false);assert.equal(s.detail.hidden,true);});
function semanticData(){
  const f=fieldData();
  f.semantic_objects=['CONCEPT','METHOD','FINDING','REPORTED_GAP','COUNTEREVIDENCE','DEBATE','IDEA_MERGER'].map((kind,i)=>({
    object_id:'semantic-'+i,build_id:'b1',kind,statement:'Located '+kind,rationale:'Source interpretation',status:'PROPOSED',
    context_sha256:'semantic-context-'+i,conditions:['original conditions'],model_contract:{actual_model:'fixture',prompt_version:'semantic-v1'},
    references:[{unit_id:'u1',quote:'Exact original sentence',role:'SUPPORTS',qualifications:['original conditions'],
      source:{skeleton_id:'s3',paper_id:'paper',paper_version_id:'pv2'},location:{page_idx:3,seq_idx:4},original_text:'Exact original sentence'}]
  }));
  f.semantic_runs=[{run_id:'semantic-run',build_id:'b1',status:'READY',result:[],updated_at:'original-time'}];
  f.builds[0].semantic_objects=f.semantic_objects;f.builds[0].semantic_runs=f.semantic_runs;
  return f;
}
await test('all semantic types have actual graph objects and separate category lists',async()=>{
  const f=semanticData(),s=setup(async()=>f);await s.work.show('fieldkg');
  for(const label of ['Findings','Reported Gaps','Counterevidence','Debates','Idea Mergers'])assert.match(s.host.innerHTML,new RegExp(label));
  const model=ui.graphModel(f.sources,f.candidates,f.candidate_gaps,[],[],f.semantic_objects);
  assert.equal(model.nodes.filter(n=>n.kind==='semantic').length,7);
  assert.equal(model.edges.filter(e=>JSON.parse(e.key)[0]==='semantic-source').length,7);
  assert.doesNotMatch(s.host.innerHTML,/尚无独立争论或 Idea Merger/);
});
await test('semantic object source detail preserves exact quote, conditions, versions and model',async()=>{
  const s=setup(async()=>semanticData());await s.work.show('fieldkg');s.work.nodeDetail(key('semantic','semantic-2'));
  for(const text of ['Exact original sentence','original conditions','Paper v2','Skeleton v3','semantic-v1','接受此来源解释'])assert.ok(s.detail.innerHTML.includes(text));
  assert.ok(s.work.locateTarget({module:'FIELDKG',field_id:'f1',object_kind:'semantic',object_id:'semantic-2'}));
});
await test('semantic review uses its scoped endpoint and exact uncertain original request',async()=>{
  const attempts=[],f=semanticData(),s=setup(async(endpoint,payload)=>{if(!payload)return f;attempts.push({endpoint,payload:plain(payload)});if(attempts.length===1)throw Error('Lost response');return {};});
  await s.work.show('fieldkg');await s.click({semanticReview:'semantic-2',reviewDecision:'ACCEPTED'});
  s.form.values.rationale='Review exact original source';await s.form.events.submit({preventDefault(){}});
  assert.match(attempts[0].endpoint,/fieldkg-semantic-objects\/semantic-2\/review/);
  s.close.events.click();await s.click({semanticReview:'semantic-2',reviewDecision:'REJECTED'});
  await s.form.events.submit({preventDefault(){}});assert.deepEqual(attempts[0],attempts[1]);assert.equal(attempts[1].payload.decision,'ACCEPTED');
});
await test('semantic extraction confirmation retains exact Build and original request',async()=>{
  const attempts=[],f=semanticData(),s=setup(async(endpoint,payload)=>{if(!payload)return f;attempts.push({endpoint,payload:plain(payload)});return {};});
  await s.work.show('fieldkg');await s.click({semanticCreate:'b1'});await s.form.events.submit({preventDefault(){}});
  assert.equal(attempts[0].endpoint,'/api/catalog/fieldkg-semantic-runs');assert.equal(attempts[0].payload.build_id,'b1');assert.equal(attempts[0].payload.expected_context_sha256,'build-old');
});
await test('late semantic continuation does not switch a newly selected work surface',async()=>{
  let resolve;const f=semanticData(),s=setup(async(endpoint,payload)=>payload?new Promise(r=>{resolve=r;}):f);
  await s.work.show('fieldkg');const old=s.click({semanticAdvance:'semantic-run'});
  s.work.cancelLoad();s.host.innerHTML='Another current surface';resolve({});await old;assert.equal(s.host.innerHTML,'Another current surface');
});
await test('frozen semantic graph uses only its captured source interpretations',()=>{
  const f=semanticData(),snapshot={sources:f.sources,manifest:{},frozen_candidate_gaps:[],frozen_evidence:[],frozen_semantic_objects:f.semantic_objects};
  const model=ui.snapshotGraph(snapshot);assert.equal(model.nodes.find(n=>n.key===key('semantic','semantic-2')).label,'Located FINDING');
  assert.equal(model.nodes.filter(n=>n.kind==='semantic').length,7);
});
await test('Track and Project runs retain full output and original artifact links',async()=>{
  const f={field:{field_id:'f1',name:'Field'},track:{track_id:'t1',field_id:'f1',title:'Track',revision:1},nodes:[],edges:[],milestones:[],available_snapshots:[],adoptions:[],decisions:[],projects:[{project_id:'p1',title:'Project',type_payload:{}}],plans:[],evidence:[],manuscripts:[],submission_events:[],source_reviews:[],
    runs:[{run_id:'r1',project_id:'p1',operation:'experiment',status:'COMPLETED',updated_at:'2026-10-08',detail:{cwd:'workspace',stdout:'FULL-OUTPUT-'+'x'.repeat(1500),stderr:'FULL-ERROR',inputs:[{relative_path:'input',sha256:'input-sha'}],environment:{python_version:'3.13'},artifacts:[{relative_path:'result.txt',sha256:'original-sha',size:12}]}},{run_id:'r2',project_id:null,operation:'direct experiment',status:'FAILED',detail:{stdout:'DIRECT-OUTPUT',stderr:'DIRECT-ERROR'}}]};
  const s=setup(async()=>f);s.location.href='http://127.0.0.1:8885/?view=track&track=t1';await s.work.show('track');
  for(const text of ['FULL-OUTPUT-','FULL-ERROR','DIRECT-OUTPUT','DIRECT-ERROR','input-sha','original-sha','完整执行输出','Track 直属执行记录'])assert.ok(s.host.innerHTML.includes(text));
  assert.match(s.host.innerHTML,/tracks\/t1\/runs\/r1\/artifacts\/0/);
  assert.ok(s.host.innerHTML.includes('x'.repeat(1500)));
});
process.stdout.write(`${passed} controlled workspace scenarios passed\n`);
