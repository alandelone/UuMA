import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const host=vm.createContext({});
vm.runInContext(fs.readFileSync(new URL('../src/rstv4/catalog_collections.js',import.meta.url),'utf8'),host);
const create=host.CatalogCollections.createProgressController;
const limits={max_papers:2,max_registered_pdf_bytes:null,max_active_seconds:null,max_task_attempts:null};
const progress=(revision=1)=>({revision,budget:{limits},references:[],workers:[]});
const store=()=>{const data=new Map();return {getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v)};};
const plain=value=>JSON.parse(JSON.stringify(value));let checks=0;
{
 const calls=[],storage=store();const c=create({api:async(path,body)=>{calls.push({path,body});return body?{revision:2}:progress();},storage,makeKey:()=> 'budget-request'});
 await c.load('collection');c.edit({limits:{...limits,max_papers:5},reason:'Explicit budget increase'});
 assert.equal(calls.length,1);assert.equal(calls[0].body,undefined);
 const restored=create({api:async()=>progress(),storage,makeKey:()=> 'next'});await restored.load('collection');assert.equal(restored.state().draft.limits.max_papers,5);checks++;
}
{
 let current=progress();let posts=0;const c=create({api:async(path,body)=>{if(body)posts++;return current;},storage:store(),makeKey:()=> 'budget-request'});
 await c.load('collection');c.edit({reason:'Kept draft'});current=progress(2);await c.load('collection');assert.equal(c.state().comparisonRequired,true);
 await assert.rejects(c.submit(),/对照/);assert.equal(posts,0);assert.equal(c.state().draft.reason,'Kept draft');c.compare();assert.equal(c.state().comparisonRequired,false);checks++;
}
{
 const sent=[];let first=true;const c=create({api:async(path,body)=>{if(!body)return progress();sent.push(plain(body));if(first){first=false;throw Error('Unconfirmed');}return {revision:2};},storage:store(),makeKey:()=> 'original-budget-key'});
 await c.load('collection');c.edit({reason:'Original reason'});await assert.rejects(c.submit(),/Unconfirmed/);c.edit({reason:'Different'});await c.submit();assert.deepEqual(sent[0],sent[1]);assert.equal(sent[1].reason,'Original reason');checks++;
}
{
 const settle=[];const c=create({api:()=>new Promise(resolve=>settle.push(resolve)),storage:store(),makeKey:()=> 'budget-request'});
 const first=c.load('old');const second=c.load('new');settle[1](progress(9));await second;settle[0](progress(1));assert.equal(await first,null);assert.equal(c.state().id,'new');assert.equal(c.state().progress.revision,9);checks++;
}
{
 let posts=0;const c=create({api:async(path,body)=>{if(body)posts++;return progress();},storage:{getItem:()=>null,setItem:()=>{throw Error('Quota');}},makeKey:()=> 'budget-request'});
 await c.load('collection');c.edit({reason:'Change'});await assert.rejects(c.submit(),/保存/);assert.equal(posts,0);checks++;
}
console.log(`${checks} controlled budget draft/comparison/original-request checks passed`);
