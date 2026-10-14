import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const host=vm.createContext({});
vm.runInContext(fs.readFileSync(new URL('../src/rstv4/catalog_review_workflow.js',import.meta.url),'utf8'),host);
const create=host.CatalogReviewWorkflow.createController;
const c=(id='file',sha='one')=>({case_id:id,context_sha256:sha,kind:'PDF_IDENTITY',file:{file_version_id:id,sha256:'source'},allowed_actions:['APPROVE_IDENTITY'],history:[]});
const store=()=>{const map=new Map();return {getItem:k=>map.get(k),setItem:(k,v)=>map.set(k,v)};};
const plain=value=>JSON.parse(JSON.stringify(value));
let checks=0;
{
 const calls=[];const controller=create({api:async(path,body)=>{calls.push({path,body});return c();},storage:store(),makeKey:()=> 'request-key'});
 await controller.load('file');controller.setReason('Source reviewed');
 assert.equal(calls.length,1);assert.equal(calls[0].body,undefined);checks++;
}
{
 let current=c();const controller=create({api:async()=>current,storage:store(),makeKey:()=> 'request-key'});
 await controller.load('file');controller.setReason('Original reason');current=c('file','new');await controller.load('file');
 assert.equal(controller.state().comparisonRequired,true);assert.equal(controller.state().draft.reason,'Original reason');
 await assert.rejects(controller.submit('APPROVE_IDENTITY'),/先对照/);controller.compare();assert.equal(controller.state().comparisonRequired,false);checks++;
}
{
 const calls=[];let first=true;const controller=create({api:async(path,body)=>{if(!body)return c();calls.push(plain(body));if(first){first=false;throw Error('Unknown result');}return {result:{status:'APPROVED_IDENTITY'}};},storage:store(),makeKey:()=> 'uncertain-key'});
 await controller.load('file');controller.setReason('Explicit review');await assert.rejects(controller.submit('APPROVE_IDENTITY'),/Unknown/);
 controller.setReason('New unsubmitted reason');await assert.rejects(controller.submit('APPROVE_IDENTITY'),/原请求/);
 await controller.retry();assert.deepEqual(calls[0],calls[1]);assert.equal(calls[1].reason,'Explicit review');checks++;
}
{
 let reads=0;const controller=create({api:async(path,body)=>{if(!body)return c('file',++reads===1?'old':'new');const e=Error('Conflict');e.status=409;throw e;},storage:store(),makeKey:()=> 'conflict-key'});
 await controller.load('file');controller.setReason('Reason retained');await assert.rejects(controller.submit('APPROVE_IDENTITY'),/Conflict/);
 assert.equal(controller.state().request,null);assert.equal(controller.state().comparisonRequired,true);assert.equal(controller.state().draft.reason,'Reason retained');checks++;
}
{
 let settle;const controller=create({api:async(path,body)=>{if(!body)return c(path.includes('other')?'other':'file');return new Promise(resolve=>settle=resolve);},storage:store(),makeKey:()=> 'late-key'});
 await controller.load('file');controller.setReason('First');const pending=controller.submit('APPROVE_IDENTITY');await controller.load('other');settle({result:{status:'APPROVED_IDENTITY'}});await pending;
 assert.equal(controller.state().caseId,'other');assert.equal(controller.state().context.case_id,'other');checks++;
}
{
 let posts=0;const controller=create({api:async(path,body)=>{if(body)posts++;return c();},storage:{getItem:()=>null,setItem:()=>{throw Error('Unavailable');}},makeKey:()=> 'blocked-key'});
 await controller.load('file');controller.setReason('Review');await assert.rejects(controller.submit('APPROVE_IDENTITY'),/无法保存/);assert.equal(posts,0);checks++;
}
{
 const storage=store();let posts=0;const setup=()=>create({api:async(path,body)=>{if(body){posts++;throw Error('Unconfirmed');}return c();},storage,makeKey:()=> 'reload-key'});
 const first=setup();await first.load('file');first.setReason('Saved review');await assert.rejects(first.submit('APPROVE_IDENTITY'),/Unconfirmed/);
 const reopened=setup();await reopened.load('file');assert.equal(reopened.state().draft.reason,'Saved review');assert.equal(reopened.state().request.body.request_id,'reload-key');assert.equal(posts,1);checks++;
}
{
 const calls=[];const controller=create({api:async(path,body)=>{if(body)calls.push(plain(body));return {...c(),allowed_actions:['RECHECK_PARSE']};},storage:store(),makeKey:()=> 'reference-key'});
 await controller.load('file');controller.setReason('Original reference correction');controller.addSelection({page_number:2,word_start:3,word_end:8,text:'Local preview text, never server authority'});
 await controller.submit('RECHECK_PARSE');assert.deepEqual(calls[0].reference_selections,[{page_number:2,word_start:3,word_end:8}]);checks++;
}
console.log(`${checks} controlled explicit review workflow checks passed`);
