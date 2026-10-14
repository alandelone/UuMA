import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const host=vm.createContext({});
vm.runInContext(fs.readFileSync(new URL('../src/rstv4/catalog_collections.js',import.meta.url),'utf8'),host);
vm.runInContext(fs.readFileSync(new URL('../src/rstv4/catalog_scientific_review.js',import.meta.url),'utf8'),host);
const create=host.CatalogCollections.createPaperPicker;
const target={field_id:'f',topic_id:'t',track_id:null};
const row={paper_id:'p',title:'Original Catalog title',doi:null};
const response=(owner=target,papers=[row])=>({target:owner,papers,total:papers.length,has_more:false});
const store=()=>{const data=new Map();return {getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v)};};
let checks=0;
{
 const calls=[];const storage=store();const c=create({api:async path=>{calls.push(path);return response();},storage});c.setScope(target);await c.load();c.toggle('p',true);assert.equal(calls.length,1);assert.deepEqual(JSON.parse(JSON.stringify(c.paperIds())),['p']);
 const restored=create({api:async()=>response(),storage});restored.setScope(target);assert.equal(restored.state().selected[0].title,'Original Catalog title');restored.setScope({...target,topic_id:'other'});assert.equal(restored.paperIds().length,0);restored.setScope(target);assert.equal(restored.paperIds()[0],'p');checks++;
}
{
 let settle;const c=create({api:()=>new Promise(resolve=>settle=resolve),storage:store()});c.setScope(target);const pending=c.load('old');c.setScope({...target,topic_id:'new'});settle(response());assert.equal(await pending,null);assert.equal(c.state().rows.length,0);assert.equal(c.state().target.topic_id,'new');checks++;
}
{
 let fail=false;const c=create({api:async()=>{if(fail)throw Error('Offline');return response();},storage:store()});c.setScope(target);await c.load();c.toggle('p',true);fail=true;await assert.rejects(c.load('new'),/Offline/);assert.equal(c.paperIds()[0],'p');assert.equal(c.state().selected[0].title,'Original Catalog title');assert.ok(c.state().error.includes('读取失败'));checks++;
}
{
 const c=create({api:async()=>response(),storage:{getItem:()=>null,setItem:()=>{throw Error('Quota');}}});c.setScope(target);await c.load();c.toggle('p',true);assert.ok(c.state().storageProblem);c.setLocked(true);assert.equal(c.toggle('p',false),false);assert.equal(c.paperIds()[0],'p');checks++;
}
{
 const context={manuscript:{revision:1},context_sha256:'sha',author_structure:{sections:[{id:'actual-section',title:'Introduction'}]},nodes:[{node_id:'n',status:'APPROVED'},{node_id:'new',status:'APPROVED'}],bindings:{nodes:[{node_id:'n',section:'Introduction'}],evidence:[]},reviews:[]};
 let posts=0,body;
 const c=host.CatalogScientificReview.createController({api:async(path,input)=>{if(input){posts++;body=input;return {review_id:'proposal'};}return context;},storage:store(),makeKey:()=> 'source-selection'});
 await c.load('ms');c.edit({reason:'Real author section reviewed'});assert.equal(c.state().unresolvedSections.length,1);
 const placement=host.CatalogScientificReview.sectionChoices(context,c.state().draft,'n');assert.equal(placement.current,'Introduction');assert.equal(placement.legacy,true);
 await assert.rejects(c.propose(),/旧章节/);assert.equal(posts,0);
 assert.equal(c.placeNode('n','actual-section'),true);assert.equal(c.state().unresolvedSections.length,0);await c.propose();assert.equal(body.section_map['actual-section'][0],'n');
 c.edit({section_map:{Ghost:['n']}});assert.equal(c.selectNode('new',true),true);assert.equal(c.selectNode('n',false),true);assert.equal(Object.keys(c.state().draft.section_map).length,0);assert.equal(c.placeNode('new','Ghost'),false);checks++;
}
{
 const html=fs.readFileSync(new URL('../src/rstv4/catalog_web.html',import.meta.url),'utf8');const begin=html.indexOf("document.addEventListener('change',event=>{");const end=html.indexOf("      let collectPaperSearchTimer",begin);assert.ok(begin>=0&&end>begin);
 let change;const select={disabled:true};const c={selectNode:(id,checked)=>id==='node'&&checked,placeNode:()=>true};
 const targetElement={dataset:{scientificNode:'node'},checked:true,id:'node-check',closest:selector=>{assert.equal(selector,'.item');return {querySelector:()=>select};}};
 const context=vm.createContext({document:{addEventListener:(name,fn)=>{change=fn;}},scientificReview:c,collectPaperPicker:{}});
 vm.runInContext(html.slice(begin,end),context);change({target:targetElement});assert.equal(select.disabled,false);checks++;
}
{
 const html=fs.readFileSync(new URL('../src/rstv4/catalog_web.html',import.meta.url),'utf8');const start=html.indexOf('function renderScientificReview('),end=html.indexOf('async function scientificReviewAction(',start);const hostElement={innerHTML:''};
 const context=vm.createContext({view:'scientific_review',$:()=>hostElement,escapeHtml:value=>String(value??'').replaceAll('<','&lt;'),CatalogScientificReview:host.CatalogScientificReview});
 vm.runInContext(html.slice(start,end),context);
 const source={manuscript:{title:'Actual manuscript',revision:1},author_structure:{sections:[{id:'actual',title:'Current section'}]},nodes:[{node_id:'n',status:'APPROVED',statement:'<Raw original statement>',revision:1}],evidence:[],bindings:{nodes:[],evidence:[]},reviews:[]};
 context.renderScientificReview({context:source,draft:{node_ids:['n'],evidence_ids:[],section_map:{'Old heading':['n']},reason:'Review'}});
 assert.ok(hostElement.innerHTML.includes('旧绑定：Old heading（需重新选择）'));assert.ok(hostElement.innerHTML.includes('value="actual"'));assert.ok(hostElement.innerHTML.includes('&lt;Raw original statement>'));checks++;
}
console.log(checks+' controlled existing-paper and actual section-handler checks passed');
