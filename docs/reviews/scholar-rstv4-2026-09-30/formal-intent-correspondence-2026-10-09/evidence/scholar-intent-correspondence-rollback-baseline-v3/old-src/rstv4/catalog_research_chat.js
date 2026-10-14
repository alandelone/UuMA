/* Discussion binds to the original object, version and exact UTF-16 selection. */
(function (root) {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clone = value => JSON.parse(JSON.stringify(value));
  const prefix = '/api/catalog/discussion';
  function sourceDestination(context, {catalogBase, studioBase}, reference) {
    const target=context.target, url=new URL(target.module==='STUDIO'?studioBase:catalogBase);
    if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.pathname!=='/')throw new Error('工作台地址不可用。');
    url.search='';url.hash='';
    if(target.module==='STUDIO'){url.searchParams.set('manuscript',target.manuscript_id);url.searchParams.set('view',target.object_kind.startsWith('generated_')?'reading':'structure');}
    else if(target.module==='CATALOG'){url.searchParams.set('view','all');url.searchParams.set('paper',target.paper_id);}
    else{url.searchParams.set('view',target.module==='TRACK'?'track':'fieldkg');if(target.field_id)url.searchParams.set('field',target.field_id);if(target.track_id)url.searchParams.set('track',target.track_id);if(target.snapshot_id)url.searchParams.set('snapshot',target.snapshot_id);}
    url.searchParams.set('discussion',reference.message_id);url.searchParams.set('discussion_scope',reference.scope);url.searchParams.set('discussion_source',String(reference.index));
    if(reference.return_url){const back=new URL(reference.return_url);const allowed=[new URL(catalogBase).origin,new URL(studioBase).origin];if(allowed.includes(back.origin)&&back.pathname==='/'&&!back.username&&!back.password&&!back.hash)url.searchParams.set('discussion_return',back.href);}
    return url.href;
  }
  function sourceReference(search) {
    const params=new URLSearchParams(search), message_id=params.get('discussion'), scope=params.get('discussion_scope'), raw=params.get('discussion_source')||'0', index=Number(raw);
    if(!message_id||message_id.length>200||!scope||scope.length>2200||!/^[0-8]$/.test(raw)||!Number.isInteger(index))return null;
    try{const owner=JSON.parse(scope);if(!Array.isArray(owner)||owner.length!==2||!['CATALOG','FIELDKG','TRACK','STUDIO'].includes(owner[0])||typeof owner[1]!=='string'||!owner[1])return null;}catch{return null;}
    return {message_id,scope,index};
  }
  function sourceReturn(search, {catalogBase,studioBase}) {
    const raw=new URLSearchParams(search).get('discussion_return');if(!raw||raw.length>32768)return null;
    try{const url=new URL(raw), origins=[new URL(catalogBase).origin,new URL(studioBase).origin];return ['http:','https:'].includes(url.protocol)&&origins.includes(url.origin)&&url.pathname==='/'&&!url.username&&!url.password&&!url.hash?url.href:null;}catch{return null;}
  }
  function sourceWithoutReference(href) {
    const url=new URL(href);
    for(const key of ['discussion','discussion_scope','discussion_source','studio_discussion'])url.searchParams.delete(key);
    return url.href;
  }
  function createController({request, storage, namespace, uuid, onChange = () => {}, onLocate}) {
    let serial = 0, historySerial = 0;
    const state = {bound:null, proposed:null, quote:null, content:'', annotation:'', extra:[], pinned:false, allowCrossScope:false, parent:null, pending:null, receipt:null, inspectedReceipt:null, busy:false, status:'选择论文、图谱对象或 Track 内容以开始讨论。', messages:[], annotations:[], historyTarget:null, currentOnly:false, nextBefore:null, nextAnnotationsBefore:null};
    const key = bound => `${namespace}:${bound.context.context_sha256}:${bound.history_message_id||'current'}:${bound.history_source_index||0}`;
    function snapshot() { return clone(state); }
    function emit() { onChange(snapshot()); }
    function save() {
      if (!state.bound) return;
      const draft = {bound:state.bound, quote:state.quote, content:state.content, annotation:state.annotation, extra:state.extra, pinned:state.pinned, allowCrossScope:state.allowCrossScope, parent:state.parent, pending:state.pending};
      try { storage.setItem(key(state.bound), JSON.stringify(draft)); storage.setItem(`${namespace}:active`, JSON.stringify(draft)); }
      catch { state.status='本机草稿保存不可用；当前文字仍保留在窗口中。'; }
    }
    function restore(draft) {
      if (!draft?.bound?.context?.context_sha256) return;
      for (const name of ['bound','quote','content','annotation','extra','pinned','allowCrossScope','parent','pending']) if (name in draft) state[name]=draft[name];
    }
    function protectedDraft() { return !!(state.content || state.annotation || state.quote || state.extra.length || state.pending); }
    function activate(bound, quote = null) {
      save(); state.bound=bound; state.quote=quote; state.content=''; state.annotation=''; state.extra=[]; state.allowCrossScope=false; state.parent=null; state.pending=null; state.receipt=null; state.inspectedReceipt=null; state.proposed=null;
      try { const draft=JSON.parse(storage.getItem(key(bound))); if (draft) restore(draft); } catch { /* use the current in-memory source */ }
      if(quote)state.quote=quote;
      if(bound.continuation){state.parent=bound.continuation;state.bound={...state.bound};delete state.bound.continuation;}
      state.status=bound.history_message_id?'正在使用历史固定来源；发送会保留原版本。':'已选此对象。可拖选下方原文，或直接提问。';
      save(); emit(); void loadHistory();
    }
    function propose(bound, quote = null) {
      if (!state.bound) { activate(bound,quote); return; }
      const same = state.bound.context.context_sha256 === bound.context.context_sha256 && state.bound.history_message_id===bound.history_message_id && state.bound.history_source_index===bound.history_source_index && !quote && !bound.continuation;
      if (same) { state.proposed=null; emit(); return; }
      if (state.pinned || protectedDraft()) {
        state.proposed={bound,quote}; state.status='新选对象已列在下面；当前问题仍绑定原对象，请明确选择。'; emit();
      } else activate(bound,quote);
    }
    async function choose(target, quote = null) {
      const token=++serial;
      try {
        const context=await request(`${prefix}/context`,target);
        if (token!==serial) return;
        if (quote?.text && context.object_text.slice(quote.start,quote.end)!==quote.text) throw new Error('选区与这个版本的原文不一致，请重新选择。');
        propose({context},quote);
      } catch(error) { if(token===serial){state.status=`来源不可用：${error.message}。当前草稿与固定来源仍保留。`;emit();} }
    }
    function compare(choice) {
      if (!state.proposed) return;
      if(choice==='keep'){state.proposed=null;state.pinned=true;state.status='已保留并固定原对象。';save();emit();return;}
      if(choice==='add') {
        const candidate=state.proposed;
        if(state.pending){state.status='先核对原提交，再添加来源。';emit();return;}
        if(state.extra.length>=8){state.status='最多加入 8 个额外固定来源。';emit();return;}
        if(!state.extra.some(item=>item.bound.context.context_sha256===candidate.bound.context.context_sha256)&&candidate.bound.context.context_sha256!==state.bound.context.context_sha256)state.extra.push(candidate);
        state.proposed=null;state.status='已加入明确选择的比较来源；不同研究范围还需要勾选跨范围比较。';save();emit();return;
      }
      const candidate=state.proposed, content=state.content;
      activate(candidate.bound,candidate.quote); if(choice==='use')state.content=content;
      state.status='已明确改用新对象；原对象的草稿与提交记录仍可回查。';save();emit();
    }
    function edit(name,value) {
      if(state.pending){state.status='原提交结果尚待核对，不能改写该请求。';emit();return;}
      if(!['content','annotation','pinned','allowCrossScope'].includes(name))return;
      state[name]=value;save();emit();
    }
    function selectQuote(quote) {
      if(!state.bound||state.pending)return;
      if(quote && state.bound.context.object_text.slice(quote.start,quote.end)!==quote.text){state.status='选区与原文不一致。';emit();return;}
      state.quote=quote;save();emit();
    }
    const selection = (bound,quote,annotation='') => ({target:bound.context.target,expected_context_sha256:bound.context.context_sha256,...(bound.history_message_id?{history_message_id:bound.history_message_id,history_source_index:bound.history_source_index||0}:{}),quote:{...(quote||{text:''}),annotation}});
    async function loadHistory(older=false) {
      const selected=state.historyView?.target||state.bound?.context.target;if(!selected)return;
      const target=clone(selected), token=++historySerial;
      try {
        const result=await request(`${prefix}/history`,{target,limit:30,current_object_only:state.currentOnly,...(older&&state.nextBefore?{before:state.nextBefore}:{}),...(older&&state.nextAnnotationsBefore?{annotations_before:state.nextAnnotationsBefore}:{})});
        if(token!==historySerial || JSON.stringify(target)!==JSON.stringify(state.historyView?.target||state.bound?.context.target))return;
        const merge=(left,right,id)=>[...new Map([...left,...right].map(item=>[item[id],item])).values()].sort((a,b)=>a.seq-b.seq);
        state.messages=merge(older?state.messages:[],result.messages,'message_id');state.annotations=merge(older?state.annotations:[],result.annotations,'annotation_id');
        state.nextBefore=result.next_before;state.nextAnnotationsBefore=result.next_annotations_before;state.historyTarget=target;emit();
      }catch(error){if(token===historySerial){state.status=`历史读取失败：${error.message}。可以重试。`;emit();}}
    }
    async function openHistory(messageId,index=0,continueDiscussion=false,owner=null) {
      if(!state.bound&&!owner)return;
      const token=++serial, scope=owner||state.bound.context.scope_key;
      try {
        const result=await request(`${prefix}/messages/${encodeURIComponent(messageId)}/context?scope=${encodeURIComponent(scope)}`);
        if(token!==serial)return;
        const source=result.sources[index];
        if(!source)throw new Error('这条历史来源不存在。');
        if(continueDiscussion&&!result.conversation?.length)throw new Error('这条问题还未形成可继续的回复或失败记录。');
        const continuation=continueDiscussion?{message_id:messageId,label:result.message.content,scope_key:scope,conversation:result.conversation}:null;
        propose({context:source.context,history_message_id:messageId,history_source_index:index,history_scope:scope,history_request_id:result.message?.request_id,current_source_state:source.current_source_state,...(continuation?{continuation}: {})},source.quote.text?{text:source.quote.text,start:source.quote.start,end:source.quote.end,offset_unit:source.quote.offset_unit}:null);
      }catch(error){if(token===serial){state.status=`原来源回查失败：${error.message}。`;emit();}}
    }
    async function locateSource(messageId,index=0,owner=null) {
      if(!onLocate||(!state.bound&&!owner))return;
      const token=++serial, scope=owner||state.bound.context.scope_key;
      try{
        const result=await request(prefix+'/messages/'+encodeURIComponent(messageId)+'/context?scope='+encodeURIComponent(scope));
        if(token!==serial)return;
        const source=result.sources[index];if(!source)throw new Error('这条历史来源不存在。');
        await onLocate({source,message_id:messageId,index,scope});
      }catch(error){if(token===serial){state.status='原对象定位失败：'+error.message+'。原草稿与历史仍保留。';emit();}}
    }
    function acceptReceipt(receipt) {
      state.receipt=receipt;
      const status=receipt.job?.status;
      if(status==='COMPLETE'||status==='FAILED'||receipt.annotation_id){
        state.pending=null;if(!receipt.annotation_id)state.content='';state.annotation='';
        const parent=receipt.messages?.find(message=>message.actor==='AGENT')||receipt.messages?.find(message=>message.actor==='AUTHOR'&&status==='FAILED');
        if(parent)state.parent={message_id:parent.message_id,label:parent.content,scope_key:parent.scope_key,conversation:[...(receipt.job?.input?.conversation||[]),...receipt.messages]};
        state.status=receipt.annotation_id?'讨论批注已保存。':status==='COMPLETE'?'回复已保存；它是讨论意见。':`回复失败：${receipt.job.error?.detail||'原因未记录'}。原问题与来源已保存；核对原提交不会再次调用模型。`;
      }else state.status=receipt.execution_observation==='LIVE_WORKER'?'原问题已保存，正在生成回复…':'原问题已保存；当前进程未观察到运行中的工作。可核对状态，不能据此认定仍在运行。';
      save();emit();void loadHistory();
    }
    async function send(kind='DISCUSS') {
      if(!state.bound||state.busy)return;
      if(state.pending){await reconcile(true);return;}
      if(kind==='DISCUSS'&&!state.content.trim()){state.status='请先填写问题。';emit();return;}
      if(kind==='ANNOTATE'&&!state.annotation.trim()){state.status='请先填写批注。';emit();return;}
      if(state.extra.some(item=>item.bound.context.scope_key!==state.bound.context.scope_key)&&!state.allowCrossScope&&kind==='DISCUSS'){state.status='这些来源属于不同研究范围，请明确勾选跨范围比较。';emit();return;}
      const source=selection(state.bound,state.quote,state.annotation);
      const historicalCross=state.parent?.conversation.some(message=>[message.context,...message.additional_sources.map(item=>item.context)].some(context=>context.scope_key!==state.bound.context.scope_key));
      if(kind==='DISCUSS'&&historicalCross&&!state.allowCrossScope){state.status='这段历史讨论含不同研究范围的固定来源，请明确勾选跨范围比较。';emit();return;}
      const payload=kind==='ANNOTATE'?{request_id:uuid(),source,comment:state.annotation}:{request_id:uuid(),source,content:state.content,additional_sources:state.extra.map(item=>selection(item.bound,item.quote)),allow_cross_scope:state.allowCrossScope,...(state.parent?{parent_message_id:state.parent.message_id}: {})};
      state.pending={kind,payload,scope:state.bound.context.scope_key};save();await reconcile(true);
    }
    async function reconcile(retry=false) {
      if(!state.pending||state.busy)return;
      const pending=clone(state.pending);state.busy=true;emit();
      try {
        let receipt;
        if(pending.kind==='ANNOTATE'){
          if(!retry){state.status='批注结果待核对；点击“核对原提交”会使用完全相同的请求。';return;}
          receipt=await request(`${prefix}/annotations`,pending.payload);
        }else{
          try { receipt=await request(`${prefix}/requests/${encodeURIComponent(pending.payload.request_id)}?scope=${encodeURIComponent(pending.scope)}`); }
          catch(error){if(error.status===404&&retry)receipt=await request(`${prefix}/messages`,pending.payload);else throw error;}
        }
        if(state.pending?.payload.request_id===pending.payload.request_id)acceptReceipt(receipt);
      }catch(error){
        if(state.pending?.payload.request_id!==pending.payload.request_id)return;
        if([400,409,410,422].includes(error.status)){
          state.receipt={rejected_request:pending,error:error.message};state.pending=null;
          state.status=`原提交未通过：${error.message}。请比较来源，再明确提交。`;
        }else state.status=`提交结果尚未确认：${error.message}。文字与原请求已保留，请核对原提交。`;
        save();emit();
      }finally{state.busy=false;emit();}
    }
    function leave() { ++serial; ++historySerial; state.proposed=null; if(!state.pinned&&!protectedDraft()){save();state.bound=null;state.messages=[];state.annotations=[];state.status='选择此页面的内容以开始讨论。';} else if(state.bound)state.status='当前讨论仍固定在原对象；点击新内容后可明确比较或切换。';emit(); }
    function resetHistory(){state.messages=[];state.annotations=[];state.nextBefore=null;state.nextAnnotationsBefore=null;state.historyTarget=null;emit();}
    function filter(currentOnly){if(state.currentOnly===currentOnly)return;state.currentOnly=currentOnly;resetHistory();void loadHistory();}
    function viewHistory(target,currentOnly=false){if(JSON.stringify(state.historyView?.target)===JSON.stringify(target)&&state.currentOnly===currentOnly)return;state.historyView={target:clone(target)};state.currentOnly=currentOnly;resetHistory();void loadHistory();}
    function removeSource(index){if(!state.pending){state.extra.splice(index,1);save();emit();}}
    function startNew(){if(state.pending)return;state.parent=null;state.status='下一条问题将开始新讨论；原问题、回复和来源仍留在历史中。';save();emit();}
    async function inspectCall(messageId){
      const message=state.messages.find(item=>item.message_id===messageId);if(!message||!state.bound)return;
      const scope=state.bound.context.scope_key;
      try{const receipt=await request(`${prefix}/requests/${encodeURIComponent(message.request_id)}?scope=${encodeURIComponent(scope)}`);if(state.bound?.context.scope_key!==scope)return;state.inspectedReceipt=receipt;emit();}
      catch(error){state.status=`原调用记录不可用：${error.message}。`;emit();}
    }
    async function inspectOrigin(){
      const bound=state.bound;if(!bound?.history_request_id||!bound.history_scope)return;
      try{const receipt=await request(prefix+'/requests/'+encodeURIComponent(bound.history_request_id)+'?scope='+encodeURIComponent(bound.history_scope));if(state.bound!==bound)return;state.inspectedReceipt=receipt;emit();}
      catch(error){if(state.bound===bound){state.status='原讨论记录不可用：'+error.message+'。';emit();}}
    }
    try { restore(JSON.parse(storage.getItem(`${namespace}:active`))); if(state.bound){state.status='已恢复原对象草稿；旧提交会先读取状态。';void loadHistory();if(state.pending)void reconcile(false);} }catch{ /* storage unavailable, preserve memory */ }
    return {snapshot,choose,compare,edit,selectQuote,loadHistory,openHistory,locateSource,send,reconcile,leave,filter,viewHistory,removeSource,startNew,inspectCall,inspectOrigin};
  }

  function createChat({host,request,storage,namespace,uuid=root.crypto.randomUUID.bind(root.crypto),onLocate}) {
    host.innerHTML='<button type="button" data-chat-toggle aria-expanded="false" aria-controls="research-chat-body">Chat · 选择内容以讨论</button><section id="research-chat-body" hidden aria-label="研究讨论"><header><strong>研究讨论</strong><button type="button" data-chat-collapse>收起</button></header><p data-chat-status role="status" aria-live="polite"></p><div data-chat-context></div><label class="chat-pin"><input type="checkbox" name="chat-pin">固定当前对象</label><div data-chat-compare></div><details data-chat-raw><summary>原文与版本 · 可拖选文字</summary><p data-chat-versions></p><pre data-chat-original tabindex="0" aria-label="当前固定对象的完整原文"></pre></details><div data-chat-quote></div><div data-chat-sources></div><label class="chat-cross"><input type="checkbox" name="chat-cross">明确允许比较不同研究范围的所选来源</label><form data-chat-form><label>问题<textarea name="chat-question" maxlength="12000" rows="3" placeholder="针对上方固定对象提问"></textarea></label><label>讨论批注<textarea name="chat-annotation" maxlength="8000" rows="2" placeholder="保留原对象、原文和版本"></textarea></label><footer><button type="button" data-chat-annotate>保存讨论批注</button><button type="submit">发送问题</button><button type="button" data-chat-reconcile hidden>核对原提交</button></footer></form><div data-chat-receipt></div><section aria-label="当前研究范围的讨论历史"><header><strong>讨论与批注历史</strong><label><input type="checkbox" name="chat-filter">只看当前对象</label><button type="button" data-chat-refresh>更新历史</button></header><div data-chat-history></div><button type="button" data-chat-older hidden>更早记录</button></section></section>';
    const find=selector=>host.querySelector(selector), body=find('#research-chat-body'), original=find('[data-chat-original]');
    const conversationBox=host.ownerDocument.createElement('div');conversationBox.setAttribute('data-chat-conversation','');find('[data-chat-form]').before(conversationBox);
    let timer=null;
    function versionText(context){return context.versions.length?context.versions.map(item=>Object.entries(item).map(([k,v])=>`${k}: ${v??'未知'}`).join(' · ')).join('\n'):'此对象无独立文件／解析版本记录；以保存时的内容摘要回查。';}
    function render(state) {
      find('[data-chat-toggle]').textContent=`Chat · ${state.bound?.context.label||'选择内容以讨论'}`;
      find('[data-chat-status]').textContent=state.status;
      find('[data-chat-context]').textContent=state.bound?`${state.bound.context.target.module} / ${state.bound.context.target.object_kind} · ${state.bound.context.label}${state.bound.history_message_id?' · 历史固定来源':''}${state.bound.current_source_state==='OLD_VERSION'?' · 原对象已有新版本；当前保留旧版原文':''}${state.bound.current_source_state==='SOURCE_UNAVAILABLE'?' · 当前对象已不可用，保留历史原文':''}`:'尚未绑定讨论对象。';
      find('[data-chat-origin-controls]')?.remove();
      if(state.bound?.history_request_id){const controls=host.ownerDocument.createElement('div');controls.setAttribute('data-chat-origin-controls','');controls.innerHTML='<button type="button" data-chat-origin-call>查看原讨论与调用记录</button>'+ (onLocate?'<button type="button" data-chat-origin-primary>返回原讨论对象</button>':'');find('[data-chat-context]').after(controls);}
      conversationBox.innerHTML=state.parent?`<p>继续这段讨论 · ${state.parent.conversation.length} 条历史消息 <button type="button" data-chat-new ${state.pending?'disabled':''}>开始新讨论</button></p><details><summary>本轮会带入的问题、回复与固定来源</summary>${state.parent.conversation.map(message=>`<article class="chat-message"><strong>${message.actor==='AUTHOR'?'你':'研究助手 · 讨论意见'}</strong><p>${esc(message.content)}</p>${[message.context,...message.additional_sources.map(item=>item.context)].map(context=>`<details><summary>${esc(context.label)} · ${esc(context.target.module)}</summary><pre>${esc(context.object_text)}</pre><p>${esc(versionText(context))}</p></details>`).join('')}${message.quote.text?`<blockquote>${esc(message.quote.text)}</blockquote>`:''}${message.quote.annotation?`<p>批注：${esc(message.quote.annotation)}</p>`:''}</article>`).join('')}</details>`:'<p>下一条问题将开始新讨论。</p>';
      find('[name="chat-pin"]').checked=state.pinned;
      find('[name="chat-cross"]').checked=state.allowCrossScope;
      find('[name="chat-filter"]').checked=state.currentOnly;
      find('[name="chat-question"]').value=state.content;find('[name="chat-annotation"]').value=state.annotation;
      for(const input of find('[data-chat-form]').querySelectorAll('textarea,button'))input.disabled=state.busy||!!state.pending||!state.bound;
      const reconcile=find('[data-chat-reconcile]');reconcile.hidden=!state.pending;reconcile.disabled=state.busy;
      if(original.textContent!==(state.bound?.context.object_text||''))original.textContent=state.bound?.context.object_text||'';
      find('[data-chat-versions]').textContent=state.bound?versionText(state.bound.context):'';
      let parts=find('[data-chat-parts]');if(!parts){parts=host.ownerDocument.createElement('div');parts.setAttribute('data-chat-parts','');find('[data-chat-raw]').append(parts);}
      const record=state.bound?.context.record, target=state.bound?.context.target;
      const children=target?.module==='CATALOG'&&target.object_kind==='skeleton'?(record.units||[]).map(unit=>({kind:'unit',id:unit.unit_id,label:`${unit.section||'原文'} · ${unit.raw_text.slice(0,90)}`})):target?.module==='CATALOG'&&target.object_kind==='parse'?(record.blocks||[]).map(block=>({kind:'parse_block',id:block.block_id,label:`第 ${block.page_number??'未知'} 页 · ${block.text.slice(0,90)}`})):[];
      parts.innerHTML=children.length?`<details><summary>选择独立原文单元（${children.length}）</summary>${children.map(child=>`<p><button type="button" data-chat-part="${esc(JSON.stringify({...target,object_kind:child.kind,object_id:child.id}))}">${esc(child.label)}</button></p>`).join('')}</details>`:'';
      find('[data-chat-compare]').innerHTML=state.proposed?`<div class="chat-comparison"><strong>新选：${esc(state.proposed.bound.context.label)}</strong><p>当前问题仍来自 ${esc(state.bound.context.label)}。</p><button type="button" data-chat-compare="keep">保留并固定原对象</button><button type="button" data-chat-compare="use">改用新对象并保留问题文字</button><button type="button" data-chat-compare="add">加入比较来源</button></div>`:'';
      find('[data-chat-quote]').innerHTML=state.quote?`<blockquote>${esc(state.quote.text)}</blockquote><p>原文位置 ${state.quote.start}–${state.quote.end}（UTF-16） <button type="button" data-chat-clear-quote>移除选区</button></p>`:'';
      find('[data-chat-sources]').innerHTML=state.extra.map((item,index)=>`<p>比较来源：${esc(item.bound.context.label)} · ${esc(item.bound.context.target.module)} <button type="button" data-chat-remove-source="${index}">移除此来源</button>${item.quote?.text?`<blockquote>${esc(item.quote.text)}</blockquote>`:''}</p>`).join('');
      const history=state.messages.map(message=>`<article class="chat-message"><strong>${message.actor==='AUTHOR'?'你':'研究助手 · 讨论意见'}</strong><span>${esc(message.status)} · ${esc(message.created_at)}</span><p>${esc(message.content)}</p>${message.quote.text?`<blockquote>${esc(message.quote.text)}</blockquote>`:''}${[message.context,...message.additional_sources.map(item=>item.context)].map((context,index)=>`<button type="button" data-chat-history-source="${esc(message.message_id)}" data-chat-source-index="${index}">${esc(context.label)} · 回查当时来源</button>`).join('')}${message.quote.annotation?`<p>批注：${esc(message.quote.annotation)}</p>`:''}${message.actor==='AGENT'||message.status==='AGENT_FAILED'?`<button type="button" data-chat-continue="${esc(message.message_id)}">继续这段讨论</button>`:''}<button type="button" data-chat-call="${esc(message.message_id)}">查看原调用记录</button></article>`).join('');
      const annotations=state.annotations.map(item=>`<article class="chat-message"><strong>讨论批注 · ${esc(item.context.label)}</strong><p>${esc(item.comment)}</p>${item.quote.text?`<blockquote>${esc(item.quote.text)}</blockquote>`:''}<details><summary>批注保存时的原文与版本</summary><pre>${esc(item.context.object_text)}</pre><p>${esc(versionText(item.context))}</p></details></article>`).join('');
      find('[data-chat-history]').innerHTML=history+annotations||'<p>此研究范围尚无讨论或批注。</p>';
      if(onLocate)for(const originalButton of find('[data-chat-history]').querySelectorAll('[data-chat-history-source]')){
        const button=host.ownerDocument.createElement('button');button.type='button';button.textContent='定位原对象';
        button.dataset.chatLocateSource=originalButton.dataset.chatHistorySource;button.dataset.chatSourceIndex=originalButton.dataset.chatSourceIndex;originalButton.after(button);
      }
      find('[data-chat-older]').hidden=!state.nextBefore&&!state.nextAnnotationsBefore;
      const job=state.receipt?.job;
      find('[data-chat-receipt]').textContent=job?`回复状态：${job.status} · 实际模型：${job.model_contract?.actual_model||'未知'} · 契约：${job.model_contract?.prompt_version||job.requested_contract?.prompt_version||'未知'}`:'';
      if(state.inspectedReceipt){const details=host.ownerDocument.createElement('details');details.open=true;const summary=host.ownerDocument.createElement('summary');summary.textContent='原调用记录 · 问题、固定输入、实际响应、契约与错误';const pre=host.ownerDocument.createElement('pre');pre.textContent=JSON.stringify(state.inspectedReceipt,null,2);details.append(summary,pre);find('[data-chat-receipt]').append(details);}
      clearTimeout(timer);
      if(state.pending&&job&&['QUEUED','RUNNING'].includes(job.status)&&state.receipt.execution_observation==='LIVE_WORKER'&&!state.busy)timer=setTimeout(()=>void controller.reconcile(false),2000);
    }
    const controller=createController({request,storage,namespace,uuid,onChange:render,onLocate});render(controller.snapshot());
    function expand(){body.hidden=false;find('[data-chat-toggle]').setAttribute('aria-expanded','true');host.classList.add('expanded');}
    host.addEventListener('click',event=>{
      const target=event.target.closest('button');if(!target)return;
      if(target.hasAttribute('data-chat-toggle')){body.hidden=!body.hidden;host.classList.toggle('expanded',!body.hidden);target.setAttribute('aria-expanded',String(!body.hidden));}
      if(target.hasAttribute('data-chat-collapse')){body.hidden=true;host.classList.remove('expanded');find('[data-chat-toggle]').setAttribute('aria-expanded','false');find('[data-chat-toggle]').focus();}
      if(target.dataset.chatCompare)controller.compare(target.dataset.chatCompare);
      if(target.dataset.chatPart)void controller.choose(JSON.parse(target.dataset.chatPart));
      if(target.hasAttribute('data-chat-clear-quote'))controller.selectQuote(null);
      if(target.dataset.chatRemoveSource!==undefined)controller.removeSource(Number(target.dataset.chatRemoveSource));
      if(target.hasAttribute('data-chat-annotate'))void controller.send('ANNOTATE');
      if(target.hasAttribute('data-chat-reconcile'))void controller.reconcile(true);
      if(target.hasAttribute('data-chat-refresh'))void controller.loadHistory();
      if(target.hasAttribute('data-chat-older'))void controller.loadHistory(true);
      if(target.dataset.chatHistorySource)void controller.openHistory(target.dataset.chatHistorySource,Number(target.dataset.chatSourceIndex));
      if(target.dataset.chatLocateSource)void controller.locateSource(target.dataset.chatLocateSource,Number(target.dataset.chatSourceIndex));
      if(target.hasAttribute('data-chat-origin-call'))void controller.inspectOrigin();
      if(target.hasAttribute('data-chat-origin-primary')){const bound=controller.snapshot().bound;if(bound)void controller.locateSource(bound.history_message_id,0,bound.history_scope);}
      if(target.dataset.chatContinue)void controller.openHistory(target.dataset.chatContinue,0,true);
      if(target.dataset.chatCall)void controller.inspectCall(target.dataset.chatCall);
      if(target.hasAttribute('data-chat-new'))controller.startNew();
    });
    host.addEventListener('input',event=>{if(event.target.name==='chat-question')controller.edit('content',event.target.value);if(event.target.name==='chat-annotation')controller.edit('annotation',event.target.value);});
    host.addEventListener('change',event=>{const name=event.target.name;if(name==='chat-pin')controller.edit('pinned',event.target.checked);if(name==='chat-cross')controller.edit('allowCrossScope',event.target.checked);if(name==='chat-filter')controller.filter(event.target.checked);});
    find('[data-chat-form]').addEventListener('submit',event=>{event.preventDefault();void controller.send();});
    function capture(){const selection=host.ownerDocument.defaultView.getSelection();if(!selection||selection.isCollapsed||!original.contains(selection.anchorNode)||!original.contains(selection.focusNode))return;const range=selection.getRangeAt(0), before=range.cloneRange();before.selectNodeContents(original);before.setEnd(range.startContainer,range.startOffset);const start=before.toString().length,end=start+range.toString().length;controller.selectQuote({text:original.textContent.slice(start,end),start,end,offset_unit:'utf16'});}
    original.addEventListener('mouseup',capture);original.addEventListener('keyup',capture);
    return {...controller,choose:(target,quote,reveal=true)=>{if(reveal)expand();return controller.choose(target,quote);},destroy:()=>clearTimeout(timer)};
  }
  root.RSTV4ResearchChat={createController,createChat,sourceDestination,sourceReference,sourceReturn,sourceWithoutReference};
})(typeof globalThis !== 'undefined' ? globalThis : this);
