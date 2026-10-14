import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const f=JSON.parse(fs.readFileSync(process.argv[2],'utf8')),trace=[];
async function call(path,body,status=200){const response=await fetch(f.base+path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const text=await response.text();assert.equal(response.status,status,text.slice(0,1200));trace.push({path,status:response.status});return JSON.parse(text);}
const script=await fetch(f.base+'/catalog-research-workspaces.js').then(r=>r.text());
assert.equal(script,fs.readFileSync(f.source_dir+'/catalog_research_workspaces.js','utf8'));
const scope=()=>call(`/api/catalog/fields/${f.field_id}/workspace`);
let data=await scope(),build=data.builds.find(b=>b.build_id===f.build_id);
const body={request_id:'actual-semantic-http-original',field_id:f.field_id,build_id:f.build_id,expected_context_sha256:build.context_sha256,confirmed:true};
const run=await call('/api/catalog/fieldkg-semantic-runs',body,201);
assert.deepEqual(await call('/api/catalog/fieldkg-semantic-runs',body,201),run);
const result=await call(`/api/catalog/fields/${f.field_id}/semantic-runs/${run.run_id}/advance`,{});
assert.equal(result.status,'COMPLETED');data=await scope();assert.equal(data.semantic_objects.length,7);
const context={URL,Intl};vm.runInNewContext(script,context);
const model=context.RSTV4ResearchWorkspaces.graphModel(data.sources,data.candidates,data.candidate_gaps,data.citations,data.evidence,data.semantic_objects);
assert.equal(model.nodes.filter(n=>n.kind==='semantic').length,7);
for(const obj of data.semantic_objects){
  const review={request_id:'actual-review-'+obj.object_id,field_id:f.field_id,expected_context_sha256:obj.context_sha256,decision:'ACCEPTED',rationale:'Software HTTP control and original quote review only',confirmed:true};
  const saved=await call(`/api/catalog/fieldkg-semantic-objects/${obj.object_id}/review`,review);
  assert.equal(saved.scientific_approval,false);assert.deepEqual(await call(`/api/catalog/fieldkg-semantic-objects/${obj.object_id}/review`,review),saved);
}
data=await scope();
for(const candidate of data.candidates){await call('/api/catalog/fieldkg-actions',{operation:'REVIEW_CANDIDATE',field_id:f.field_id,object_id:candidate.record.candidate_id,request_id:'existing-review-'+candidate.record.candidate_id,expected_context_sha256:candidate.context_sha256,decision:'ACCEPTED',rationale:'Retain original source',confirmed:true});}
data=await scope();
for(const gap of data.candidate_gaps){await call('/api/catalog/fieldkg-actions',{operation:'REVIEW_GAP',field_id:f.field_id,object_id:gap.record.candidate_gap_id,request_id:'existing-review-'+gap.record.candidate_gap_id,expected_context_sha256:gap.context_sha256,decision:'ACCEPTED',rationale:'Candidate only',confirmed:true});}
data=await scope();build=data.builds.find(b=>b.build_id===f.build_id);
const ready=await call('/api/catalog/fieldkg-actions',{operation:'READY_BUILD',field_id:f.field_id,build_id:f.build_id,request_id:'semantic-http-ready',expected_context_sha256:build.context_sha256,confirmed:true});
const sealed=await call('/api/catalog/fieldkg-actions',{operation:'SEAL_SNAPSHOT',field_id:f.field_id,build_id:f.build_id,request_id:'semantic-http-seal',expected_context_sha256:ready.build.context_sha256,confirmed:true});
const fixed=await call(`/api/catalog/fields/${f.field_id}/workspace?snapshot=${sealed.object_id}`);
assert.equal(fixed.selected_snapshot.members_match,true);assert.equal(fixed.selected_snapshot.frozen_semantic_objects.length,7);
const obj=fixed.selected_snapshot.frozen_semantic_objects.find(o=>o.kind==='DEBATE');assert.equal(new Set(obj.references.map(ref=>ref.source.paper_id)).size,2);
const target={module:'FIELDKG',field_id:f.field_id,object_kind:'semantic',object_id:obj.object_id,snapshot_id:sealed.object_id};
const quoted=await call('/api/research/discussion/context',target);assert.ok(quoted.object_text.includes(obj.references[0].quote));
const relation=await call('/api/research/discussion/context',{...target,object_kind:'relationship',object_id:JSON.stringify(['semantic-source',obj.object_id+'|1'])});assert.equal(relation.object_text,obj.references[1].quote);
await call('/api/research/discussion/context',{...target,field_id:f.other_field_id},404);
fs.writeFileSync(process.argv[3],JSON.stringify({status:'PASS_ACTUAL_HTTP_SEMANTIC_LIFECYCLE',requests:trace,actual_http_requests:trace.length,semantic_kinds:data.semantic_objects.map(o=>o.kind),snapshot_id:sealed.object_id,model_is_explicit_software_fixture:true,scientific_approval:false,browser_verified:false},null,2),{flag:'wx'});
process.stdout.write(`PASS ${trace.length} actual HTTP semantic creation/review/freeze/Chat checks; model fixture only\n`);
