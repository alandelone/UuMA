import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const [,,base,phase,fixturePath,receiptPath]=process.argv;
const fixture=JSON.parse(fs.readFileSync(fixturePath,'utf8'));
const requests=[];
const api=async(path,body)=>{const response=await fetch(base+path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const value=await response.json();requests.push({path,body,status:response.status,response:value});if(!response.ok){const error=Error(JSON.stringify(value));error.status=response.status;throw error;}return value;};
const response=await fetch(base+'/catalog-scientific-review.js');assert.equal(response.status,200);
const source=await response.text();assert.equal(source,fs.readFileSync(fixture.controller_source,'utf8'));
const host=vm.createContext({});vm.runInContext(source,host);
const map=new Map();const controller=host.CatalogScientificReview.createController({api,storage:{getItem:k=>map.get(k),setItem:(k,v)=>map.set(k,v)},makeKey:()=> 'actual-http-scientific-binding-fixture'});
await controller.load('ms');
let result;
if(phase==='propose'){
 assert.equal(controller.state().context.manuscript.needs_scientific_review,1);
 const section=controller.state().context.author_structure.sections[0].id;
 controller.edit({node_ids:['untouched'],evidence_ids:[],section_map:{[section]:['untouched']},reason:'Explicit isolated software review: replace the complete current binding set'});
 const original=controller.state().context.bindings;
 const proposal=await controller.propose();assert.equal(proposal.status,'PROPOSED');assert.equal(proposal.grant_available,false);
 assert.deepEqual(JSON.parse(JSON.stringify(controller.state().context.bindings)),JSON.parse(JSON.stringify(original)));
 await assert.rejects(controller.apply(proposal.review_id),/真实用户批准/);
 await assert.rejects(api('/api/catalog/manuscripts/ms/scientific-review/'+proposal.review_id+'/apply',{}),error=>error.status===403);
 result={proposal,original_bindings:original};
}else{
 const proposal=controller.state().context.reviews.find(row=>row.review_id===fixture.proposal.review_id);
 assert.equal(proposal.grant_available,true);
 const before=await api('/studio/api/manuscripts/ms/workspace');
 const applied=await controller.apply(proposal.review_id);assert.equal(applied.status,'APPLIED');
 const after=await api('/studio/api/manuscripts/ms/workspace');
 assert.equal(after.manuscript.needs_scientific_review,0);assert.equal(after.generated_is_stale,true);
 assert.equal(after.active_generated_version_id,'old-version');assert.deepEqual(after.document,before.document);assert.equal(after.document_revision,before.document_revision);
 assert.deepEqual(applied.event.before.bindings,fixture.original_bindings);
 const retry=await api('/api/catalog/manuscripts/ms/scientific-review/'+proposal.review_id+'/apply',{});assert.deepEqual(retry,applied);
 const current=controller.state().context.bindings;assert.deepEqual(current.nodes.map(row=>row.node_id),['untouched']);assert.deepEqual(current.evidence,[]);
 result={applied,current_bindings:current,before,after,exact_retry:true};
}
fs.writeFileSync(receiptPath,JSON.stringify({status:'PASS_ACTUAL_SHIPPED_SCIENTIFIC_CONTROLLER_'+phase.toUpperCase(),requests,...result,browser_verified:false,actual_scientific_approval:false,simulated_trusted_boundary:true},null,2),{flag:'wx'});
console.log('Actual shipped controller '+phase+' verified '+requests.length+' HTTP requests.');
