import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const [,,base,phase,fixturePath,outPath]=process.argv;const fixture=JSON.parse(fs.readFileSync(fixturePath,'utf8')),calls=[];
const api=async(path,body)=>{const response=await fetch(base+path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const data=await response.json();calls.push({path,body,status:response.status,data});if(!response.ok){const e=Error(JSON.stringify(data));e.status=response.status;throw e;}return data;};
const script=await(await fetch(base+'/catalog-collections.js')).text();assert.equal(script,fs.readFileSync(fixture.collection_source,'utf8'));const host=vm.createContext({});vm.runInContext(script,host);
let result;
if(phase==='request'){
 const paper=await api('/api/catalog/papers/'+fixture.paper_id);const memory=new Map(),storage={getItem:k=>memory.get(k),setItem:(k,v)=>memory.set(k,v)};
 const controller=host.CatalogCollections.createDeepReadController({api,storage,makeKey:()=> 'actual-deep-read-native-v1'});controller.load(paper);controller.edit({collection_id:fixture.collection_id,parse_run_id:fixture.parse_run_id,reason:'Explicit software document: verify full four-layer extraction and actual model receipts'});
 const job=await controller.submit();assert.equal(job.job_type,'SKELETON');assert.equal(JSON.parse(job.input_json).parse_run_id,fixture.parse_run_id);assert.equal(controller.state().receipt.job_id,job.job_id);
 const input={paper_id:fixture.paper_id,parse_run_id:fixture.parse_run_id,reason:controller.state().draft.reason,idempotency_key:'actual-deep-read-native-v1'};const repeated=await api('/api/catalog/collections/'+fixture.collection_id+'/deep-read',input);assert.deepEqual(repeated,job);result={job,input};
}else{
 const paper=await api('/api/catalog/papers/'+fixture.paper_id);assert.ok(paper.assessments.some(a=>a.assessment_type==='QUICK_READ'));assert.ok(paper.assessments.some(a=>a.assessment_type==='CONTENT'));assert.ok(paper.skeletons.length>0);
 const tasks=new Set(paper.model_calls.map(c=>c.task));for(const task of ['screen','quick_read','skeleton_layer_1','skeleton_layer_2','skeleton_layer_3','skeleton_layer_4','assessment'])assert.ok(tasks.has(task),task);
 const originals=[];for(const call of paper.model_calls){assert.equal(call.status,'RETURNED');assert.ok(call.contract.actual_model);const original=await api('/api/catalog/papers/'+fixture.paper_id+'/model-calls/'+call.call_id);assert.deepEqual(original.contract,call.contract);assert.deepEqual(original.output._contract,original.contract);if(call.task!=='screen')assert.equal(original.source.parse_run_id,fixture.parse_run_id);originals.push(original);}
 const repeated=await api('/api/catalog/collections/'+fixture.collection_id+'/deep-read',fixture.request.input);assert.equal(repeated.job_id,fixture.request.job.job_id);assert.equal(repeated.status,'SUCCEEDED');
 result={paper,original_calls:originals,original_request_reused:true,job:repeated};
}
fs.writeFileSync(outPath,JSON.stringify({status:'PASS_ACTUAL_DEEP_READ_'+phase.toUpperCase(),calls,...result,browser_verified:false,scientific_approval:false},null,2),{flag:'wx'});console.log('Actual deep read '+phase+' '+calls.length+' HTTP checks passed');
