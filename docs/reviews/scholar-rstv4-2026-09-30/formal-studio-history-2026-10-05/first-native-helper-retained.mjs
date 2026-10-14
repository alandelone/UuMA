import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { createRequire } from 'node:module';

const repo=process.cwd(), frontend=path.resolve(repo,'../writing-studio');
const require=createRequire(path.join(frontend,'package.json')),ts=require('typescript');
vm.runInThisContext(fs.readFileSync(path.resolve(repo,'../RSTV4/src/rstv4/catalog_research_chat.js'),'utf8'));
const exported={exports:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(frontend,'lib/studio-discussion-history.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,exported);
const {legacySelection,historyFilter,matchesHistory}=exported.exports;
const native=JSON.parse(fs.readFileSync(path.join(repo,'.tmp/scholar-studio-shared-native-v2.json'),'utf8'));
const manuscripts=[...Object.keys(native.old_workspace_sha256),native.manuscript_id],responses=[];
async function api(endpoint,body) {
  const response=await fetch('http://127.0.0.1:8874/api'+endpoint,{...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
  const value=await response.json(); assert.equal(response.status,200,JSON.stringify(value));
  responses.push({method:body?'POST':'GET',endpoint});return value;
}
const verified=[],legacy=[];
for(const manuscript of manuscripts) {
  const endpoint='/manuscripts/'+manuscript+'/chat';
  const all=await api(endpoint+'?limit=200');
  let page=await api(endpoint+'?limit=2'),collected=[];
  while(page.length) {
    collected=[...page,...collected];const cursor=page[0];
    page=await api(endpoint+'?'+new URLSearchParams({limit:'2',before:cursor.created_at,before_message_id:cursor.message_id}));
  }
  assert.deepEqual(collected,all);
  for(const message of all) {
    const original=await api(endpoint+'/'+message.message_id+'/context');
    const selected=legacySelection(original,manuscript);
    assert.equal(selected.type,message.anchor_type);assert.equal(selected.id,message.anchor_id||null);
    assert.equal(selected.anchorRevision,message.anchor_revision);
    assert.equal(selected.quote.text,original.quote.text);
    assert.equal(selected.quote.annotation,original.quote.annotation);
    const filter=historyFilter(selected,message.anchor_revision);
    const exact=await api(endpoint+'?'+new URLSearchParams({limit:'200',...(selected.id?{anchor_id:selected.id}:{}),...Object.fromEntries(Object.entries(filter).map(([k,v])=>[k,String(v)]))}));
    assert.ok(exact.some(row=>row.message_id===message.message_id));
    assert.ok(exact.every(row=>matchesHistory(row,selected,message.anchor_revision)));
    const target={module:'STUDIO',manuscript_id:manuscript,object_kind:selected.type,object_id:selected.id||manuscript,document_revision:selected.anchorRevision,...(selected.quote.generated_version_id?{generated_version_id:selected.quote.generated_version_id}:{})};
    const controller=globalThis.RSTV4ResearchChat.createController({request:async(route,body)=>{assert.ok(!route.endsWith('/messages')&&!route.endsWith('/annotations'));return api(route.replace(/^\/api/,''),body);},storage:{getItem:()=>null,setItem:()=>{}},namespace:'native-readonly-'+message.message_id,uuid:()=>{throw new Error('No new request permitted');}});
    await controller.choose(target,selected.quote.text?{text:selected.quote.text,start:selected.quote.start,end:selected.quote.end,offset_unit:selected.quote.offset_unit}:null);
    const current=controller.snapshot();assert.ok(current.bound,current.status);
    assert.equal(current.bound.context.object_text,original.quote.object_text);
    assert.equal(current.parent,null);
    controller.edit('content','Unsent native contract check; no submission');
    controller.viewHistory({...target,object_kind:'paper',object_id:manuscript},false);
    assert.equal(controller.snapshot().content,'Unsent native contract check; no submission');
    assert.deepEqual(controller.snapshot().bound.context.target,target);
    controller.leave();
    const result={manuscript_id:manuscript,message_id:message.message_id,shared:!!message.quoted._research_discussion,anchor_type:message.anchor_type,anchor_revision:message.anchor_revision,generated_version_id:selected.quote.generated_version_id||null};
    verified.push(result);if(!result.shared)legacy.push(result);
  }
}
assert.ok(legacy.length>0,'Existing independent Studio history must actually be exercised.');
assert.equal(responses.filter(row=>row.endpoint.endsWith('/messages')||row.endpoint.endsWith('/annotations')).length,0);
const result={status:'PASS_REAL_STUDIO_HISTORY_FILTER_CURSOR_AND_LEGACY_BINDING',browser_verified:false,new_model_calls:0,manuscripts_checked:manuscripts.length,messages_checked:verified.length,independent_legacy_messages_checked:legacy.length,verified,responses};
fs.writeFileSync(path.join(repo,'.tmp/scholar-studio-history-native-view-v1.json'),JSON.stringify(result,null,2),{flag:'wx'});
console.log(JSON.stringify({...result,responses:responses.length,verified:undefined}));
