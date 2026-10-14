import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const repo=new URL('../',import.meta.url);
const out=new URL('.tmp/scholar-collection-controller-native-v2.json',repo);
assert.equal(fs.existsSync(out),false);
const fixture=JSON.parse(fs.readFileSync(new URL('.tmp/scholar-collection-native-v2.json',repo),'utf8'));
assert.equal(fixture.status,'PASS_REAL_HTTP_COLLECTION_SOFTWARE_WORKFLOW');
const source=await (await fetch('http://127.0.0.1:8886/catalog-collections.js')).text();
assert.equal(source,fs.readFileSync(new URL('../RSTV4/src/rstv4/catalog_collections.js',repo),'utf8'));
const context=vm.createContext({});vm.runInContext(source,context);
const responses=[],states=[],storage=new Map(),started=[];
const api=async(path,body)=>{
  assert.ok(path.startsWith('/api/catalog/collections'));
  const response=await fetch('http://127.0.0.1:8886'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const result=await response.json();responses.push({path,status:response.status,body:result});
  assert.ok(response.ok,JSON.stringify(result));return result;
};
const controller=context.CatalogCollections.createController({api,makeKey:()=> 'collection-actual-controller-native-v2',
  requireDurableRequest:true,storage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
  onState:s=>states.push({pending:s.pending,key:s.key,message:s.message}),onStarted:c=>started.push(c.collection_id)});
controller.change({field_id:fixture.field_id,topic_id:fixture.topic_id,track_id:fixture.track_id,
  name:'实际控制器 · 软件采集',scope:{purpose:'software fixture only'},dois:[],bibtex:null,
  queries:['actual software fixture query one','actual software fixture query two','actual software fixture query one']});
const preview=await controller.check();assert.equal(preview.creates_jobs,false);assert.equal(preview.counts.queries,2);
const first=await controller.start();assert.equal(first.counts.jobs,2);assert.equal(started[0],first.collection_id);
const repeated=await controller.start();assert.deepEqual(repeated,first);
assert.equal(responses[1].body.collection_id,responses[2].body.collection_id);
await api(`/api/catalog/collections/${first.collection_id}/pause`,{expected_revision:first.revision});
const proof={status:'PASS_ACTUAL_SHIPPED_COLLECTION_CONTROLLER_WITH_REAL_HTTP',browser_verified:false,
  root:fixture.root,collection_id:first.collection_id,jobs:2,creates_models:false,network_providers_executed:false,
  exact_repeated_receipt:true,started:started,states:states,responses:responses,final_collection_paused:true};
fs.writeFileSync(out,JSON.stringify(proof,null,2),{flag:'wx'});
console.log('Actual shipped Collection controller preview/start/exact retry/pause passed against isolated HTTP.');
