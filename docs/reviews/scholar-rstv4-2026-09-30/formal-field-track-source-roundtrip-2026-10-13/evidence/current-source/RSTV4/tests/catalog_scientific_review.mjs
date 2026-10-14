import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const host=vm.createContext({});vm.runInContext(fs.readFileSync(new URL('../src/rstv4/catalog_scientific_review.js',import.meta.url),'utf8'),host);
const create=host.CatalogScientificReview.createController;
const ctx=(hash='current',id='ms')=>({manuscript:{manuscript_id:id,revision:1},context_sha256:hash,bindings:{nodes:[],evidence:[]},reviews:[]});
const store=()=>{const data=new Map();return {getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v)};};
const plain=v=>JSON.parse(JSON.stringify(v));let checks=0;
{
 const calls=[];const c=create({api:async(path,body)=>{calls.push({path,body});return ctx();},storage:store(),makeKey:()=> 'request'});await c.load('ms');c.edit({node_ids:['new-node'],reason:'Review'});assert.equal(calls.length,1);assert.equal(calls[0].body,undefined);checks++;
}
{
 let current=ctx();const c=create({api:async()=>current,storage:store(),makeKey:()=> 'request'});await c.load('ms');c.edit({reason:'Preserved reason',node_ids:['new-node']});current=ctx('new');await c.load('ms');assert.equal(c.state().comparisonRequired,true);await assert.rejects(c.propose(),/对照/);assert.equal(c.state().draft.reason,'Preserved reason');c.compare();assert.equal(c.state().comparisonRequired,false);checks++;
}
{
 const calls=[];let first=true;const c=create({api:async(path,body)=>{if(!body)return ctx();calls.push(plain(body));if(first){first=false;throw Error('Unconfirmed');}return {review_id:'proposal'};},storage:store(),makeKey:()=> 'original-key'});await c.load('ms');c.edit({reason:'Original',node_ids:['new']});await assert.rejects(c.propose(),/Unconfirmed/);c.edit({reason:'New draft'});await assert.rejects(c.propose(),/原请求/);await c.retry();assert.deepEqual(calls[0],calls[1]);assert.equal(calls[1].reason,'Original');checks++;
}
{
 let posts=0;const c=create({api:async(path,body)=>{if(body)posts++;return ctx();},storage:store(),makeKey:()=> 'request'});await c.load('ms');await assert.rejects(c.apply('unknown'),/真实用户批准/);assert.equal(posts,0);checks++;
}
{
 let posts=0;const c=create({api:async(path,body)=>{if(body)posts++;return ctx();},storage:{getItem:()=>null,setItem:()=>{throw Error('Blocked');}},makeKey:()=> 'request'});await c.load('ms');c.edit({reason:'Review',node_ids:['new']});await assert.rejects(c.propose(),/存储/);assert.equal(posts,0);checks++;
}
{
 let settle;const storage=store();const c=create({api:async(path,body)=>body?new Promise(resolve=>settle=resolve):ctx('current',path.includes('other')?'other':'ms'),storage,makeKey:()=> 'request'});await c.load('ms');c.edit({reason:'Original',node_ids:['new']});const pending=c.propose();await c.load('other');settle({review_id:'old'});await pending;assert.equal(c.state().manuscriptId,'other');assert.equal(c.state().context.manuscript.manuscript_id,'other');assert.equal(JSON.parse(storage.getItem('scientific-review:ms')).draft.reason,'Original');assert.deepEqual(JSON.parse(storage.getItem('scientific-review:ms')).draft.node_ids,['new']);assert.equal(JSON.parse(storage.getItem('scientific-review:other')).draft.reason,'');await c.load('ms');assert.equal(c.state().draft.reason,'Original');checks++;
}
console.log(`${checks} controlled scientific binding review checks passed`);
