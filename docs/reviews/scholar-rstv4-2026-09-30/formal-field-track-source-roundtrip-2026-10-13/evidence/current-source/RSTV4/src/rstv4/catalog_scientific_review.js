(function(root){
  'use strict';
  function sectionChoices(context,draft,nodeId){
    const sections=context?.author_structure?.sections||[];
    const current=Object.entries(draft.section_map).find(([,nodes])=>nodes.includes(nodeId))?.[0]||'';
    return {sections,current,legacy:Boolean(current&&!sections.some(section=>section.id===current))};
  }
  function unresolvedSections(context,draft){
    return draft.node_ids.map(nodeId=>({nodeId,...sectionChoices(context,draft,nodeId)})).filter(item=>item.legacy);
  }
  function createController({api,storage,makeKey,onState=()=>{},namespace='scientific-review'}){
    let manuscriptId='',context=null,draft={node_ids:[],evidence_ids:[],section_map:{},reason:'',bound:null},request=null,pending=false,epoch=0,error='',storageError=false;
    const clone=v=>JSON.parse(JSON.stringify(v));
    const state=()=>({manuscriptId,context,draft:clone(draft),request,pending,error,storageError,
      comparisonRequired:Boolean(context&&draft.bound&&draft.bound.context_sha256!==context.context_sha256),
      unresolvedSections:context?unresolvedSections(context,draft):[]});
    const publish=()=>onState(state()),key=id=>namespace+':'+id;
    function save(){try{if(!storage)throw Error('Unavailable');const value=JSON.stringify({draft,request});storage.setItem(key(manuscriptId),value);if(storage.getItem(key(manuscriptId))!==value)throw Error('Not retained');storageError=false;}catch{storageError=true;error='浏览器无法保存科研复核草稿，请恢复存储后再提交。';}}
    async function load(id){
      const token=++epoch;
      if(id!==manuscriptId){if(manuscriptId)save();manuscriptId=id;context=null;error='';request=null;draft={node_ids:[],evidence_ids:[],section_map:{},reason:'',bound:null};try{const saved=JSON.parse(storage?.getItem(key(id))||'null');if(saved){draft=saved.draft;request=saved.request;}}catch{}}
      publish();
      try{const current=await api(`/api/catalog/manuscripts/${encodeURIComponent(id)}/scientific-review`);if(token!==epoch||id!==manuscriptId)return null;context=current;if(!draft.bound){draft.bound=clone(current);draft.node_ids=current.bindings.nodes.map(row=>row.node_id);draft.evidence_ids=current.bindings.evidence.map(row=>row.evidence_id);draft.section_map={};for(const row of current.bindings.nodes)if(row.section)(draft.section_map[row.section]??=[]).push(row.node_id);}save();publish();return current;}
      catch(failure){if(token===epoch){context=null;error='科研依据读取失败：'+failure.message;publish();}throw failure;}
    }
    function edit(values){if(pending)return;draft={...draft,...clone(values)};save();if(storageError)publish();}
    function selectNode(nodeId,selected){
      if(pending||!context)return false;
      const node=context.nodes.find(row=>row.node_id===nodeId);
      if(!node||(selected&&node.status!=='APPROVED'))return false;
      const ids=new Set(draft.node_ids);if(selected)ids.add(nodeId);else ids.delete(nodeId);
      const map={};for(const [section,nodes] of Object.entries(draft.section_map)){const retained=nodes.filter(id=>ids.has(id));if(retained.length)map[section]=retained;}
      edit({node_ids:[...ids],section_map:map});return true;
    }
    function placeNode(nodeId,sectionId){
      if(pending||!context||!draft.node_ids.includes(nodeId))return false;
      if(sectionId&&!sectionChoices(context,draft,nodeId).sections.some(section=>section.id===sectionId))return false;
      const map={};for(const [section,nodes] of Object.entries(draft.section_map)){const retained=nodes.filter(id=>id!==nodeId);if(retained.length)map[section]=retained;}
      if(sectionId)(map[sectionId]??=[]).push(nodeId);
      edit({section_map:map});return true;
    }
    function compare(){if(pending||request||!context)return;draft.bound=clone(context);save();error='';publish();}
    async function propose(original=false){
      if(pending)return null;
      if(!context)throw Error('科研依据尚未读回。');
      if(request&&!original)throw Error('上次提案结果尚未确认，请先核对原请求。');
      if(!request){if(state().unresolvedSections.length)throw Error('旧章节绑定未匹配当前作者结构，请为所选节点选择真实章节或未放置。');if(state().comparisonRequired)throw Error('请先对照当前依据。');if(!draft.reason.trim())throw Error('请填写重审说明。');request={manuscriptId,body:{request_id:makeKey(),expected_revision:context.manuscript.revision,expected_context_sha256:context.context_sha256,node_ids:draft.node_ids,evidence_ids:draft.evidence_ids,section_map:draft.section_map,reason:draft.reason.trim()}};}
      save();if(storageError)throw Error(error);const submitted=clone(request),submittedDraft=clone(draft),token=epoch;pending=true;error='';publish();
      try{const result=await api(`/api/catalog/manuscripts/${encodeURIComponent(submitted.manuscriptId)}/scientific-review/proposals`,submitted.body);storage.setItem(key(submitted.manuscriptId),JSON.stringify({draft:token===epoch?draft:submittedDraft,request:null}));if(token===epoch){request=null;await load(manuscriptId);}return result;}
      catch(failure){if(token===epoch){error=failure.message;if([403,404,409,422].includes(failure.status))request=null;save();publish();if(failure.status===409){try{await load(manuscriptId);}catch{}}}throw failure;}
      finally{pending=false;publish();}
    }
    async function apply(reviewId){
      if(pending||!context)return null;
      const proposal=context.reviews.find(row=>row.review_id===reviewId);
      if(!proposal?.grant_available||proposal.status!=='PROPOSED')throw Error('尚未收到该提案的真实用户批准记录。');
      const id=manuscriptId,token=epoch;pending=true;publish();
      try{const result=await api(`/api/catalog/manuscripts/${encodeURIComponent(id)}/scientific-review/${encodeURIComponent(reviewId)}/apply`,{});if(token===epoch){draft={node_ids:[],evidence_ids:[],section_map:{},reason:'',bound:null};save();await load(id);}return result;}
      catch(failure){if(token===epoch){error=failure.message;publish();}throw failure;}finally{pending=false;publish();}
    }
    function leave(){epoch++;if(manuscriptId)save();context=null;publish();}
    return {load,edit,selectNode,placeNode,compare,propose:()=>propose(false),retry:()=>propose(true),apply,leave,state};
  }
  root.CatalogScientificReview={createController,sectionChoices};
})(typeof window==='undefined'?globalThis:window);
