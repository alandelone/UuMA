(function(root){
  'use strict';
  function createController({api,makeKey,onState=()=>{},onStarted=()=>{},storage=null,requireDurableRequest=false}){
    let input=null,signature='',key='',preview=null,pending=false,epoch=0,created=null,storageProblem='';
    const state=()=>({input,key,preview,pending,created,storageProblem});
    function persist(confirmed=false){
      if(!storage){if(requireDurableRequest)storageProblem='浏览器暂时无法保存采集请求，请恢复存储后再开始。';return;}
      try{
        const value=JSON.stringify({signature,key,confirmed});storage.setItem('rstv4-collection-request',value);
        if(storage.getItem('rstv4-collection-request')!==value)throw Error('Storage did not retain the request');
        storageProblem='';
      }catch{storageProblem='浏览器暂时无法保存采集请求，请恢复存储后再开始。';}
    }
    function begin(){
      if(pending)return;
      let saved=null;try{saved=JSON.parse(storage?.getItem('rstv4-collection-request')||'null');}catch{}
      if(created||saved?.confirmed){
        try{storage?.removeItem('rstv4-collection-request');}catch{}
        input=null;signature='';key='';preview=null;created=null;epoch++;
      }
    }
    function publish(message){onState({...state(),message});}
    function change(next){
      if(pending)return;
      const nextSignature=JSON.stringify(next);
      if(nextSignature!==signature){
        input=JSON.parse(nextSignature);signature=nextSignature;preview=null;created=null;epoch++;
        let saved=null;try{saved=JSON.parse(storage?.getItem('rstv4-collection-request')||'null');}catch{}
        key=saved?.signature===signature&&typeof saved.key==='string'?saved.key:makeKey();
      }
      persist();publish(storageProblem||'检查输入可查看 Catalog 去重与文件复用；开始采集才会创建任务。');
    }
    async function check(){
      if(!input)throw new Error('请从真实 Topic 或 Track 进入采集。');
      const token=++epoch,body={...input,idempotency_key:key};
      publish('正在检查输入与 Catalog 文件…');
      try{
        const result=await api('/api/catalog/collections/preview',body);
        if(token!==epoch)return null;
        preview=result;publish(`检查通过；已有 ${result.counts.catalog_papers} 篇，可复用 ${result.counts.reusable_pdfs} 份 PDF，待审核 ${result.counts.needs_review} 篇。尚未创建任务。`);
        return result;
      }catch(error){if(token===epoch)publish(`检查失败：${error.message}`);throw error;}
    }
    async function start(){
      if(pending)return null;
      if(!input)throw new Error('请从真实 Topic 或 Track 进入采集。');
      persist();if(storageProblem){publish(storageProblem);throw new Error(storageProblem);}
      pending=true;epoch++;
      const body={...input,idempotency_key:key};
      publish('正在创建采集任务…');
      try{
        created=await api('/api/catalog/collections',body);
        persist(true);
        publish(`已创建采集 ${created.collection_id}，共 ${created.counts.jobs} 项任务。`);
      }catch(error){publish(`创建未确认：${error.message}。保留输入后再点开始，会用同一请求核对结果。`);throw error;}
      finally{pending=false;onState(state());}
      try{await onStarted(created);}catch(error){publish(`采集已创建，更新页面失败：${error.message}。可返回总览更新状态。`);}
      return created;
    }
    return {begin,change,check,start,state};
  }
  function createPaperPicker({api,storage=null,onState=()=>{},onSelection=()=>{}}){
    let target=null,rows=[],selected=new Map(),pending=false,locked=false,epoch=0,query='',offset=0,total=0,hasMore=false,error='',storageProblem='';
    const clone=v=>JSON.parse(JSON.stringify(v));
    const key=()=> 'rstv4-collection-paper-draft:'+JSON.stringify(target);
    const state=()=>({target:clone(target),rows:clone(rows),selected:clone([...selected.values()]),pending,locked,query,offset,total,hasMore,error,storageProblem});
    const publish=()=>onState(state());
    function save(){try{if(!storage)throw Error('Unavailable');const raw=JSON.stringify([...selected.values()]);storage.setItem(key(),raw);if(storage.getItem(key())!==raw)throw Error('Not retained');storageProblem='';}catch{storageProblem='所选论文暂时无法保存，请恢复浏览器存储后再开始采集。';}}
    function setScope(next){
      const same=JSON.stringify(target)===JSON.stringify(next);if(same)return;
      epoch++;target=clone(next);rows=[];selected=new Map();pending=false;query='';offset=0;total=0;hasMore=false;error='';storageProblem='';
      try{const saved=JSON.parse(storage?.getItem(key())||'[]');if(!Array.isArray(saved)||saved.length>500||saved.some(row=>!row||typeof row.paper_id!=='string'))throw Error('Invalid saved selection');selected=new Map(saved.map(row=>[row.paper_id,row]));}catch{storageProblem='原论文选择草稿无法读取，请先恢复并核对浏览器存储。';}
      publish();onSelection(state());
    }
    async function load(nextQuery=query,nextOffset=0){
      if(!target||locked)return null;
      const token=++epoch,owner=clone(target);query=nextQuery;offset=nextOffset;pending=true;error='';publish();
      const params=Object.entries({...owner,q:query,offset,limit:25}).filter(([,v])=>v!==null&&v!==undefined).map(([k,v])=>encodeURIComponent(k)+'='+encodeURIComponent(v)).join('&');
      try{const result=await api('/api/catalog/collections/paper-options?'+params);if(token!==epoch)return null;
        if(result.target.field_id!==owner.field_id||result.target.track_id!==owner.track_id||(owner.topic_id&&result.target.topic_id!==owner.topic_id))throw Error('返回的研究归属与当前选择不一致');
        rows=result.papers;total=result.total;hasMore=result.has_more;return result;
      }catch(failure){if(token===epoch){error='Catalog 读取失败：'+failure.message;rows=[];}throw failure;}
      finally{if(token===epoch){pending=false;publish();}}
    }
    function toggle(paperId,checked){
      if(locked||!target)return false;
      const row=rows.find(item=>item.paper_id===paperId)||selected.get(paperId);if(!row)return false;
      if(checked){if(selected.size>=500&&!selected.has(paperId)){error='每次最多选择 500 篇；请分批采集。';publish();return false;}selected.set(paperId,clone(row));}else selected.delete(paperId);
      save();publish();onSelection(state());return true;
    }
    function setLocked(value){if(locked===value)return;locked=value;publish();}
    return {setScope,load,toggle,setLocked,state,paperIds:()=>[...selected.keys()]};
  }
  function createProgressController({api,storage,makeKey,onState=()=>{}}){
    let id='',progress=null,draft={limits:null,reason:'',revision:null},request=null,pending=false,epoch=0,error='',storageProblem='';
    const clone=value=>JSON.parse(JSON.stringify(value));
    const state=()=>({id,progress,draft:clone(draft),request,pending,error,storageProblem,comparisonRequired:Boolean(progress&&draft.revision!==progress.revision)});
    const key=()=> 'rstv4-collection-budget:'+id,publish=()=>onState(state());
    function save(){try{const raw=JSON.stringify({draft,request});storage.setItem(key(),raw);if(storage.getItem(key())!==raw)throw Error('Not retained');storageProblem='';}catch{storageProblem='预算草稿无法保存，请恢复存储后再提交。';}}
    async function load(nextId,referenceOffset=0){
      const token=++epoch;
      if(nextId!==id){id=nextId;progress=null;request=null;draft={limits:null,reason:'',revision:null};error='';try{const restored=JSON.parse(storage?.getItem(key())||'null');if(restored){draft=restored.draft;request=restored.request;}}catch{storageProblem='原预算草稿无法恢复。';}}
      try{const data=await api('/api/catalog/collections/'+encodeURIComponent(id)+'/progress?reference_offset='+referenceOffset);if(token!==epoch)return null;progress=data;if(draft.revision===null){draft.revision=data.revision;draft.limits=data.budget.limits||{max_papers:500,max_registered_pdf_bytes:10737418240,max_active_seconds:86400,max_task_attempts:null};}save();publish();return data;}
      catch(failure){if(token===epoch){error=failure.message;publish();}throw failure;}
    }
    function edit(values){if(pending||request)return;draft={...draft,...clone(values)};save();if(storageProblem)publish();}
    function compare(){if(pending||request||!progress)return;draft.revision=progress.revision;save();publish();}
    async function submit(){
      if(pending)return null;if(!progress)throw Error('采集状态尚未读回。');
      if(!request){if(state().comparisonRequired)throw Error('采集状态已改变，请对照后再保存预算。');if(!draft.reason.trim())throw Error('请说明预算调整的原因。');request={request_id:makeKey(),expected_revision:draft.revision,limits:clone(draft.limits),reason:draft.reason.trim()};}
      save();if(storageProblem)throw Error(storageProblem);const token=epoch,owner=id,body=clone(request);pending=true;error='';publish();
      try{const result=await api('/api/catalog/collections/'+encodeURIComponent(owner)+'/budget',body);if(token===epoch){request=null;draft.revision=result.revision;save();await load(owner);}return result;}
      catch(failure){if(token===epoch){error=failure.message;if([404,409,422].includes(failure.status)){request=null;save();}publish();if(failure.status===409)try{await load(owner);}catch{}}throw failure;}
      finally{pending=false;publish();}
    }
    function leave(){epoch++;if(id)save();progress=null;}
    return {load,edit,compare,submit,leave,state};
  }
  function createDeepReadController({api,storage,makeKey,onState=()=>{}}){
    let paper=null,draft={collection_id:'',parse_run_id:'',reason:''},request=null,pending=false,epoch=0,error='',storageProblem='',receipt=null;
    const copy=value=>JSON.parse(JSON.stringify(value));
    const state=()=>({paper,draft:copy(draft),request:request?copy(request):null,pending,error,storageProblem,receipt});
    const key=()=> 'rstv4-deep-read:'+paper.paper_id,publish=()=>onState(state());
    function retain(){try{const raw=JSON.stringify({draft,request});storage.setItem(key(),raw);if(storage.getItem(key())!==raw)throw Error('Not retained');storageProblem='';}catch{storageProblem='深读草稿无法保存，请恢复存储后再提交。';}}
    function load(data){epoch++;pending=false;receipt=null;error='';paper=data;draft={collection_id:'',parse_run_id:'',reason:''};request=null;storageProblem='';try{const saved=JSON.parse(storage.getItem(key())||'null');if(saved){draft=saved.draft;request=saved.request;}}catch{storageProblem='原深读草稿无法恢复，请先恢复浏览器存储。';}publish();}
    function edit(values){if(pending||request)return;draft={...draft,...copy(values)};retain();if(storageProblem)publish();}
    async function submit(){
      if(pending)return null;if(!paper)throw Error('论文尚未读回。');
      if(!request){if(!paper.collections?.some(c=>c.collection_id===draft.collection_id))throw Error('请选择这篇论文所属的采集。');if(!paper.parse_runs?.some(p=>p.parse_run_id===draft.parse_run_id&&p.status==='SUCCEEDED'))throw Error('请选择实际已完成的解析版本。');if(!draft.reason.trim())throw Error('请说明请求深读的理由。');request={collection_id:draft.collection_id,body:{paper_id:paper.paper_id,parse_run_id:draft.parse_run_id,reason:draft.reason.trim(),idempotency_key:makeKey()}};}
      retain();if(storageProblem)throw Error(storageProblem);const owner=paper.paper_id,token=epoch,frozen=copy(request);pending=true;error='';publish();
      try{const job=await api('/api/catalog/collections/'+encodeURIComponent(frozen.collection_id)+'/deep-read',frozen.body);if(token===epoch&&paper.paper_id===owner){receipt=job;request=null;retain();publish();}return job;}
      catch(failure){if(token===epoch){error=failure.message;if([404,409,422].includes(failure.status)){request=null;retain();}publish();}throw failure;}
      finally{if(token===epoch){pending=false;publish();}}
    }
    function leave(){epoch++;pending=false;paper=null;}
    return {load,edit,submit,leave,state};
  }
  root.CatalogCollections={createController,createPaperPicker,createProgressController,createDeepReadController};
})(typeof window==='undefined'?globalThis:window);
