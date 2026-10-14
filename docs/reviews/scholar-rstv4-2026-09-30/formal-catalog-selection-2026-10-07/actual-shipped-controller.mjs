import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const [,,base,phase,fixturePath,outPath]=process.argv;
const fixture=JSON.parse(fs.readFileSync(fixturePath,'utf8'));
const calls=[];
const api=async(path,body)=>{const response=await fetch(base+path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const data=await response.json();calls.push({path,body,status:response.status,data});if(!response.ok){const error=Error(JSON.stringify(data));error.status=response.status;throw error;}return data;};
const script=await(await fetch(base+'/catalog-collections.js')).text();assert.equal(script,fs.readFileSync(fixture.collection_source,'utf8'));
const host=vm.createContext({});vm.runInContext(script,host);
const storage=new Map(),store={getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)};
let result;
if(phase==='select'){
 const picker=host.CatalogCollections.createPaperPicker({api,storage:store});picker.setScope({field_id:'f1',topic_id:'t1',track_id:null});await picker.load('Catalog selected');assert.equal(picker.state().rows[0].paper_id,'existing');picker.toggle('existing',true);
 const input={field_id:'f1',topic_id:'t1',track_id:null,name:'Actual Catalog selection software flow',scope:{topic:'Software scope'},paper_ids:[...picker.paperIds()],dois:[],bibtex:null,queries:[]};
 const controller=host.CatalogCollections.createController({api,storage:store,requireDurableRequest:true,makeKey:()=> 'actual-catalog-selection-native'});controller.change(input);
 const preview=await controller.check();assert.equal(preview.counts.catalog_selected,1);assert.equal(preview.counts.reusable_pdfs,1);assert.equal(preview.creates_jobs,false);
 const created=await controller.start();assert.equal(created.counts.papers,1);assert.equal(created.counts.jobs,1);assert.equal(created.seeds[0].paper_id,'existing');
 const exact=await controller.start();assert.equal(exact.collection_id,created.collection_id);assert.deepEqual(exact,created);
 await assert.rejects(api('/api/catalog/collections/preview',{...input,idempotency_key:'unknown-selected-native',paper_ids:['missing']}),error=>error.status===404);
 const invalid=await fetch(base+'/api/catalog/collections/paper-options?field_id=f2&topic_id=t1');assert.equal(invalid.status,422);
 result={created,preview,input:{...input,idempotency_key:'actual-catalog-selection-native'},selected:picker.state().selected};
}else{
 const details=await api('/api/catalog/collections/'+fixture.created.collection_id);
 assert.deepEqual(details.stages.map(row=>[row.job_type,row.status]).sort(),[['LOCATE_PDF','SUCCEEDED'],['PARSE_PDF','READY'],['SCREEN','SUCCEEDED']].sort());
 const original=await api('/api/catalog/collections',fixture.input);assert.equal(original.collection_id,fixture.created.collection_id);assert.equal(original.counts.papers,1);assert.equal(original.counts.jobs,3);
 result={details,exact_original_key_reused:true,actual_collection:original};
}
fs.writeFileSync(outPath,JSON.stringify({status:'PASS_ACTUAL_EXISTING_PAPER_'+phase.toUpperCase(),calls,...result,browser_verified:false,real_model_called:false,scientific_approval:false},null,2),{flag:'wx'});
console.log('Actual existing-paper controller '+phase+' passed '+calls.length+' semantic HTTP requests.');
