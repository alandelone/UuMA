const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const ts = require('typescript');
const path = require('node:path');
function load(name) {
  const file=path.resolve('lib/'+name+'.ts');const mod=new Module(file,module);mod.filename=file;mod.paths=module.paths;
  const source=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  if(name==='studio-undo-history') mod.require=(name)=> name==='./offline-outbox' ? load('offline-outbox') : require(name);
  mod._compile(source,file);return mod.exports;
}
const {restoreUndoHistory,serializeUndoHistory}=load('studio-undo-history');
const doc={schema_version:1,manuscript_id:'ms',title:'Current Ω',abstract:'',venue:'',sections:[{id:'s',title:'S',role:'',paragraphs:[{id:'p',purpose:'Purpose',paradigm:'Custom',asset_ids:['asset'],formulas:[{id:'f',latex:'x=1',caption:'Formula'}],intents:[{id:'i',label:'Intent',thoughts:[{id:'t',text:'Exact Ω thought',citation_mode:'SELECTED',citations:[{evidence_id:'e',selected:true}]}]}]}]}],argument_relations:[{id:'edge',source_id:'p',target_id:'t',relation:'Relation Ω',condition:'Exact condition'}]};
const previous=structuredClone(doc);previous.title='Previous';const later=structuredClone(doc);later.title='Later';
let count=0;function check(name,fn){fn();count++;console.log('PASS '+name);}
check('full author snapshots survive storage round trip, including citations, assets, formula and relations',()=>{const raw=serializeUndoHistory(doc,55,[previous],[later]);const restored=restoreUndoHistory(raw,'ms',55,structuredClone(doc));assert.deepEqual(restored,{undo:[previous],redo:[later]});restored.undo[0].sections[0].paragraphs[0].intents[0].thoughts[0].text='changed';assert.equal(restoreUndoHistory(raw,'ms',55,doc).undo[0].sections[0].paragraphs[0].intents[0].thoughts[0].text,'Exact Ω thought');});
check('server key order changes do not erase a semantically equal stack',()=>{const reordered=JSON.parse(JSON.stringify(doc,(key,value)=>value && !Array.isArray(value) && typeof value==='object' ? Object.fromEntries(Object.entries(value).reverse()) : value));assert.deepEqual(restoreUndoHistory(serializeUndoHistory(doc,55,[previous],[]),'ms',55,reordered).undo,[previous]);});
check('foreign manuscript, changed revision and changed author word or array ordering are rejected',()=>{const raw=serializeUndoHistory(doc,55,[previous],[]);assert.throws(()=>restoreUndoHistory(raw,'foreign',55,doc));assert.throws(()=>restoreUndoHistory(raw,'ms',56,doc));const changed=structuredClone(doc);changed.sections[0].paragraphs[0].intents[0].thoughts[0].text+='!';assert.throws(()=>restoreUndoHistory(raw,'ms',55,changed));});
check('unreadable or malformed stacks and foreign snapshot stay unusable without mutating the saved raw',()=>{for(const raw of ['{', '{}',serializeUndoHistory(doc,55,[{...previous,manuscript_id:'foreign'}],[]),serializeUndoHistory(doc,55,[{...previous,sections:[{id:'bad'}]}],[])]){const before=raw;assert.throws(()=>restoreUndoHistory(raw,'ms',55,doc));assert.equal(raw,before);}});
check('history is bounded to the most recent 100 complete operations',()=>{const items=Array.from({length:102},(_,i)=>({...previous,title:String(i)}));const restored=restoreUndoHistory(serializeUndoHistory(doc,55,items,items),'ms',55,doc);assert.equal(restored.undo.length,100);assert.equal(restored.redo.length,100);assert.equal(restored.undo[0].title,'2');assert.equal(restored.undo[99].title,'101');});
check('undo and redo stacks can each resume after a different saved revision',()=>{const raw=serializeUndoHistory(previous,56,[],[doc]);assert.deepEqual(restoreUndoHistory(raw,'ms',56,previous),{undo:[],redo:[doc]});const redo=serializeUndoHistory(doc,57,[previous],[]);assert.deepEqual(restoreUndoHistory(redo,'ms',57,doc),{undo:[previous],redo:[]});});
console.log(`${count} durable undo storage binding and preservation cases passed; no browser used.`);
