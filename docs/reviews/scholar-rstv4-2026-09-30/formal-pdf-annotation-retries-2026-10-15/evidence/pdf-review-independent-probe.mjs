import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

// Execute the shipped page functions, including their real async continuations.
const html=fs.readFileSync('../RSTV4/src/rstv4/catalog_web.html','utf8');
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
   paper:{title:'Old Title',doi:null}});
 vm.runInContext(`let selectedCase='file-a',pdfReviewLoadToken=1,latestAnnotations={},commentSaveTimers={};\n${source}`,context);
 return {context,node,run:s=>vm.runInContext(s,context),editor:node('[data-annotation-comment="TITLE"]')};
}

const wait=deferred(); let reads=0,committed=false; const h=setup(async(path,body)=>{if(body)return wait.promise; reads++; return [record(committed?'committed-new-head':'old-head')];});
const save=h.run("savePdfAnnotation('TITLE','FOUND',{page_number:1,word_start:0,word_end:2})");
await new Promise(resolve=>setImmediate(resolve));
h.run('pdfReviewLoadToken++; latestAnnotations={};');
await h.run("loadPdfReviewAnnotations('file-a')");
committed=true; wait.resolve(record('committed-new-head')); await save;
console.log(JSON.stringify({reads,visibleHead:h.run('latestAnnotations.TITLE.annotation_id'),requests:h.run('annotationRequests.size'),notice:h.node('review-action-notice').textContent,paper:h.context.paper}));
assert.equal(h.run('latestAnnotations.TITLE.annotation_id'),'committed-new-head','Reopened same case must eventually read back committed old request');
