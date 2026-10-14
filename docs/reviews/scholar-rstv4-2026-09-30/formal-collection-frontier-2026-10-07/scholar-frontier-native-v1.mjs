import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const [,,base,phase,fixturePath,outPath]=process.argv;
const fixture=JSON.parse(fs.readFileSync(fixturePath,'utf8')),calls=[];
const api=async(path,body)=>{const res=await fetch(base+path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const data=await res.json();calls.push({path,body,status:res.status,data});if(!res.ok){const e=Error(JSON.stringify(data));e.status=res.status;throw e;}return data;};
const script=await(await fetch(base+'/catalog-collections.js')).text();assert.equal(script,fs.readFileSync(fixture.collection_source,'utf8'));
const host=vm.createContext({});vm.runInContext(script,host);
const memory=new Map(),storage={getItem:k=>memory.get(k),setItem:(k,v)=>memory.set(k,v)};
let result;
if(phase==='create'){
 const input={field_id:'f1',topic_id:'t1',track_id:null,name:'Actual budget and preserved reference software flow',scope:{topic:'Explicit software scope'},paper_ids:['existing'],dois:[],bibtex:null,queries:[],budget:{max_papers:1,max_registered_pdf_bytes:null,max_active_seconds:null,max_task_attempts:1}};
 const controller=host.CatalogCollections.createController({api,storage,requireDurableRequest:true,makeKey:()=> 'actual-frontier-create-v1'});controller.change(input);await controller.check();const created=await controller.start();result={created,input};
}else if(phase==='recover'){
 const cid=fixture.created.collection_id,path='/api/catalog/collections/'+cid;
 const before=await api(path+'/progress');assert.equal(before.status,'PAUSED');assert.equal(before.completion,'PARTIAL_BUDGET');assert.equal(before.budget.usage.task_attempts,1);assert.equal(before.references[0].resolution_status,'DEFERRED_BUDGET');assert.equal(before.references[0].raw_text,'Original reference 10.1234/frontier-native');assert.equal(before.references[0].page_number,4);assert.deepEqual(before.references[0].location,{section:'References',line:9});
 const worker=before.workers.find(w=>w.worker_id==='actual-idle-parser');assert.equal(worker.observation,'RECENT_HEARTBEAT');assert.equal(worker.state,'IDLE');assert.equal(worker.job_id,null);assert.equal(worker.process_id,fixture.process_id);
 let lose=true;const lostApi=async(p,b)=>{const data=await api(p,b);if(p.endsWith('/budget')&&lose){lose=false;throw Error('Explicit simulated lost response after actual successful HTTP');}return data;};
 const controller=host.CatalogCollections.createProgressController({api:lostApi,storage,makeKey:()=> 'actual-frontier-budget-v1'});await controller.load(cid);controller.edit({limits:{max_papers:2,max_registered_pdf_bytes:null,max_active_seconds:null,max_task_attempts:10},reason:'Explicit software fixture: resume preserved frontier'});await assert.rejects(controller.submit(),/simulated lost response/);const original=JSON.parse(JSON.stringify(controller.state().request));assert.ok(original);
 const reload=host.CatalogCollections.createProgressController({api,storage,makeKey:()=>{throw Error('Must reuse original request');}});await reload.load(cid);assert.deepEqual(JSON.parse(JSON.stringify(reload.state().request)),original);const saved=await reload.submit();assert.equal(saved.revision,before.revision+1);assert.equal(reload.state().progress.status,'PAUSED');assert.equal(reload.state().progress.budget.history.length,2);
 await assert.rejects(api(path+'/budget',{...original,reason:'Different contents under original key'}),e=>e.status===409);
 await api(path+'/resume',{expected_revision:saved.revision});const after=await api(path+'/progress');assert.equal(after.status,'ACTIVE');assert.equal(after.references[0].reference_entry_id,before.references[0].reference_entry_id);assert.equal(after.references[0].resolution_status,'RESOLVED');assert.equal(after.references[0].raw_text,before.references[0].raw_text);assert.equal(after.budget.usage.papers,2);assert.equal(after.fixed_depth_cutoff,null);assert.ok(after.frontier_jobs>0);assert.notEqual(after.completion,'CURRENT_FRONTIER_COMPLETE');await api(path+'/pause',{expected_revision:after.revision});result={before,original_budget_request:original,saved,after,exact_retry_preserved:true,adjustment_did_not_resume:true};
}else{
 const progress=await api('/api/catalog/collections/'+fixture.created.collection_id+'/progress');const worker=progress.workers.find(w=>w.worker_id==='actual-idle-parser');assert.equal(worker.observation,'STOPPED');assert.equal(progress.status,'PAUSED');result={progress};
}
fs.writeFileSync(outPath,JSON.stringify({status:'PASS_ACTUAL_FRONTIER_'+phase.toUpperCase(),calls,...result,browser_verified:false,real_model_calls:0,scientific_approval:false},null,2),{flag:'wx'});console.log(phase+' actual HTTP checks passed '+calls.length);
