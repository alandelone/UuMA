import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const context=vm.createContext({});
vm.runInContext(fs.readFileSync(new URL('../src/rstv4/catalog_collections.js',import.meta.url),'utf8'),context);
const createController=context.CatalogCollections.createController;
const input={field_id:'f1',topic_id:'t1',track_id:null,name:'Collection',scope:{},dois:['10.1234/a'],bibtex:null,queries:[]};
const result={collection_id:'actual-collection',counts:{jobs:1}};
const preview={counts:{catalog_papers:1,reusable_pdfs:1,needs_review:0},creates_jobs:false};
let checks=0;
{
  const calls=[],events=[],storage=new Map();let keys=0;
  const store={getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)};
  const create=()=>createController({api:async(url,body)=>{calls.push({url,body});return url.endsWith('preview')?preview:result;},makeKey:()=>`key-${++keys}`,storage:store,onState:s=>events.push(s)});
  const controller=create();controller.change(input);await controller.check();
  assert.equal(calls.length,1);assert.equal(calls[0].url,'/api/catalog/collections/preview');
  assert.equal(controller.state().preview.creates_jobs,false);checks++;
  controller.change(input);const key=controller.state().key;
  const restored=create();restored.change(input);assert.equal(restored.state().key,key);checks++;
  restored.change({...input,topic_id:'t2'});assert.notEqual(restored.state().key,key);checks++;
}
{
  let settle;const events=[],calls=[];
  const controller=createController({api:(url,body)=>{calls.push({url,body});return new Promise(resolve=>settle=resolve);},makeKey:()=> 'pending-key',onState:s=>events.push(s)});
  controller.change(input);const pending=controller.start();
  assert.equal(await controller.start(),null);controller.change({...input,topic_id:'other'});
  assert.equal(controller.state().input.topic_id,'t1');assert.equal(calls.length,1);
  settle(result);await pending;assert.equal(controller.state().pending,false);checks++;
}
{
  let settle;const controller=createController({api:()=>new Promise(resolve=>settle=resolve),makeKey:()=> 'preview-key'});
  controller.change(input);const pending=controller.check();controller.change({...input,queries:['new query']});
  settle(preview);assert.equal(await pending,null);assert.equal(controller.state().preview,null);checks++;
}
{
  const calls=[],started=[];let first=true;
  const controller=createController({api:async(url,body)=>{calls.push({url,body});if(first){first=false;throw Error('Lost response');}return result;},makeKey:()=> 'fixed-key',onStarted:collection=>started.push(collection)});
  controller.change(input);await assert.rejects(controller.start(),/Lost response/);
  await controller.start();assert.deepEqual(calls[0].body,calls[1].body);
  assert.equal(started[0].collection_id,'actual-collection');assert.equal(controller.state().pending,false);checks++;
}
{
  const messages=[];const controller=createController({api:async()=>result,makeKey:()=> 'render-key',onStarted:()=>{throw Error('Render failure');},onState:s=>messages.push(s.message)});
  controller.change(input);assert.equal((await controller.start()).collection_id,'actual-collection');
  assert.ok(messages.some(m=>m?.includes('采集已创建')));assert.equal(controller.state().created.collection_id,'actual-collection');checks++;
}
{
  let calls=0;const controller=createController({api:async()=>{calls++;return result;},makeKey:()=> 'blocked-key',requireDurableRequest:true,storage:{getItem:()=>null,setItem:()=>{throw Error('Unavailable');}}});
  controller.change(input);await assert.rejects(controller.start(),/无法保存/);assert.equal(calls,0);checks++;
}
{
  const values=new Map();let keys=0;
  const store={getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
  const controller=createController({api:async()=>result,makeKey:()=> `intent-${++keys}`,storage:store,requireDurableRequest:true});
  controller.change(input);await controller.start();const original=controller.state().key;
  controller.begin();controller.change(input);assert.notEqual(controller.state().key,original);checks++;
}
console.log(`${checks} controlled Collection request checks passed`);
