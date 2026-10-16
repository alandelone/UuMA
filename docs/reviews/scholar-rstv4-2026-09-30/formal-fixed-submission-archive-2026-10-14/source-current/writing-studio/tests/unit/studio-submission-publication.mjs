/* Executes the shipped SubmissionPanel and ReadingView; no browser/model/database claim. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';
import { fileURLToPath } from 'node:url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
let active;
const hooks = {
  useState(value) { const r=active,n=r.index++;if(!(n in r.slots))r.slots[n]=value;return[r.slots[n],v=>{r.slots[n]=typeof v==='function'?v(r.slots[n]):v;r.dirty=true;}]; },
  useRef(value) { const r=active,n=r.index++;r.slots[n]??={current:value};return r.slots[n]; },
  useEffect(fn,deps) { const r=active,n=r.index++;const prev=r.slots[n];if(!prev||deps.some((v,i)=>!Object.is(v,prev[i]))){r.slots[n]=deps;r.effects.push(fn);} },
};
function mount(fn,props) {
  const r={slots:[],effects:[],index:0,dirty:false,props};
  r.render=()=>{for(let pass=0;pass<12;pass++){r.index=0;r.dirty=false;active=r;r.tree=fn(r.props);active=null;r.effects.splice(0).forEach(f=>f());if(!r.dirty)return r.tree;}throw Error('Unexpected render loop');};
  r.render();return r;
}
function nodes(tree,predicate) {
  if(Array.isArray(tree))return tree.flatMap(n=>nodes(n,predicate));
  if(!tree||typeof tree!=='object')return[];
  return[...(predicate(tree)?[tree]:[]),...nodes(tree.props?.children,predicate)];
}
function text(v){return Array.isArray(v)?v.map(text).join(''):v&&typeof v==='object'?text(v.props?.children):v==null?'':String(v);}
function control(r,label){const found=nodes(r.render(),n=>n.props?.['aria-label']===label);assert.equal(found.length,1,label);return found[0];}
function button(r,label){const found=nodes(r.render(),n=>n.type==='Button'&&text(n.props.children)===label);assert.equal(found.length,1,label);return found[0];}
function change(r,label,value){control(r,label).props.onChange({target:typeof value==='boolean'?{checked:value}:{value}});r.render();}
async function click(r,label){const b=button(r,label);assert.equal(Boolean(b.props.disabled),false,label+' disabled');await b.props.onClick();await tick();r.render();}
async function tick(){for(let i=0;i<30;i++)await Promise.resolve();}
const source=fs.readFileSync(path.join(__dirname,'../../components/studio-workspace.tsx'),'utf8');
const start=source.indexOf('function ReadingView('),end=source.indexOf('function quoteFromSelection(',start);
assert(start>0&&end>start);
const compiled=ts.transpileModule(source.slice(start,end)+'\nexports.SubmissionPanel=SubmissionPanel;exports.ReadingView=ReadingView;',{
  compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022},
}).outputText;
function setup(){
  const attempts=[],api={},exports={},ids={n:0};
  api.recordSubmission=async(...args)=>{attempts.push(args);return event('SUBMITTED','v5');};
  const scope={exports,...hooks,studioApi:api,API_BASE:'http://fixture.invalid/api',crypto:{randomUUID:()=> 'software-operation-'+(++ids.n)},
    Button:'Button',Input:'Input',LoaderCircle:'LoaderCircle',FileDown:'FileDown',Pencil:'Pencil',CitationText:'CitationText',Intl,Date,Error,
    require:n=>{if(n==='react/jsx-runtime')return{jsx:(type,props,key)=>({type,props,key}),jsxs:(type,props,key)=>({type,props,key})};throw Error(n);}};
  vm.runInNewContext(compiled,scope);
  return{...exports,attempts,api};
}
function event(status,id='v5',venue='Fixture venue',round=1){
  return{event_id:'event-'+status+'-'+id,status,venue,round,created_at:'2026-10-14T00:00:00Z',binding:{status:'BOUND',snapshot:{
    generated_version:{manuscript_version_id:id,version:id==='v5'?5:6,document_revision:62,content_sha256:'content',inputs_sha256:'inputs',job_id:'job-fixed',template_manifest:{author_document_sha256:'author-sha'}},
    parent_event_id:null,accepted_event_id:null,
  }}};
}
const doc=id=>({asset_id:id,asset_kind:'DOCUMENT',filename:id+'.pdf',media_type:'application/pdf',status:'READY',metadata:{}});
const file=id=>({asset_id:id,filename:id+'.pdf',sha256:'sha-'+id,byte_size:123,media_type:'application/pdf'});
function props(overrides={}){
  return{manuscriptId:'ms',submissions:[],generated:{generated_version_id:'v5',version:5,input_revision:62,blocks:[],references:[],citation_style:'numeric_first_use'},
    activeVersionId:'v5',stale:false,stage:'FINALIZATION_SUBMISSION',publication:{accepted_event_id:null,accepted_generated_version_id:null,completion:null},
    publicationFiles:[doc('final'),doc('proof')],defaultVenue:'Fixture venue',onSaved:async()=>{},onArchiveFile:async()=>{},...overrides};
}
async function run(){
  {
    const expression=source.match(/<ReadingView\b[\s\S]*?stale=\{([^}]+)\}/)?.[1];
    assert(expression,'The shipped parent must pass a stale state to ReadingView');
    for(const flag of [true,1]) {
      const effective=vm.runInNewContext(expression,{workspace:{generated_is_stale:false,manuscript:{needs_scientific_review:flag}},Boolean});
      assert.equal(effective,true,'Legacy generation still respects an explicit scientific review hold');
    }
    assert.equal(vm.runInNewContext(expression,{workspace:{generated_is_stale:false,manuscript:{needs_scientific_review:0}},Boolean}),false);
    console.log('PASS actual parent wiring disables publication for a legacy scientific-review hold');
  }
  {
    const h=setup(),r=mount(h.SubmissionPanel,props({activeVersionId:'v6',submissions:[{event_id:'legacy',status:'ACCEPTED',venue:'Fixture venue',round:1,created_at:'old',binding:{status:'UNBOUND'}}]}));
    assert(text(r.tree).includes('旧记录 · 版本未绑定'));
    change(r,'确认当前显示的终稿版本',true);
    assert(button(r,'＋ 记录').props.disabled);
    await button(r,'＋ 记录').props.onClick();await tick();assert.equal(h.attempts.length,0);
    change(r,'投稿状态','ACCEPTED');await click(r,'＋ 记录');
    assert.equal(h.attempts[0][5].generated_version_id,'v5','Historical editorial event must bind displayed version, never active');
    console.log('PASS historical/legacy records never borrow active version; final submission guarded');
  }
  {
    const h=setup(),r=mount(h.SubmissionPanel,props());
    assert(button(r,'＋ 记录').props.disabled);
    change(r,'投稿／出版说明','Retain this exact author input');
    change(r,'确认当前显示的终稿版本',true);
    h.api.recordSubmission=async(...args)=>{h.attempts.push(args);throw Error('network result unconfirmed');};
    await click(r,'＋ 记录');
    assert.equal(control(r,'投稿／出版说明').props.value,'Retain this exact author input');
    await click(r,'＋ 记录');
    assert.equal(h.attempts.length,2);
    assert.equal(h.attempts[0][5].operation_id,h.attempts[1][5].operation_id);
    assert.equal(h.attempts[0][5].acknowledged,true);
    assert.equal(h.attempts[0][5].generated_version_id,'v5');
    console.log('PASS failed same-payload retry preserves input and operation identity');
  }
  {
    const h=setup();let refreshes=0;
    const r=mount(h.SubmissionPanel,props({onSaved:async()=>{if(++refreshes===1)throw Error('read failed');}}));
    change(r,'确认当前显示的终稿版本',true);await click(r,'＋ 记录');
    assert.equal(h.attempts.length,1);assert(button(r,'＋ 记录').props.disabled);
    assert(text(r.tree).includes('事件已保存；读取结果暂未确认'));
    await click(r,'重新读取投稿与归档状态');
    assert.equal(h.attempts.length,1);assert.equal(refreshes,2);
    console.log('PASS acknowledged event read recovery never repeats successful POST');
  }
  {
    const h=setup(),r=mount(h.SubmissionPanel,props({submissions:[event('ACCEPTED','v6')]}));
    change(r,'投稿状态','PUBLISHED');change(r,'确认当前显示的终稿版本',true);
    assert(button(r,'＋ 记录').props.disabled);
    r.props.submissions=[event('ACCEPTED','v5','Wrong venue')];r.render();assert(button(r,'＋ 记录').props.disabled);
    r.props.submissions=[event('ACCEPTED','v5','Fixture venue',2)];r.render();assert(button(r,'＋ 记录').props.disabled);
    r.props.submissions=[event('ACCEPTED')];r.render();await click(r,'＋ 记录');
    assert.equal(h.attempts[0][3],'PUBLISHED');assert.equal(h.attempts[0][5].generated_version_id,'v5');
    for (const next of ['WITHDRAWN','REVISION_REQUESTED']) {
      const withdrawn=mount(h.SubmissionPanel,props({submissions:[event('ACCEPTED'),event(next)]}));
      change(withdrawn,'投稿状态','PUBLISHED');change(withdrawn,'确认当前显示的终稿版本',true);
      assert(button(withdrawn,'＋ 记录').props.disabled);
    }
    console.log('PASS published requires exact bound acceptance venue, round and version; later withdrawal or revision invalidates it');
  }
  {
    const h=setup(),r=mount(h.SubmissionPanel,props({stage:'PUBLICATION',submissions:[event('ACCEPTED'),event('PUBLISHED')],
      publication:{accepted_event_id:'event-ACCEPTED-v5',accepted_generated_version_id:'v5',completion:null}}));
    assert(button(r,'确认归档完成').props.disabled);
    change(r,'终稿文件','final');change(r,'校样文件','proof');
    assert(button(r,'确认归档完成').props.disabled);
    change(r,'校样已核对并确认归档',true);
    await click(r,'确认归档完成');
    const a=h.attempts[0];assert.equal(a[3],'ARCHIVED');
    assert.equal(a[5].final_asset_id,'final');assert.equal(a[5].proof_asset_id,'proof');assert.equal(a[5].acknowledged,true);
    assert.equal(a[5].generated_version_id,'v5');
    r.props.stale=true;r.render();assert(button(r,'确认归档完成').props.disabled);
    const completion={event_id:'archived',generated_version_id:'v5',status:'UNAVAILABLE',files:{final:file('final'),proof:file('proof')}};
    r.props.publication.completion=completion;r.render();
    assert(text(r.tree).includes('原归档文件不可用'));assert(text(r.tree).includes('sha-final'));assert(text(r.tree).includes('sha-proof'));
    console.log('PASS archive requires published accepted version, both explicit files and author confirmation; unavailable hashes retained');
  }
  {
    const h=setup();let saved=0;
    const r=mount(h.SubmissionPanel,props({onArchiveFile:async()=>{saved++;throw Error('upload refused');}}));
    const input={files:[{name:'proof.pdf'}],value:'proof.pdf'};
    await control(r,'上传校样或终稿文件').props.onChange({currentTarget:input});r.render();
    assert.equal(saved,1);assert.equal(input.value,'proof.pdf');assert(text(r.tree).includes('upload refused'));
    assert(text(r.tree).includes('上传成功不代表校样已核对或归档完成'));
    assert.equal(h.attempts.length,0);
    console.log('PASS failed upload retains selected file and never creates archive completion');
  }
  {
    const h=setup(),base=props({content:'Software manuscript',artifacts:[],findings:[],packageDownloads:null,onEdit:()=>{},onReview:()=>{},onPackage:()=>{},onStage:()=>{},onWorkspaceRefresh:async()=>{}});
    const r=mount(h.ReadingView,base);
    assert(button(r,'出版归档').props.disabled);
    r.props.publication={accepted_event_id:'a',accepted_generated_version_id:'v5',completion:null};r.render();
    assert.equal(button(r,'出版归档').props.disabled,false);
    r.props.generated={...r.props.generated,generated_version_id:'v4'};r.render();assert(button(r,'出版归档').props.disabled);
    r.props.generated=base.generated;r.props.stale=true;r.render();assert(button(r,'出版归档').props.disabled);
    r.props.content='';r.render();assert(text(r.tree).includes('还没有成文版本'));
    assert.equal(nodes(r.tree,n=>n.type==='Button'&&text(n.props.children)==='出版归档').length,0);
    console.log('PASS existing Stage6 entry requires current accepted displayed version; zero content has no completion action');
  }
}
run().catch(error=>{console.error(error);process.exitCode=1;});
