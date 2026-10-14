const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const ts = require('typescript');
const path = require('node:path');
const cache = new Map();
function load(name) {
  if (cache.has(name)) return cache.get(name);
  const file = path.resolve('lib', name + '.ts');
  const compiled = ts.transpileModule(fs.readFileSync(file, 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const mod = new Module(file, module); mod.filename = file; mod.paths = module.paths;
  mod.require = request => request === './studio-blocks' ? load('studio-blocks') : Module.prototype.require.call(mod, request);
  mod._compile(compiled, file); cache.set(name, mod.exports); return mod.exports;
}
const { correspondenceReview, mapAuthorIntent, unmapAuthorIntent, displayedThoughts, correspondenceOwners } = load('studio-correspondence');
const { reconcileStructure } = load('studio-blocks');
const source = {skeleton_id:'sk',source_sha256:'fixed',unit_id:'u',source_path:['Source Ω','Repeated'],page_number:3};
const author = n => ({id:'ap'+n,purpose:'Original purpose',paradigm:'Original Ω',logical_relation:'Author relation',asset_ids:['asset'],formulas:[{id:'f'+n,latex:'x='+n,caption:'Exact formula'}],intents:[{id:'ai'+n,label:'Original Intent',thoughts:[{id:'at'+n,text:'Original Ω '+n,citation_mode:'SELECTED',citations:[{evidence_id:'e',selected:true}]}]}]});
const slot = n => ({id:'tp'+n,purpose:'Source purpose',paradigm:'Source',asset_ids:[],intents:[{id:'ti'+n,label:'Repeated Intent',template_source:structuredClone(source),thoughts:[]}]});
const doc = {schema_version:1,manuscript_id:'ms',title:'Author',abstract:'',venue:'',sections:[
  {id:'target',title:'Root',role:'Source',paragraphs:[slot(1)]},
  {id:'child',title:'Repeated',role:'Source',parent_section_id:'target',paragraphs:[slot(2)]},
  {id:'original',title:'Author Ω',role:'Author',placement_status:'UNPLACED',paragraphs:[author(1),author(2)],paragraph_groups:[{id:'group',label:'Exact group',paragraph_ids:['ap1','ap2']}],block_order:['group']}
],argument_relations:[{id:'edge',source_id:'ap1',target_id:'at2',relation:'Comparison',condition:'Exact Ω condition'}]};
let count = 0; function check(name, fn) { fn(); count++; console.log('PASS ' + name); }
const map = (raw, a='ai1', t='ti2', context=true) => mapAuthorIntent(raw,a,t,context,correspondenceReview(raw,a,t,context));
check('arbitrary nested same-label target retains canonical author data and fixed source', () => {
  const before=structuredClone(doc), next=map(doc); assert.deepEqual(doc,before);
  assert.deepEqual(next.sections[2],before.sections[2]); assert.deepEqual(next.argument_relations,before.argument_relations);
  assert.deepEqual(next.sections[0],before.sections[0]); assert.deepEqual(next.sections[1].paragraphs[0].intents[0].template_source,source);
  assert.deepEqual(next.sections[1].paragraphs[0].intents[0].author_intent_ids,['ai1']);
  assert.deepEqual(next.sections[1].paragraphs[0].author_context_paragraph_ids,['ap1']);
  assert.deepEqual(displayedThoughts(next,next.sections[1].paragraphs[0].intents[0])[0].thought,before.sections[2].paragraphs[0].intents[0].thoughts[0]);
});
check('all-original context choices and distinct Intent references remain independent', () => {
  const next=map(map(doc),'ai2','ti1',true); assert.equal(correspondenceOwners(next).authors.size,2); assert.equal(correspondenceOwners(next).contexts.size,2);
  assert.deepEqual(next.sections[2],doc.sections[2]); assert.deepEqual(next.sections[0].paragraphs[0].author_context_paragraph_ids,['ap2']);
});
check('leaving formula and asset placement pending does not invent a target', () => {
  const next=map(doc,'ai1','ti1',false); assert.equal(next.sections[0].paragraphs[0].author_context_paragraph_ids,undefined);
});
check('legacy flat fixed paragraph source is inherited without rewriting the slot', () => {
  const legacy=structuredClone(doc); legacy.sections[1].paragraphs[0].template_source=legacy.sections[1].paragraphs[0].intents[0].template_source; delete legacy.sections[1].paragraphs[0].intents[0].template_source;
  const next=map(legacy); assert.equal(next.sections[1].paragraphs[0].intents[0].template_source,undefined); assert.deepEqual(next.sections[2],doc.sections[2]);
});
check('every reviewed source, target, parent, group and edge change invalidates confirmation', () => {
  const review=correspondenceReview(doc,'ai1','ti2',true);
  for (const change of [d=>d.sections[2].paragraphs[0].intents[0].thoughts[0].text+='change', d=>d.sections[1].paragraphs[0].intents[0].template_source.source_sha256='new', d=>d.sections[0].title='changed parent', d=>d.sections[2].paragraph_groups[0].label='changed group', d=>d.argument_relations[0].condition='changed']) {
    const raw=structuredClone(doc); change(raw); const before=structuredClone(raw); assert.throws(()=>mapAuthorIntent(raw,'ai1','ti2',true,review)); assert.deepEqual(raw,before);
  }
});
check('repeated/foreign/unplaced/self destinations fail without writes', () => {
  assert.throws(()=>map(map(doc))); for (const ids of [['foreign','ti1'],['ai1','foreign'],['ai1','ai2'],['ai1','ai1']]) assert.throws(()=>map(doc,...ids));
  assert.deepEqual(doc.sections[2].paragraphs[0].intents[0].thoughts[0].id,'at1');
});
check('explicitly cancelling and undo/redo preserve exact documents', () => {
  const next=map(doc); assert.deepEqual(unmapAuthorIntent(next,'ai1'),doc);
  assert.deepEqual(structuredClone(doc),doc); assert.deepEqual(structuredClone(next),next);
});
check('deleting a target releases its mapping but never deletes original author content', () => {
  const next=map(doc); next.sections.splice(1,1); reconcileStructure(next); assert.deepEqual(next.sections[1],doc.sections[2]); assert.equal(correspondenceOwners(next).authors.size,0);
});
check('template replacement releases references to canonical original bank', () => {
  const next=map(doc); next.sections[0].placement_status='UNPLACED'; next.sections[1].placement_status='UNPLACED'; reconcileStructure(next);
  assert.equal(correspondenceOwners(next).authors.size,0); assert.deepEqual(next.sections[2],doc.sections[2]);
});
console.log(`${count} author correspondence contracts passed; no browser or real model used.`);
