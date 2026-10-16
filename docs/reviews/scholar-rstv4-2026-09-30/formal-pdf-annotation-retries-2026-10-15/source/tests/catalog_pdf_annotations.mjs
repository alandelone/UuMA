import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

// Execute the shipped page functions, including their real async continuations.
const html=fs.readFileSync(new URL('../src/rstv4/catalog_web.html',import.meta.url),'utf8');
const begin=html.includes('let annotationReadSerial=')?'let annotationReadSerial=':'async function loadPdfReviewAnnotations(';
const source=html.slice(html.indexOf(begin),html.indexOf("      document.addEventListener('pointerdown'",html.indexOf(begin)));
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const record=(id='head',comment='saved')=>({annotation_id:id,field_name:'TITLE',decision:'FOUND',page_number:1,word_start:0,word_end:2,selected_text:'Original Source Title',comment,value_before:'Old Title',value_after:'Original Source Title',catalog_title:'Original Source Title',catalog_doi:null});
const plain=x=>JSON.parse(JSON.stringify(x));
function setup(api){
 const nodes=new Map();
 const node=key=>{if(!nodes.has(key))nodes.set(key,{textContent:'',value:'',hidden:false,children:[],dataset:{},classList:{toggle(){},add(){},remove(){}},append(child){this.children.push(child);}});return nodes.get(key);};
 const context=vm.createContext({api,console,crypto:{randomUUID:()=>`request-${++context.counter}`},counter:0,setTimeout,clearTimeout,
   document:{querySelector:node,activeElement:null,createElement:()=>({dataset:{}})},$:node,
   reviewCase:()=>context.paper,renderCases(){},applyAnnotationHighlights(){},loadSummary(){},
   reviewWorkflow:{load:async()=>{}},errorText:e=>e.message,
   paper:{paper_id:'paper-a',title:'Old Title',doi:null}});
 vm.runInContext(`let selectedCase='file-a',pdfReviewLoadToken=1,latestAnnotations={},commentSaveTimers={};\n${source}`,context);
 return {context,node,run:s=>vm.runInContext(s,context),editor:node('[data-annotation-comment="TITLE"]')};
}
let checks=0;
{
 const wait=deferred();const h=setup(()=>wait.promise);const pending=h.run("loadPdfReviewAnnotations('file-a')");
 h.run('pdfReviewLoadToken++');wait.resolve([record('obsolete')]);await pending;
 assert.equal(h.run('latestAnnotations.TITLE?.annotation_id'),undefined,'old same-case read must not publish into reopened view');checks++;
}
{
 const one=deferred(),two=deferred();let calls=0;const h=setup(()=>++calls===1?one.promise:two.promise);
 const old=h.run("loadPdfReviewAnnotations('file-a')"),fresh=h.run("loadPdfReviewAnnotations('file-a')");
 two.resolve([record('new')]);await fresh;one.resolve([record('old')]);await old;
 assert.equal(h.run('latestAnnotations.TITLE.annotation_id'),'new');checks++;
}
{
 const h=setup(async()=>[record()]);await h.run("loadPdfReviewAnnotations('file-a')");
 h.editor.value='unsaved newer note';h.run("scheduleAnnotationComment('TITLE')");h.run("clearTimeout(commentSaveTimers.TITLE)");
 await h.run("loadPdfReviewAnnotations('file-a')");assert.equal(h.editor.value,'unsaved newer note','blurred draft survives readback');checks++;
}
{
 const calls=[];let fail=true;const h=setup(async(path,body)=>{if(!body)return [record('saved')];calls.push(plain(body));if(fail){fail=false;throw Error('connection lost after commit');}return record('saved');});
 await h.run("savePdfAnnotation('TITLE','FOUND',{page_number:1,word_start:0,word_end:2})");
 await h.run("savePdfAnnotation('TITLE','FOUND',{page_number:1,word_start:0,word_end:2})");
 assert.equal(calls.length,2);assert.deepEqual(calls[1],calls[0],'unknown save retries its original request ID and payload');checks++;
}
{
 const calls=[],wait=deferred();const h=setup(async(path,body)=>{if(!body)return [record()];calls.push(body);return wait.promise;});
 const one=h.run("savePdfAnnotation('TITLE','FOUND',{page_number:1,word_start:0,word_end:2})");
 const two=h.run("savePdfAnnotation('TITLE','FOUND',{page_number:1,word_start:0,word_end:2})");
 await new Promise(resolve=>setImmediate(resolve));assert.equal(calls.length,1,'duplicate blur/click shares in-flight save');
 wait.resolve(record());await Promise.all([one,two]);checks++;
}
{
 const calls=[];const h=setup(async(path,body)=>{if(!body)return [record()];calls.push(plain(body));return record('note','new note');});
 await h.run("loadPdfReviewAnnotations('file-a')");h.editor.value='new note';h.run("scheduleAnnotationComment('TITLE')");
 h.run("clearTimeout(commentSaveTimers.TITLE)");h.run("selectedCase='file-b';pdfReviewLoadToken++");
 await h.run("loadPdfReviewAnnotations('file-b')");
 assert.equal(calls.length,0);assert.equal(h.editor.value,'saved','another case never receives the old draft');checks++;
}
{
 const wait=deferred();const h=setup(async(path,body)=>body?wait.promise:path.includes('/papers/')?{title:'Readback Title',doi:null}:[record('readback')]);
 const saving=h.run("savePdfAnnotation('TITLE','FOUND',{page_number:1,word_start:0,word_end:2})");
 await new Promise(resolve=>setImmediate(resolve));h.run('pdfReviewLoadToken++');wait.resolve(record());await saving;
 assert.equal(h.context.paper.title,'Readback Title','reopened case reads current Catalog instead of the old POST snapshot');
 assert.equal(h.run('latestAnnotations.TITLE.annotation_id'),'readback');checks++;
}
{
 const calls=[];const h=setup(async(path,body)=>{if(!body)return [record()];calls.push(plain(body));return record('noted','note');});
 await h.run("loadPdfReviewAnnotations('file-a')");h.editor.value='note';await h.run("scheduleAnnotationComment('TITLE',true)");
 assert.equal(calls[0].expected_annotation_id,'head','comment binds to the exact source annotation');checks++;
 assert.deepEqual(calls[0].expected_catalog_value,{value:'Original Source Title'},'comment cannot restore a value changed through another file');
}
{
 let posts=0;const h=setup(async(path,body)=>{if(body){posts++;return record();}throw Error('readback offline');});
 await h.run("savePdfAnnotation('TITLE','FOUND',{page_number:1,word_start:0,word_end:2})");
 assert.match(h.node('review-action-notice').textContent,/已保存/);assert.equal(posts,1);checks++;
}
{
 const wait=deferred();let committed=false,reads=0;
 const h=setup(async(path,body)=>{if(body)return wait.promise;if(path.includes('/papers/'))return {title:'Current after reopen',doi:'10.1234/new'};reads++;return [record(committed?'new-head':'old-head')];});
 const pending=h.run("savePdfAnnotation('TITLE','FOUND',{page_number:1,word_start:0,word_end:2})");
 await new Promise(resolve=>setImmediate(resolve));h.run('pdfReviewLoadToken++');await h.run("loadPdfReviewAnnotations('file-a')");
 assert.equal(h.run('latestAnnotations.TITLE.annotation_id'),'old-head');committed=true;wait.resolve(record('new-head'));await pending;
 assert.equal(reads,2);assert.equal(h.run('latestAnnotations.TITLE.annotation_id'),'new-head');
 assert.equal(h.context.paper.title,'Current after reopen');assert.equal(h.run('annotationRequests.size'),0);
 assert.doesNotMatch(h.node('review-action-notice').textContent,/尚未确认/);checks++;
}
{
 const calls=[];let fail=true;const h=setup(async(path,body)=>{if(!body)return [record()];calls.push(plain(body));if(fail){fail=false;throw Error('unknown commit');}return record();});
 await h.run("savePdfAnnotation('TITLE','FOUND',{page_number:1,word_start:0,word_end:2},'first')");
 await h.run("savePdfAnnotation('TITLE','FOUND',{page_number:1,word_start:0,word_end:2},'changed')");assert.equal(calls.length,1);
 await h.run("retryPdfAnnotation('TITLE')");assert.deepEqual(calls[1],calls[0]);checks++;
}
{
 const calls=[];let current=record('old');const h=setup(async(path,body)=>{if(!body)return [current];calls.push(plain(body));const error=Error('source head changed');error.status=409;throw error;});
 await h.run("loadPdfReviewAnnotations('file-a')");h.editor.value='preserved draft';h.run("scheduleAnnotationComment('TITLE')");h.run('clearTimeout(commentSaveTimers.TITLE)');
 current=record('new');await h.run("loadPdfReviewAnnotations('file-a')");await h.run("scheduleAnnotationComment('TITLE',true)");
 assert.equal(calls[0].expected_annotation_id,'old');assert.equal(h.editor.value,'preserved draft');
 assert.match(h.node('review-action-notice').textContent,/未保存/);assert.equal(h.run('annotationRequests.size'),0);checks++;
}
{
 const h=setup(async()=>[record()]);await h.run("loadPdfReviewAnnotations('file-a')");h.editor.value='case A draft';
 h.run("scheduleAnnotationComment('TITLE');clearTimeout(commentSaveTimers.TITLE);selectedCase='file-b';pdfReviewLoadToken++");
 await h.run("loadPdfReviewAnnotations('file-b')");assert.equal(h.editor.value,'saved');
 h.run("selectedCase='file-a';pdfReviewLoadToken++");await h.run("loadPdfReviewAnnotations('file-a')");assert.equal(h.editor.value,'case A draft');checks++;
}
{
 const timerCallbacks=new Map();let timerId=0;const calls=[];const h=setup(async(path,body)=>{if(!body)return [record()];calls.push(body);return record();});
 h.context.setTimeout=(fn,delay)=>{assert.equal(delay,700);timerCallbacks.set(++timerId,fn);return timerId;};
 h.context.clearTimeout=id=>timerCallbacks.delete(id);
 await h.run("loadPdfReviewAnnotations('file-a')");h.editor.value='note';h.run("scheduleAnnotationComment('TITLE')");
 const delayed=[...timerCallbacks.values()][0];h.run("selectedCase='file-b';pdfReviewLoadToken++");await delayed();assert.equal(calls.length,0);checks++;
}
{
 const waiting=deferred(),newRead=deferred();let posted=0;
 const h=setup(async(path,body)=>{if(body){posted++;return posted===1?waiting.promise:record('doi');}return path.includes('file-b')?newRead.promise:[record()];});
 const a=h.run("savePdfAnnotation('TITLE','FOUND',{page_number:1,word_start:0,word_end:2})");
 const b=h.run("savePdfAnnotation('DOI','ABSENT')");await new Promise(resolve=>setImmediate(resolve));
 h.run("selectedCase='file-b';pdfReviewLoadToken++");const read=h.run("loadPdfReviewAnnotations('file-b')");
 waiting.resolve(record());await Promise.all([a,b]);newRead.resolve([record('case-b-head')]);await read;
 assert.equal(h.run('latestAnnotations.TITLE.annotation_id'),'case-b-head','old case queued writes do not invalidate current case reads');checks++;
}
{
 const h=setup(async()=>[record()]);const query=h.context.document.querySelector;
 h.context.document.querySelector=selector=>selector.includes('data-review-decision')?null:query(selector);
 assert.equal(await h.run("loadPdfReviewAnnotations('file-a')"),true,'absent identity controls do not break annotation reads');checks++;
}
console.log(`PASS ${checks} shipped PDF annotation async checks; native_browser_executed=false`);
