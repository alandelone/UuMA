(function(root){
  'use strict';
  function createController({api,makeKey,storage,onState=()=>{},namespace='review'}){
    let caseId='',context=null,draft={reason:'',selections:[],bound:null},request=null,pending=false,epoch=0,error='',storageError=false;
    const clone=value=>JSON.parse(JSON.stringify(value));
    const state=()=>({caseId,context,draft:clone(draft),request,pending,error,storageError,
      comparisonRequired:Boolean(context&&draft.bound&&draft.bound.context_sha256!==context.context_sha256)});
    const publish=()=>onState(state());
    const key=id=>`${namespace}:${id}`;
    function save(){
      try{
        if(!storage)throw Error('Unavailable');
        const text=JSON.stringify({draft,request});storage.setItem(key(caseId),text);
        if(storage.getItem(key(caseId))!==text)throw Error('Not retained');storageError=false;
      }catch{storageError=true;error='无法保存本页审核请求，请恢复浏览器存储后再确认。';}
    }
    async function load(id){
      const token=++epoch;
      if(id!==caseId){
        if(caseId)save();caseId=id;context=null;error='';request=null;draft={reason:'',selections:[],bound:null};
        try{const saved=JSON.parse(storage?.getItem(key(id))||'null');if(saved){draft=saved.draft;request=saved.request;}}catch{}
      }
      publish();
      try{
        const current=await api(`/api/catalog/review/cases/${encodeURIComponent(id)}/workflow`);
        if(token!==epoch||caseId!==id)return null;
        context=current;if(!draft.bound||(!draft.reason.trim()&&!draft.selections.length&&!request))draft.bound=clone(current);save();publish();return current;
      }catch(failure){if(token===epoch){context=null;error=`审核依据读取失败：${failure.message}`;publish();}throw failure;}
    }
    function setReason(value){if(pending)return;draft.reason=value;save();if(storageError)publish();}
    function addSelection(selection){
      if(pending||!context)return;
      if(state().comparisonRequired){error='先对照新状态，再选择本次要补充的原文。';publish();return;}
      draft.selections.push(clone(selection));save();publish();
    }
    function removeSelection(index){if(pending)return;draft.selections.splice(index,1);save();publish();}
    function compare(){
      if(pending||request||!context)return;
      if(draft.bound?.file.sha256!==context.file.sha256||draft.bound?.file.file_version_id!==context.file.file_version_id){
        error='原文件版本已改变，保留原稿并重新选择当前文件的原文。';publish();return;
      }
      draft.bound=clone(context);save();error='';publish();
    }
    async function send(original=false,action=null){
      if(pending)return null;
      if(!caseId||!context)throw Error('审核依据尚未加载。');
      if(request&&!original){error='上次决定的结果尚未确认，请先核对原请求；当前草稿会保留。';publish();throw Error(error);}
      if(!request){
        if(state().comparisonRequired)throw Error('先对照当前审核状态。');
        if(!draft.reason.trim())throw Error('请填写本次复核说明。');
        if(!context.allowed_actions.includes(action))throw Error('当前状态不允许这个审核动作。');
        request={caseId,body:{request_id:makeKey(),action,expected_context_sha256:context.context_sha256,
          reason:draft.reason.trim(),reference_selections:action==='RECHECK_PARSE'?draft.selections.map(({page_number,word_start,word_end})=>({page_number,word_start,word_end})):[]}};
      }
      save();if(storageError){request=null;publish();throw Error(error);}
      const submitted=clone(request),token=epoch;pending=true;error='';publish();
      try{
        const result=await api(`/api/catalog/review/cases/${encodeURIComponent(submitted.caseId)}/actions`,submitted.body);
        const saved={draft:{reason:'',selections:[],bound:null},request:null,receipt:result};
        storage.setItem(key(submitted.caseId),JSON.stringify(saved));
        if(token===epoch&&caseId===submitted.caseId){request=null;draft=saved.draft;await load(caseId);}
        return result;
      }catch(failure){
        if(token===epoch&&caseId===submitted.caseId){
          error=`复核未确认：${failure.message}`;
          if([403,404,409,422].includes(failure.status))request=null;
          save();publish();
          if(failure.status===409){try{await load(caseId);}catch{}}
        }
        throw failure;
      }finally{pending=false;publish();}
    }
    function leave(){epoch++;if(caseId)save();context=null;publish();}
    return {load,setReason,addSelection,removeSelection,compare,submit:action=>send(false,action),retry:()=>send(true),leave,state};
  }
  root.CatalogReviewWorkflow={createController};
})(typeof window==='undefined'?globalThis:window);
