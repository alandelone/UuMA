// Actual canonical controller and original HTTP records; no browser or new model call.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
vm.runInThisContext(fs.readFileSync(path.resolve(repo, '../RSTV4/src/rstv4/catalog_research_chat.js'), 'utf8'));
const core = globalThis.RSTV4ResearchChat;
const prior = JSON.parse(fs.readFileSync(path.join(repo, '.tmp/scholar-studio-shared-final-v1.json'), 'utf8'));
const output = path.join(repo, '.tmp/scholar-studio-history-controller-v1.json');
assert.equal(fs.existsSync(output), false);
const routes = [], requests = [];
async function request(route, body) {
  const url = route.replace('/api/catalog/discussion', 'http://127.0.0.1:8874/api/research/discussion');
  requests.push({route, method: body === undefined ? 'GET' : 'POST'});
  const response = await fetch(url, body === undefined ? undefined : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const value = await response.json();
  if (!response.ok) throw Object.assign(new Error(value.detail || 'Unavailable'), {status: response.status});
  return value;
}
function make(onLocate) {
  const saved = new Map();
  return core.createController({request,storage:{getItem:key=>saved.get(key)||null,setItem:(key,value)=>saved.set(key,value)},namespace:'readonly-native-navigation',uuid:()=>{throw new Error('This verification must not submit a new request.');},onLocate});
}
const apps = {catalogBase:'http://127.0.0.1:8885/',studioBase:'http://127.0.0.1:3000/'};
for(const receipt of prior.responses.filter(row=>row.method==='GET'&&row.path.startsWith('/api/research/discussion/requests/')).map(row=>row.body)){
  const source=receipt.job.input.source, message=receipt.messages.at(-1);
  let located;
  const controller=make(async reference=>{located=reference;});
  await controller.choose(source.context.target);
  controller.edit('content','保留这段未发送的软件验收草稿。');
  await controller.locateSource(message.message_id,0,source.context.scope_key);
  assert.deepEqual(located.source.context,source.context);
  assert.deepEqual(located.source.quote,message.quote);
  assert.equal(controller.snapshot().content,'保留这段未发送的软件验收草稿。');
  const url=core.sourceDestination(located.source.context,apps,{...located,return_url:apps.studioBase+'?manuscript=manuscript_0dd6fc921b534d44b01735629157f761&view=structure'});
  const link=core.sourceReference(new URL(url).search);
  assert.equal(link.message_id,message.message_id);
  assert.equal(link.scope,source.context.scope_key);
  const restored=make();
  await restored.openHistory(link.message_id,link.index,false,link.scope);
  await restored.loadHistory();
  assert.deepEqual(restored.snapshot().bound.context,source.context);
  assert.equal(restored.snapshot().bound.history_request_id,receipt.request_id);
  await restored.inspectOrigin();
  assert.deepEqual(restored.snapshot().inspectedReceipt.job,receipt.job);
  const count=routes.length;
  located=null;
  await controller.locateSource(message.message_id,0,'["STUDIO","wrong-owned-manuscript"]');
  assert.equal(located,null);
  assert.equal(routes.length,count);
  routes.push({message_id:message.message_id,request_id:receipt.request_id,module:source.context.target.module,context_sha256:source.context.context_sha256,url,quote:message.quote,current_source_state:restored.snapshot().bound.current_source_state,origin_request_read:true});
}
assert.equal(routes.length,4);
assert.equal(requests.some(item=>/\/messages$|\/annotations$/.test(item.route)),false);
const result={status:'PASS_ACTUAL_CONTROLLER_HTTP_SOURCE_NAVIGATION',new_model_calls:0,browser_verified:false,routes,requests};
fs.writeFileSync(output,JSON.stringify(result,null,2),{flag:'wx'});
process.stdout.write(JSON.stringify({status:result.status,original_routes:routes.length,new_model_calls:0,browser_verified:false})+'\n');
