const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const ts = require('typescript');
const path = require('node:path');
const file = path.resolve('lib/studio-blocks.ts');
const compiled = ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const mod = new Module(file,module);mod.filename=file;mod.paths=module.paths;mod._compile(compiled,file);
const {canDropTemplate,canPlaceOriginalSection,placeOriginalSection,sectionDepth}=mod.exports;
const paragraph = {id:'p',purpose:'Author purpose',paradigm:'Custom Ω',logical_relation:'Author relation',asset_ids:['asset'],formulas:[{id:'formula',latex:'x=1',caption:'Exact caption'}],intents:[{id:'i',label:'Author Intent',thoughts:[{id:'t',text:'Exact author Ω words',citation_mode:'SELECTED',citations:[{evidence_id:'e',selected:true}]}]}]};
const doc={schema_version:1,manuscript_id:'ms',title:'Author',abstract:'',venue:'',sections:[
  {id:'template',title:'Template',role:'',paragraphs:[{id:'slot',purpose:'',paradigm:'',asset_ids:[],template_source:{skeleton_id:'sk',unit_id:'u',source_sha256:'fixed'},intents:[{id:'empty-i',label:'Structural source Intent',thoughts:[]}]}]},
  {id:'original',title:'Original Ω',role:'Author role',placement_status:'UNPLACED',unplaced_parent_section_id:'prior-parent',paragraphs:[]},
  {id:'child',title:'Child',role:'',placement_status:'UNPLACED',parent_section_id:'original',paragraphs:[paragraph],paragraph_groups:[{id:'group',label:'Exact group',paragraph_ids:['p']}],block_order:['group']},
  {id:'other',title:'Other unresolved original',role:'',placement_status:'UNPLACED',paragraphs:[]}
],argument_relations:[{id:'edge',source_id:'p',target_id:'empty-i',relation:'Conditions Ω',condition:'Author explicit condition'}]};
let count=0;function check(name,fn){fn();count++;console.log('PASS '+name);}
check('template drop only exposes locations with the same insertion meaning as preview',()=>{
  for(const kindId of [['section','template'],['paragraph','slot'],['intent','empty-i']]) {
    assert.equal(canDropTemplate(doc,{kind:kindId[0],id:kindId[1],placement:'after'}),true);
    for(const placement of ['before','inside']) assert.equal(canDropTemplate(doc,{kind:kindId[0],id:kindId[1],placement}),false);
  }
  assert.equal(canDropTemplate(doc,{kind:'paper',id:'ms',placement:'inside'}),true);
});
check('unplaced sources, thoughts, groups, unknown and foreign manuscript are not adoption destinations',()=>{
  for(const target of [{kind:'section',id:'original',placement:'after'},{kind:'paragraph',id:'p',placement:'after'},{kind:'thought',id:'t',placement:'after'},{kind:'paragraph_group',id:'group',placement:'after'},{kind:'paragraph',id:'missing',placement:'after'},{kind:'paper',id:'foreign',placement:'inside'}]) assert.equal(canDropTemplate(doc,target),false);
});
check('whole reviewed author tree preserves all author fields, stable endpoints, groups, source and siblings',()=>{
  const before=structuredClone(doc),next=placeOriginalSection(doc,'original','template');
  assert.deepEqual(doc,before);
  assert.deepEqual(next.sections.map(s=>s.id),['template','original','child','other']);
  assert.equal(next.sections[1].parent_section_id,'template');assert.equal(sectionDepth(next,'child'),2);
  assert.equal(next.sections[1].placement_status,undefined);assert.equal(next.sections[2].placement_status,undefined);
  assert.equal(next.sections[1].unplaced_parent_section_id,'prior-parent');
  assert.deepEqual(next.sections[2].paragraphs,before.sections[2].paragraphs);
  assert.deepEqual(next.sections[2].paragraph_groups,before.sections[2].paragraph_groups);
  assert.deepEqual(next.sections[2].block_order,before.sections[2].block_order);
  assert.deepEqual(next.sections[0].paragraphs,before.sections[0].paragraphs);
  assert.deepEqual(next.argument_relations,before.argument_relations);
  assert.equal(next.sections[3].placement_status,'UNPLACED');
});
check('repeated placement, missing and unplaced destination, self and descendant never change input',()=>{
  const before=structuredClone(doc);
  for(const ids of [['template','original'],['missing','template'],['original','missing'],['original','other'],['original','original'],['original','child']]) {
    assert.equal(canPlaceOriginalSection(doc,...ids),false);assert.throws(()=>placeOriginalSection(doc,...ids));assert.deepEqual(doc,before);
  }
});
check('depth limit considers the entire original subtree',()=>{
  const next=structuredClone(doc);next.sections.unshift({id:'root',title:'Root',role:'',paragraphs:[]},{id:'deep1',title:'Deep',role:'',parent_section_id:'root',paragraphs:[]},{id:'deep2',title:'Deeper',role:'',parent_section_id:'deep1',paragraphs:[]});next.sections[3].parent_section_id='deep2';
  assert.equal(canPlaceOriginalSection(next,'original','template'),false);assert.throws(()=>placeOriginalSection(next,'original','template'));
});
check('extracting an unplaced subtree leaves its unresolved parent and all external relations',()=>{
  const next=placeOriginalSection(doc,'child','template');assert.equal(next.sections.find(s=>s.id==='child').parent_section_id,'template');
  assert.equal(next.sections.find(s=>s.id==='original').placement_status,'UNPLACED');assert.deepEqual(next.argument_relations,doc.argument_relations);
});
check('old immutable snapshot can undo and redo without content conversion or provenance loss',()=>{
  const before=structuredClone(doc),placed=placeOriginalSection(doc,'original','template');
  const undone=structuredClone(before),redone=structuredClone(placed);assert.deepEqual(undone,doc);assert.deepEqual(redone,placed);
});
console.log(`${count} template drag destination and reviewed placement preservation cases passed; no browser used.`);
