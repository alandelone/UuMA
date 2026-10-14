import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const host=vm.createContext({});vm.runInContext(fs.readFileSync('src/rstv4/catalog_collections.js','utf8'),host);
const factory=host.CatalogCollections.createDeepReadController;
const memory=()=>{const map=new Map();return {getItem:k=>map.get(k),setItem:(k,v)=>map.set(k,v)};};
const paper=id=>({paper_id:id,collections:[{collection_id:'c-'+id}],parse_runs:[{parse_run_id:'parse-'+id,status:'SUCCEEDED'}]});
const choose=(c,id)=>{c.load(paper(id));c.edit({collection_id:'c-'+id,parse_run_id:'parse-'+id,reason:'Explicit original reason'});};
{
 const storage=memory(),calls=[];let lost=true;
 const api=async(p,b)=>{calls.push([p,JSON.parse(JSON.stringify(b))]);if(lost){lost=false;throw Error('Lost response');}return {job_id:'original-job',status:'READY'};};
 const first=factory({api,storage,makeKey:()=> 'original-deep-key'});choose(first,'a');await assert.rejects(first.submit(),/Lost/);
 const second=factory({api,storage,makeKey:()=>{throw Error('New key forbidden');}});second.load(paper('a'));await second.submit();
 assert.deepEqual(calls[0],calls[1]);assert.equal(second.state().receipt.job_id,'original-job');assert.equal(second.state().request,null);
}
{
 const c=factory({api:async()=>{},storage:memory(),makeKey:()=> 'key'});choose(c,'a');choose(c,'b');c.edit({reason:'Other owner reason'});c.load(paper('a'));assert.equal(c.state().draft.reason,'Explicit original reason');
}
{
 let resolve;const storage=memory();const c=factory({api:()=>new Promise(r=>{resolve=r;}),storage,makeKey:()=> 'late-deep-key'});choose(c,'a');const waiting=c.submit();choose(c,'b');resolve({job_id:'a-old'});await waiting;assert.equal(c.state().paper.paper_id,'b');assert.equal(c.state().receipt,null);assert.equal(c.state().draft.parse_run_id,'parse-b');
}
{
 let calls=0;const c=factory({api:async()=>{calls++;},storage:{getItem:()=>null,setItem:()=>{throw Error('Blocked storage');}},makeKey:()=> 'blocked-key'});choose(c,'a');await assert.rejects(c.submit(),/保存/);assert.equal(calls,0);
}
{
 let calls=0;const c=factory({api:async()=>{calls++;},storage:memory(),makeKey:()=> 'unknown-parse-key'});choose(c,'a');c.load({...paper('a'),parse_runs:[{parse_run_id:'new-parse',status:'SUCCEEDED'}]});assert.equal(c.state().draft.parse_run_id,'parse-a');await assert.rejects(c.submit(),/解析版本/);assert.equal(calls,0);
}
{
 const storage=memory();const c=factory({api:async()=>{const e=Error('Source changed');e.status=422;throw e;},storage,makeKey:()=> 'source-changed-key'});choose(c,'a');await assert.rejects(c.submit(),/Source/);assert.equal(c.state().request,null);assert.equal(c.state().draft.reason,'Explicit original reason');
}
console.log('6 frozen deep-read draft/owner/exact-retry/source checks passed');
