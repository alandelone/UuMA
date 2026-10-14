
    (() => {
      const $ = id => document.getElementById(id);
      const escapeHtml = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
      const fields = {
        title:'Name', authors:'Authors', published_year:'Year', doi:'DOI', source:'Source',
        abstract:'Abstract', pdf_status:'PDF status', pdf_count:'PDF files',
        verified_count:'Verified PDFs', review_count:'PDFs to review',
        parse_status:'Parse', parse_count:'Parse runs', reference_count:'References',
        brief_status:'QuickRead', brief_count:'QuickReads',
        skeleton_status:'Skeleton', skeleton_count:'Skeletons',
        review_status:'Review', human_count:'Human cases',
        collection_count:'Collections', created_at:'Created', updated_at:'Last Updated'
      };
      const numericFields = new Set(['published_year','pdf_count','verified_count','review_count','parse_count','reference_count','brief_count','skeleton_count','human_count','collection_count']);
      const statusChoices = {
        pdf_status:['NEEDS_REVIEW','VERIFIED','NO_PDF'],
        parse_status:['NEEDS_HUMAN','PARSED','NOT_STARTED'],
        brief_status:['AVAILABLE','NOT_STARTED'], skeleton_status:['AVAILABLE','NOT_STARTED'],
        review_status:['NEEDS_REVIEW','CLEAR']
      };
      const hiddenDefaults = new Set(['abstract','verified_count','parse_count','brief_count','skeleton_count','human_count','collection_count']);
      const columnOrder = ['title','created_at','published_year','updated_at','authors','doi','source','pdf_status','pdf_count','review_count','parse_status','reference_count','brief_status','skeleton_status','review_status',...Object.keys(fields).filter(key=>!['title','created_at','published_year','updated_at','authors','doi','source','pdf_status','pdf_count','review_count','parse_status','reference_count','brief_status','skeleton_status','review_status'].includes(key))];
      const defaults = Object.keys(fields).map(key=>({key,visible:!hiddenDefaults.has(key),width:key==='title'?340:key==='authors'?200:key==='source'?155:key==='abstract'?260:key.endsWith('_at')?220:132,order:columnOrder.indexOf(key)}));
      let columns;
      try { columns=JSON.parse(localStorage.getItem('rstv4-catalog-columns-v2')) || defaults; } catch { columns=defaults; }
      if(!Array.isArray(columns)||columns.length!==defaults.length||columns.some(c=>!fields[c.key]))columns=defaults;
      let view='overview', collectReturnView='overview', page=1, pageSize=50, result=null, cases=[],selectedCase=null, nextId=3;
      let collectScope=null, overviewData=null, paperQueryToken=0;
      let reviewTotal=0, currentPdfPage=1, currentPdfPages=1,locatedReviewCase=null;
      let currentTextLayout=null, lastSelectedText='';
      let pdfReviewObserver=null, pdfReviewLoadToken=0, pdfReviewLayouts=new Map();
      let latestAnnotations={}, pendingPdfSelection=null, commentSaveTimers={};
      let filter={type:'group',id:1,operator:'and',filters:[{type:'rule',id:2,field:'title',operator:'contains',value:''}]};
      let sorts=[{field:'updated_at',direction:'desc'}];
      const options=(list,current)=>list.map(v=>`<option value="${escapeHtml(v)}" ${v===current?'selected':''}>${escapeHtml(fields[v]||v)}</option>`).join('');
      function saveColumns(){localStorage.setItem('rstv4-catalog-columns-v2',JSON.stringify(columns));}
      function activeColumns(){return columns.filter(c=>c.visible).sort((a,b)=>a.order-b.order);}
      function errorText(error){return error?.message || String(error);}
      async function api(url,body){
        const response=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});
        if(!response.ok){let detail='';try{const data=await response.json();detail=typeof data.detail==='string'?data.detail:'';}catch{}const error=new Error(detail||`Request failed (${response.status})`);error.status=response.status;throw error;}
        return response.json();
      }
      function badge(value){const text=String(value??'—');const kind=/NEEDS|REVIEW/.test(text)?'warn':'';return `<span class="badge ${kind}">${escapeHtml(text)}</span>`;}
      function cell(row,key){
        const value=row[key];
        if(key==='title')return `<button type="button" class="cell-link" data-paper="${escapeHtml(row.paper_id)}">${escapeHtml(value)}</button>${scopeReasons(row.scope_association)}`;
        if((key==='pdf_status'&&value==='NEEDS_REVIEW')||(key==='parse_status'&&value==='NEEDS_HUMAN')||(key==='review_status'&&value==='NEEDS_REVIEW')){
          const kind=key==='parse_status'||(key==='review_status'&&row.human_count&&!row.review_count)?'PARSER':'PDF_IDENTITY';
          return `<button type="button" class="badge warn" data-review-paper="${escapeHtml(row.paper_id)}" data-review-kind="${kind}">${escapeHtml(value)}</button>`;
        }
        if(key.endsWith('_status'))return badge(value);
        if(key==='created_at'||key==='updated_at'){
          const date=value?new Date(value):null;
          return escapeHtml(date&&!Number.isNaN(date.getTime())?new Intl.DateTimeFormat('en-US',{dateStyle:'long',timeStyle:'short'}).format(date):'—');
        }
        return escapeHtml(value??'—');
      }
      function propertyIcon(key){
        if(key.endsWith('_at'))return '◷';
        if(key==='published_year')return '▣';
        if(numericFields.has(key))return '#';
        if(key.endsWith('_status'))return '◆';
        return 'Aa';
      }
      function renderTable(){
        const active=activeColumns();
        document.querySelector('.table-wrap table').style.minWidth=active.reduce((sum,c)=>sum+Math.max(70,Number(c.width)||130),0)+'px';
        $('paper-colgroup').innerHTML=active.map(c=>`<col style="width:${Math.max(70,Number(c.width)||130)}px">`).join('');
        $('paper-head').innerHTML=active.map(c=>`<th scope="col" data-column="${c.key}"><span class="property-icon" aria-hidden="true">${propertyIcon(c.key)}</span>${escapeHtml(fields[c.key])}<span class="resize" data-resize="${c.key}" role="separator" aria-label="Resize ${escapeHtml(fields[c.key])} column"></span></th>`).join('');
        if(!result){$('paper-body').innerHTML=`<tr><td colspan="${active.length}">Loading…</td></tr>`;return;}
        $('paper-body').innerHTML=result.items.length?result.items.map(row=>`<tr>${active.map(c=>`<td title="${escapeHtml(row[c.key]??'')}">${cell(row,c.key)}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${active.length}" class="status-line">No papers match this view.</td></tr>`;
        $('list-count').textContent=`${result.total.toLocaleString()} papers`;
        $('page-info').textContent=`Page ${result.page} · ${result.page_size} per page`;
        $('prev-page').disabled=page<=1;
        $('next-page').disabled=!result.has_more;
      }
      function cleanFilter(node){
        if(node.type==='rule'){
          if(!['is_empty','is_not_empty'].includes(node.operator)&&String(node.value??'').trim()==='')return null;
          return {type:'rule',field:node.field,operator:node.operator,value:node.value};
        }
        const children=node.filters.map(cleanFilter).filter(Boolean);
        return children.length?{type:'group',operator:node.operator,filters:children}:null;
      }
      function queryFilter(){
        const own=cleanFilter(filter);
        const tab=view==='needs_review'?{type:'rule',field:'review_status',operator:'is',value:'NEEDS_REVIEW'}:
          view==='ready'?{type:'rule',field:'brief_status',operator:'is',value:'AVAILABLE'}:null;
        if(!own)return tab;if(!tab)return own;
        return {type:'group',operator:'and',filters:[tab,own]};
      }
      function scopeReasons(association){
        if(!association)return '';
        const labels={CONFIRMED:'明确关联（非科学批准）',CANDIDATE:'候选关联'};
        const reasons=association.reasons.map(reason=>{
          if(reason.kind==='collection')return `采集：${reason.name} · ${reason.discovery_kind} · ${reason.membership_status}${reason.screening?` · 范围筛选 ${reason.screening.category}`:' · 尚无当前范围筛选'}${reason.excluded?' · 此关联已排除':''}${reason.discovered_from_paper_id?` · 引用来自 ${reason.discovered_from_paper_id}`:''}`;
          if(reason.kind==='fieldkg_build')return `明确选入 FieldKG Build ${reason.build_id} · 论文版本 ${reason.paper_version_id} · Skeleton ${reason.skeleton_id}`;
          if(reason.kind==='adopted_snapshot')return `Track 已采用 Snapshot v${reason.snapshot_version} · ${reason.snapshot_id} · 论文版本 ${reason.paper_version_id}`;
          return `研究节点 ${reason.node_id} · Evidence ${reason.evidence_id}`;
        });
        return `<details style="white-space:normal;overflow-wrap:anywhere"><summary>${escapeHtml(association.excluded?'已排除':labels[association.association_status])} · ${reasons.length.toLocaleString()} 条归属</summary><ul>${reasons.map(reason=>`<li>${escapeHtml(reason)}</li>`).join('')}</ul></details>`;
      }
      async function loadPapers(){
        const token=++paperQueryToken;
        $('list-count').textContent='Loading papers…';
        try{
          const scope=RSTV4Overview.scopeFromUrl(location.href);
          const loaded=await api('/api/catalog/papers/query',{scope,filter:queryFilter(),sorts,page,page_size:pageSize});
          if(token!==paperQueryToken)return;
          result=loaded;renderTable();
          const banner=$('scope-literature');banner.hidden=!loaded.scope;
          if(loaded.scope)banner.innerHTML=`<strong>${escapeHtml(loaded.scope.title)} · 范围文献</strong> · ${loaded.scope.paper_count.toLocaleString()} 篇唯一论文 · ${loaded.scope.excluded_count.toLocaleString()} 篇已排除 <button type="button" id="toggle-scope-excluded">${scope.include_excluded?'隐藏已排除':'查看已排除'}</button> <a href="?view=overview" data-research-nav>返回研究总览</a>${loaded.scope.unavailable_sources.length?`<p>另有 ${loaded.scope.unavailable_sources.length.toLocaleString()} 个快照来源无法核实；这些来源未计入数量，也未用当前图谱代替。</p>`:''}`;
        }
        catch(error){if(token!==paperQueryToken)return;result=null;$('scope-literature').hidden=true;$('list-count').textContent='Could not load papers';$('paper-body').innerHTML=`<tr><td colspan="${activeColumns().length}" class="error">${escapeHtml(errorText(error))}</td></tr>`;}
      }
      async function loadSummary(){
        try{const s=await api('/api/catalog/summary');reviewTotal=s.pdf_review_cases+s.parser_review_cases;
          $('review-banner').hidden=['overview','review_queue','collect'].includes(view)||!reviewTotal;
          $('overview-total').textContent=s.papers.toLocaleString();
          $('banner-count').textContent=`${reviewTotal.toLocaleString()} to review`;
          $('pdf-review-stat').textContent=`PDF 身份 · ${s.pdf_review_cases.toLocaleString()}`;
          $('parser-review-stat').textContent=`解析质量 · ${s.parser_review_cases.toLocaleString()}`;}
        catch{$('review-banner').hidden=true;}
      }
      function overviewRow(level,node,parent,title,type,status,extra={},expandable=false){
        const safe=escapeHtml(title),parentAttr=parent?` data-parent="${escapeHtml(parent)}"`:'';
        const name=level==='paper'?`<a class="overview-manuscript" data-manuscript-id="${escapeHtml(extra.manuscript_id)}" data-track-id="${escapeHtml(extra.track_id)}">${safe} ↗</a>`:level==='track'?`<a class="overview-title overview-manuscript" href="${escapeHtml(researchNavigationUrl('track',extra.field_id,extra.track_id))}" data-research-nav title="${safe}">${safe} ↗</a>`:`<span class="overview-title" title="${safe}">${safe}</span>`;
        const toggle=expandable?`<button type="button" class="overview-toggle" data-toggle-node="${escapeHtml(node)}" aria-label="收起 ${safe}" aria-expanded="true">⌄</button>`:'<span class="overview-toggle-spacer"></span>';
        const icons={field:'◇',topic:'◈',track:'↗',question:'?',paper:'▧'};
        const paperCount=level==='paper'?'<span class="overview-paper-tag">写作稿件</span>':extra.literature_url?`<a class="overview-paper-count" data-research-nav href="${escapeHtml(extra.literature_url)}" aria-label="查看 ${safe} 的 ${extra.paper_count} 篇关联论文"><span class="count-icon" aria-hidden="true">▤</span>${Number(extra.paper_count).toLocaleString()}${extra.unavailable_count?'＋待核实':''}</a>`:`<button type="button" class="overview-paper-count" data-overview-papers="${safe}" aria-label="查看 ${safe} 的关联论文"><span class="count-icon" aria-hidden="true">▤</span>—</button>`;
        const collect=(level==='topic'||level==='track')?`<button type="button" class="overview-collect" data-collect-scope="${level}" data-collect-field="${escapeHtml(extra.field||'')}" data-collect-topic="${escapeHtml(extra.topic||'')}" data-collect-track="${escapeHtml(extra.track||'')}" data-collect-field-id="${escapeHtml(extra.field_id||'')}" data-collect-topic-id="${escapeHtml(extra.topic_id||'')}" data-collect-track-id="${escapeHtml(extra.track_id||'')}">＋ 采集</button>`:'';
        const entityAttr=level==='track'?` data-track-id="${escapeHtml(extra.track_id||'')}"`:'';
        const state=extra.collection_id?`<button type="button" class="overview-status" data-collection-id="${escapeHtml(extra.collection_id)}" aria-label="查看 ${safe} 的采集详情">${escapeHtml(status||'—')} ↗</button>`:`<span class="overview-status">${escapeHtml(status||'—')}</span>`;
        const edit=['field','topic','track'].includes(level)?`<button type="button" data-research-operation="EDIT_${level.toUpperCase()}" data-research-key="${escapeHtml(node)}" aria-label="修改 ${safe}">编辑</button>`:'';
        const add=level==='field'?`<a href="${escapeHtml(researchNavigationUrl('fieldkg',extra.field_id))}" data-research-nav>FieldKG ↗</a><button type="button" data-research-operation="CREATE_TOPIC" data-research-key="${escapeHtml(node)}">＋ Topic</button><button type="button" data-research-operation="LINK_TOPIC" data-research-key="${escapeHtml(node)}">关联 Topic</button>`:level==='topic'?`<button type="button" data-research-operation="CREATE_TRACK" data-research-key="${escapeHtml(node)}">＋ Track</button>`:'';
        return `<div class="overview-row" data-level="${level}" data-node="${escapeHtml(node)}"${parentAttr}${entityAttr} role="treeitem" tabindex="-1" aria-label="${safe}" aria-level="${extra.depth}"${expandable?' aria-expanded="true"':''}><div class="overview-name">${toggle}<span class="overview-type" aria-hidden="true">${icons[level]}</span>${name}<span class="overview-caption">${type}</span>${edit||add?`<span class="overview-structure">${edit}${add}</span>`:''}</div>${paperCount}<div class="overview-right">${state}${collect}</div></div>`;
      }
      function collectionStatus(collection, jobs){
        if(!collection)return '尚无采集';
        const active=jobs.filter(job=>job.collection_id===collection.collection_id);
        const counts=new Map(active.map(job=>[job.status,job.count]));
        const pending=['WAITING_DEPENDENCY','READY','RUNNING','RETRY_WAIT','RESOURCE_WAIT'].reduce((sum,key)=>sum+(counts.get(key)||0),0);
        if(collection.status==='PAUSED')return `已暂停 · ${pending} 项待处理`;
        if(collection.status==='COMPLETED_CURRENT_FRONTIER')return '当前范围已完成';
        if(pending)return `采集中 · ${pending} 项待处理`;
        if(counts.get('NEEDS_HUMAN'))return `待人工核对 · ${counts.get('NEEDS_HUMAN')} 项`;
        if(counts.get('FAILED_TERMINAL'))return `有失败任务 · ${counts.get('FAILED_TERMINAL')} 项`;
        const labels={ACTIVE:'已启动',PAUSED:'已暂停',COMPLETED_CURRENT_FRONTIER:'当前范围已完成'};
        return `${labels[collection.status]||collection.status} · ${active.reduce((sum,job)=>sum+job.count,0)} 项`;
      }
      async function loadResearchOverview(captureCurrent=true){
        const token=++overviewLoadToken;
        try{
          const data=await api('/api/catalog/research-overview');
          if(token!==overviewLoadToken)return;
          overviewData=data;
          overviewList.load(data,captureCurrent);
          if(!data.fields.length){
            $('overview-tree').innerHTML=overviewDemo;
            document.querySelector('.overview-note span').textContent='尚无真实 Field · 下方是只读布局示例。点击「＋ Field」建立自己的研究结构。';
            return;
          }
          document.querySelector('.overview-note span').textContent='真实研究结构 · 文献按唯一论文去重，父级取所属范围并集；明确关联与候选分别说明。写作 Paper 属于 Track。';
        }catch(error){if(token===overviewLoadToken)document.querySelector('.overview-note span').textContent=`研究结构读取失败：${errorText(error)}`;}
      }
      const overviewDemo=$('overview-tree').innerHTML;
      let overviewLoadToken=0;
      const overviewList=RSTV4Overview.createList({tree:$('overview-tree'),storage:localStorage,location,history,viewport:window,
        renderRow:row=>{
          const {level,record,field,topic,track}=row;
          const scope=RSTV4Overview.literatureScope(row);
          const count=scope?overviewData.literature_counts?.find(item=>item.kind===scope.kind&&item.field_id===scope.field_id&&item.object_id===scope.object_id):null;
          const latest=level==='track'?overviewData.collections.find(c=>c.track_id===track.track_id):level==='topic'?overviewData.collections.find(c=>c.field_id===field.field_id&&(c.topic_id===topic.topic_id||(!c.topic_id&&overviewData.tracks.some(t=>t.track_id===c.track_id&&t.primary_topic_id===topic.topic_id)))):null;
          const status=level==='field'?'研究领域':level==='question'?record.status:level==='paper'?(record.needs_scientific_review?'需科学复核':record.workflow_stage||'阶段未知'):collectionStatus(latest,overviewData.collection_jobs);
          return overviewRow(level,row.key,row.parent,row.title,{field:'Field',topic:'Topic',track:'Track',question:'Research Question',paper:'Paper'}[level],status,
            {...record,field:field.name,topic:topic?.name||'',track:track?.title||'',field_id:field.field_id,topic_id:topic?.topic_id,track_id:track?.track_id,collection_id:latest?.collection_id,depth:row.depth,literature_url:count?RSTV4Overview.literatureUrl(row,location.href):null,paper_count:count?.paper_count,unavailable_count:count?.unavailable_count},row.expandable);
        }});
      let researchDraftNamespace;
      try{researchDraftNamespace=sessionStorage.getItem('rstv4-research-tab-v1');if(!researchDraftNamespace){researchDraftNamespace=crypto.randomUUID();sessionStorage.setItem('rstv4-research-tab-v1',researchDraftNamespace);}}
      catch{researchDraftNamespace=crypto.randomUUID();}
      const researchChat=RSTV4ResearchChat.createChat({host:$('research-chat'),request:api,storage:localStorage,namespace:`rstv4-chat-v1:${location.origin}:${researchDraftNamespace}`,onLocate:locateDiscussionSource});
      const researchEditor=RSTV4Overview.createEditor({dialog:$('research-editor'),storage:localStorage,getData:()=>overviewData,escapeHtml,draftNamespace:researchDraftNamespace,
        onSaved:()=>loadResearchOverview(),fetchAction:async body=>{
          const response=await fetch('/api/catalog/research-actions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
          const result=await response.json();
          if(!response.ok){const error=new Error(typeof result.detail==='string'?result.detail:'请检查必填内容与研究类型。');error.status=response.status;throw error;}
          return result;
        }});
      const researchWorkspaces=RSTV4ResearchWorkspaces.createWorkspace({host:$('research-workspace'),dialog:$('fieldkg-action'),storage:localStorage,location,history,draftNamespace:researchDraftNamespace,
        overviewCapture:()=>overviewList.capture(),returnOverview:()=>setView('overview'),openPaper,selectDiscussion:(target,reveal=true)=>researchChat.choose(target,null,reveal),
        request:async(url,body)=>{
          const response=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});
          const result=await response.json();
          if(!response.ok){const error=new Error(typeof result.detail==='string'?result.detail:'请核对必填内容与固定对象。');error.status=response.status;throw error;}
          return result;
        }});
      const discussionApps={catalogBase:location.origin+'/',studioBase:'http://127.0.0.1:3000/'};
      function updateDiscussionBack(){
        document.querySelector('[data-discussion-back]')?.remove();
        const destination=RSTV4ResearchChat.sourceReturn(location.search,discussionApps);if(!destination)return;
        const link=document.createElement('a');link.href=destination;link.textContent='返回原讨论页面';link.className='research-link';link.dataset.discussionBack='';$('research-chat').prepend(link);
      }
      function highlightDiscussionSource(context){
        const target=context.target;
        document.querySelectorAll('.discussion-selected').forEach(el=>el.classList.remove('discussion-selected'));
        if(['FIELDKG','TRACK'].includes(target.module))return researchWorkspaces.locateTarget(target);
        if(target.module!=='CATALOG'||new URL(location.href).searchParams.get('paper')!==target.paper_id)return false;
        const elements=[...$('paper-drawer').querySelectorAll('[data-discussion-section],[data-discussion-target]')];
        const exact=elements.find(el=>{const value=JSON.parse(el.dataset.discussionSection||el.dataset.discussionTarget);return value.object_kind===target.object_kind&&value.object_id===target.object_id&&(value.part||null)===(target.part||null);});
        if(!exact)return false;
        exact.classList.add('discussion-selected');exact.setAttribute('tabindex','-1');exact.scrollIntoView({block:'center',behavior:'instant'});exact.focus();return true;
      }
      async function restoreDiscussionLink(){
        updateDiscussionBack();
        const reference=RSTV4ResearchChat.sourceReference(location.search);if(!reference)return;
        await researchChat.openHistory(reference.message_id,reference.index,false,reference.scope);
        const state=researchChat.snapshot(),context=state.proposed?.bound.context||state.bound?.context;
        if(context)highlightDiscussionSource(context);
      }
      async function locateDiscussionSource(reference){
        if(view==='overview')overviewList.capture();
        const destination=RSTV4ResearchChat.sourceDestination(reference.source.context,discussionApps,{...reference,return_url:location.href});
        if(new URL(destination).origin!==location.origin){location.assign(destination);return;}
        history.pushState({},'',destination);await setView(viewFromUrl(),false);
        updateDiscussionBack();
        highlightDiscussionSource(reference.source.context);
        await researchChat.openHistory(reference.message_id,reference.index,false,reference.scope);
      }
      function researchNavigationUrl(next,fieldId,trackId){
        const url=new URL(location.href);url.searchParams.set('view',next);
        if(fieldId)url.searchParams.set('field',fieldId);else url.searchParams.delete('field');
        if(trackId)url.searchParams.set('track',trackId);else url.searchParams.delete('track');
        url.searchParams.delete('snapshot');url.searchParams.delete('research_object');return url.href;
      }
      function viewFromUrl(){
        const name=new URLSearchParams(location.search).get('view');
        return name==='review'?'review_queue':
          ['all','needs_review','ready','collect','overview','fieldkg','track','scientific_review'].includes(name)?name:'overview';
      }
      function setView(next,syncUrl=true){
        paperQueryToken++;
        scientificReview.leave();
        reviewWorkflow.leave();
        researchChat.leave();
        if(view==='overview')overviewList.capture();
        view=next;page=1;document.querySelectorAll('.view').forEach(b=>b.classList.toggle('active',b.dataset.view===next));
        $('view-label').textContent=document.querySelector(`.view[data-view="${next}"]`)?.textContent||({fieldkg:'知识图谱',track:'Track 工作面',collect:'新建采集',scientific_review:'科学依据复核'}[next])||'研究总览';
        $('view-menu').hidden=true;$('view-trigger').setAttribute('aria-expanded','false');
        for(const panel of ['filter','sort','columns']){$(panel+'-panel').hidden=true;document.querySelector(`[data-panel="${panel}"]`).classList.remove('active');}
        document.querySelector('.tools').hidden=['overview','review_queue','collect','fieldkg','track','scientific_review'].includes(next);
        $('open-collect').hidden=true;
        $('review-banner').hidden=['overview','review_queue','collect','fieldkg','track','scientific_review'].includes(next)||!reviewTotal;
        $('overview').hidden=next!=='overview';
        $('library').hidden=['overview','review_queue','collect','fieldkg','track','scientific_review'].includes(next);
        $('review').hidden=next!=='review_queue';$('collect').hidden=next!=='collect';
        $('research-workspace').hidden=!['fieldkg','track','scientific_review'].includes(next);
        $('paper-drawer').hidden=true;
        collectionDetailToken++;collectionDetails=null;
        researchWorkspaces.cancelLoad();
        for(const link of document.querySelectorAll('[data-workspace-nav]')){
          const url=new URL(link.href),target=url.searchParams.get('view')||'overview';
          const current=new URL(location.href);
          if(target==='fieldkg'&&current.searchParams.get('field'))url.searchParams.set('field',current.searchParams.get('field'));
          if(current.searchParams.get('overview_state'))url.searchParams.set('overview_state',current.searchParams.get('overview_state'));
          link.href=url.href;link.setAttribute('aria-current',target===next||(target==='overview'&&['track','scientific_review'].includes(next))?'page':'false');
        }
        document.title=next==='overview'?'研究总览 · Paper Catalog':next==='review_queue'?'核对原文 · Paper Catalog':next==='collect'?'新建采集 · Paper Catalog':next==='scientific_review'?'科学依据复核 · Paper Catalog':'Paper Catalog';
        if(syncUrl){
          const url=new URL(location.href);
          if(next==='overview')url.searchParams.delete('view');
          else url.searchParams.set('view',next==='review_queue'?'review':next);
          if(next!=='review_queue')url.searchParams.delete('case');
          history.pushState({},'',url);
        }
        if(next==='collect'){updateCollectPreview();return Promise.resolve();}
        if(next==='scientific_review')return scientificReview.load(new URL(location.href).searchParams.get('manuscript')||'');
        if(next==='overview')return loadResearchOverview(false);
        if(['fieldkg','track'].includes(next))return researchWorkspaces.show(next);
        if(next==='review_queue')return loadCases();
        return loadPapers().then(()=>{const paper=new URL(location.href).searchParams.get('paper');if(paper)return openPaper(paper);});
      }
      function toggleOverviewNode(nodeId){
        if(overviewList.find(nodeId)){overviewList.toggle(nodeId);return;}
        const row=document.querySelector(`.overview-row[data-node="${nodeId}"]`);
        if(!row)return;
        const open=row.getAttribute('aria-expanded')!=='true';
        row.setAttribute('aria-expanded',String(open));
        const toggle=row.querySelector('.overview-toggle');
        toggle.setAttribute('aria-expanded',String(open));
        toggle.setAttribute('aria-label',`${open?'收起':'展开'} ${row.querySelector('.overview-title').textContent}`);
        const rows=[...document.querySelectorAll('.overview-tree .overview-row')];
        for(const child of rows){
          let parent=child.dataset.parent,visible=true;
          while(parent){
            const ancestor=rows.find(item=>item.dataset.node===parent);
            if(!ancestor||ancestor.getAttribute('aria-expanded')==='false'){visible=false;break;}
            parent=ancestor.dataset.parent;
          }
          child.hidden=!visible;
        }
      }
      function openOverviewPaperInfo(scope){
        const drawer=$('paper-drawer');drawer.hidden=false;
        drawer.innerHTML=`<div class="drawer-head"><div><span class="eyebrow">Research overview</span><h2>${escapeHtml(scope)} · 关联论文</h2></div><button type="button" id="close-paper" aria-label="Close paper details">✕</button></div>`+
          `<p class="status-line">${overviewData?.fields.length?'这是实际研究结构，':'此行是只读研究结构示意，'}尚未建立目录论文与该层级的关联，因此没有可确认的论文数。写作稿件与目录论文分别记录。</p>`+
          '<button type="button" id="overview-open-catalog">打开现有 Paper Catalog →</button>';
      }
      let collectionDetailToken=0,collectionDetails=null;
      const collectionJobLabels={WAITING_DEPENDENCY:'等待前置任务',READY:'待执行',RUNNING:'执行中',RETRY_WAIT:'等待重试',RESOURCE_WAIT:'等待资源',NEEDS_HUMAN:'待人工处理',SUCCEEDED:'已完成',SKIPPED:'已复用／跳过',FAILED_TERMINAL:'失败'};
      const collectionStageLabels={RESOLVE_SEED:'身份解析',SEARCH_LITERATURE:'文献检索',SCREEN:'范围筛选',LOCATE_PDF:'获取 PDF',PARSE_PDF:'PDF 解析',REFERENCE_LOOKUP:'引用解析',QUICK_READ:'快速阅读',SKELETON:'Skeleton',ASSESSMENT:'评估'};
      function collectionTime(value){const date=new Date(value);return value&&!Number.isNaN(date.getTime())?new Intl.DateTimeFormat('zh-CN',{dateStyle:'medium',timeStyle:'medium'}).format(date):'未记录';}
      async function openCollectionDetails(collectionId, demoName='',offset=0){
        const drawer=$('paper-drawer');drawer.hidden=false;
        paperLoadToken++;
        const token=++collectionDetailToken;
        if(!collectionId){
          collectionDetails=null;
          drawer.innerHTML=`<div class="drawer-head"><div><span class="eyebrow">Collection / Example</span><h2>${escapeHtml(demoName||'采集进度')}</h2></div><button type="button" id="close-paper" aria-label="关闭采集详情">✕</button></div>`+
            '<p class="status-line">这是总览的流程示意，当前没有实际 Collection 或下载任务。正式开始采集后会返回原 Topic／Track；点击右侧状态可在这里看任务数、最近活动及需要处理的项目。</p>'+
            '<div class="section"><h3>怎样确认采集在跑？</h3><p>查看 READY／RUNNING／SUCCEEDED 等任务数，通过总览上方的「更新状态」读取最新记录。实时 worker 心跳将在正式运行页接入。</p></div>';
          return;
        }
        const previous=offset&&collectionDetails?.collection.collection_id===collectionId?collectionDetails.jobs:[];
        drawer.innerHTML='<div class="drawer-head"><h2>读取采集详情…</h2><button type="button" id="close-paper" aria-label="关闭采集详情">✕</button></div>';
        try{
          const data=await api(`/api/catalog/collections/${encodeURIComponent(collectionId)}?offset=${offset}`);
          if(token!==collectionDetailToken||drawer.hidden)return;
          data.jobs=[...previous,...data.jobs];collectionDetails=data;
          renderCollectionDetails(data);
          await collectionProgress.load(collectionId);
        }catch(error){if(token===collectionDetailToken&&!drawer.hidden){collectionDetails=null;drawer.innerHTML=`<div class="drawer-head"><h2>采集详情读取失败</h2><button type="button" id="close-paper" aria-label="关闭采集详情">✕</button></div><p class="error">${escapeHtml(errorText(error))}</p><button type="button" data-refresh-collection="${escapeHtml(collectionId)}">重新读取</button>`;}}
      }
      function renderCollectionDetails(data){
        const drawer=$('paper-drawer'),collection=data.collection;
        drawer.innerHTML=`<div class="drawer-head"><div><span class="eyebrow">Collection / ${escapeHtml(collection.status)}</span><h2>${escapeHtml(collection.name)}</h2><span class="muted">${escapeHtml(collection.collection_id)}</span></div><button type="button" id="close-paper" aria-label="关闭采集详情">✕</button></div>`+
          `<p class="status-line">${data.counts.papers} 篇论文 · ${data.counts.jobs} 项任务 · 本次读取 ${escapeHtml(collectionTime(data.observed_at))}</p><p id="collection-action-feedback" aria-live="polite"></p>`+
          `<div class="section"><button type="button" data-collection-control="${collection.status==='PAUSED'?'resume':'pause'}">${collection.status==='PAUSED'?'继续采集':'暂停采集'}</button> <button type="button" data-refresh-collection="${escapeHtml(collection.collection_id)}">↻ 更新状态</button><p>暂停后停止领取新任务，正在执行的任务会完成当前步骤。待执行表示任务还在等待处理服务领取。</p></div>`+
          '<div id="collection-progress-panel"></div>'+
          `<div class="section"><h3>处理阶段</h3>${data.stages.map(stage=>`<div class="item">${escapeHtml(collectionStageLabels[stage.job_type]||stage.job_type)} · ${escapeHtml(collectionJobLabels[stage.status]||stage.status)} · ${stage.count} 项</div>`).join('')||'<p>尚无任务。</p>'}</div>`+
          `<div class="section"><h3>任务与需要处理的项目</h3>${data.jobs.map(job=>`<div class="item collection-task"><strong>${escapeHtml(collectionStageLabels[job.job_type]||job.job_type)} · ${escapeHtml(collectionJobLabels[job.status]||job.status)}</strong><p>${escapeHtml(job.job_id)} · 已尝试 ${job.attempts} 次</p>${job.paper_id?`<button type="button" data-paper="${escapeHtml(job.paper_id)}">查看 Catalog 论文</button>`:''}${job.last_error_detail?`<p class="error">${escapeHtml(job.last_error_code)}：${escapeHtml(job.last_error_detail)}</p>`:''}${job.status==='RUNNING'?`<p>${job.lease_state==='OBSERVED_ACTIVE'?'处理服务最近有活动':'处理状态未更新，请检查处理服务'} · 最近更新 ${escapeHtml(collectionTime(job.updated_at))}</p>`:''}${['RETRY_WAIT','RESOURCE_WAIT','FAILED_TERMINAL'].includes(job.status)?`<button type="button" data-retry-collection-job="${escapeHtml(job.job_id)}">重试此步骤</button>`:''}${job.status==='NEEDS_HUMAN'?'<p>需要先处理人工审核；此处不会自动确认或重跑。</p><button type="button" data-open-collection-review>打开审核队列</button>':''}</div>`).join('')}${data.has_more?`<button type="button" data-more-collection="${escapeHtml(collection.collection_id)}" data-offset="${data.offset+data.limit}">更多任务</button>`:''}</div>`+
          `<div class="section"><h3>最近执行记录</h3>${data.recent_attempts.map(attempt=>`<div class="item">${escapeHtml(attempt.status)} · ${escapeHtml(attempt.worker_id)}<p>${escapeHtml(collectionTime(attempt.started_at))} → ${escapeHtml(attempt.completed_at?collectionTime(attempt.completed_at):'进行中')}</p></div>`).join('')||'<p>尚无执行记录。任务在等待处理服务领取。</p>'}</div>`+
          (data.history.length>1?`<div class="section"><h3>同一 ${collection.track_id?'Track':'Topic／Field'} 的采集记录</h3>${data.history.map(item=>`<div class="item"><button type="button" data-collection-id="${escapeHtml(item.collection_id)}">${escapeHtml(item.name)} · ${escapeHtml(item.status)}</button></div>`).join('')}</div>`:'');
      }
      async function controlCollection(button,action,jobId){
        const data=collectionDetails;if(!data)return;
        const token=collectionDetailToken,id=data.collection.collection_id;
        const job=data.jobs.find(item=>item.job_id===jobId);
        const body=jobId?{expected_fencing_token:job?.fencing_token,expected_status:job?.status,expected_updated_at:job?.updated_at}:{expected_revision:data.collection.revision};
        button.disabled=true;
        try{
          await api(`/api/catalog/collections/${encodeURIComponent(id)}/${jobId?`jobs/${encodeURIComponent(jobId)}/retry`:action}`,body);
          if(token===collectionDetailToken){await openCollectionDetails(id);loadResearchOverview();}
        }catch(error){if(token===collectionDetailToken&&$('collection-action-feedback'))$('collection-action-feedback').textContent=`处理失败：${errorText(error)}。请更新状态后再操作。`;}
        finally{button.disabled=false;}
      }
      function openCollectFor(button){
        if(collectController.state().pending)return;
        collectController.begin();
        collectReturnView='overview';
        collectScope={level:button.dataset.collectScope,field:button.dataset.collectField||'',topic:button.dataset.collectTopic||'',track:button.dataset.collectTrack||'',fieldId:button.dataset.collectFieldId||'',topicId:button.dataset.collectTopicId||'',trackId:button.dataset.collectTrackId||'',returnNode:button.closest('.overview-row')?.dataset.node};
        $('collect-scope').textContent=[collectScope.field,collectScope.topic,collectScope.track].filter(Boolean).join(' / ');
        collectPaperPicker.setScope({field_id:collectScope.fieldId,topic_id:collectScope.topicId||null,track_id:collectScope.trackId||null});
        $('collect-paper-search').value='';setView('collect');window.scrollTo(0,0);collectPaperPicker.load('').catch(()=>{});
      }
      let collectStorage=null;try{collectStorage=sessionStorage;}catch{}
      const collectController=CatalogCollections.createController({api,makeKey:()=>crypto.randomUUID(),storage:collectStorage,requireDurableRequest:true,
        onState:state=>{
          if(state.message)$('collect-feedback').textContent=state.message;
          collectPaperPicker.setLocked(state.pending);
          $('collect-start').disabled=state.pending||Boolean(state.storageProblem)||Boolean(collectPaperPicker.state().storageProblem)||!collectScope?.fieldId||!(collectScope?.topicId||collectScope?.trackId);
          $('collect-check').disabled=state.pending;$('collect-back').disabled=state.pending;
          for(const input of document.querySelectorAll('[data-collect-input],#collect-bib-file'))input.disabled=state.pending;
          const counts=state.preview?.counts;
          $('collect-catalog-count').textContent=counts?counts.catalog_papers:'待检查';
          $('collect-reuse-count').textContent=counts?counts.reusable_pdfs:'待检查';
          $('collect-review-count').textContent=counts?counts.needs_review:'待检查';
        },onStarted:async collection=>{
          if(view!=='collect')return;
          const node=collectScope?.returnNode;await setView(collectReturnView);
          const row=[...$('overview-tree').querySelectorAll('.overview-row')].find(item=>item.dataset.node===node);
          row?.focus({preventScroll:true});row?.scrollIntoView({block:'nearest',behavior:'instant'});
          document.querySelector('.overview-note span').textContent=`已创建「${collection.name}」，${collection.counts.jobs} 项任务已入队。点击原 Topic／Track 右侧状态查看进度。`;
        }});
      const collectPaperPicker=CatalogCollections.createPaperPicker({api,storage:collectStorage,onState:renderCollectPaperPicker,onSelection:()=>{if(view==='collect')updateCollectPreview();}});
      function renderCollectPaperPicker(state){
        const chosen=new Set(state.selected.map(row=>row.paper_id));
        const metadata=row=>[row.doi||'未记录 DOI',row.published_year||'',...(row.authors||[]).slice(0,3)].filter(Boolean).join(' · ');
        $('collect-paper-results').innerHTML=state.pending?'<p role="status">正在读取 Catalog…</p>':state.rows.map(row=>`<div class="item collection-paper-row"><label><input type="checkbox" name="catalog_paper_ids" data-collect-paper="${escapeHtml(row.paper_id)}" ${chosen.has(row.paper_id)?'checked':''} ${state.locked?'disabled':''}><strong>${escapeHtml(row.title)}</strong></label><p>${escapeHtml(metadata(row))}</p><small>${row.quarantined?'目录隔离中':row.registered_review_files?'文件身份有待审记录':row.registered_verified_files?'已登记验证文件，复用前检查完整性':'尚未记录已验证文件'}</small></div>`).join('')||'<p>没有匹配论文；可换关键词，或使用 DOI／BibTeX／检索词。</p>';
        $('collect-selected-papers').innerHTML=state.selected.map(row=>`<div class="item collection-paper-row"><strong>${escapeHtml(row.title||row.paper_id)}</strong><button type="button" data-remove-collect-paper="${escapeHtml(row.paper_id)}" ${state.locked?'disabled':''}>移除选择</button></div>`).join('')||'<p>还未选择已有论文。</p>';
        $('collect-selected-count').textContent=state.selected.length;
        $('collect-paper-pages').innerHTML=`<span>Catalog 匹配 ${state.total} 篇</span> <button type="button" data-collect-paper-page="${Math.max(0,state.offset-25)}" ${!state.offset||state.pending||state.locked?'disabled':''}>上一页</button><button type="button" data-collect-paper-page="${state.offset+25}" ${!state.hasMore||state.pending||state.locked?'disabled':''}>下一页</button>`;
        $('collect-paper-feedback').textContent=state.storageProblem||state.error||'这里只选择目录论文，检查输入才会确认文件是否可以复用。';
      }
      const collectionProgress=CatalogCollections.createProgressController({api,storage:collectStorage,makeKey:()=>crypto.randomUUID(),onState:renderCollectionProgress});
      function renderCollectionProgress(state){
        const host=$('collection-progress-panel');if(!host||collectionDetails?.collection.collection_id!==state.id)return;
        const p=state.progress;if(!p){host.innerHTML='<p role="status">读取前沿与处理服务状态…</p>';return;}
        const labels={PARTIAL_BUDGET:'预算触限，部分完成',PAUSED:'采集已暂停',WAITING_REVIEW:'等待人工复核',PROCESSING:'仍有任务待处理',PARTIAL_FAILURE:'有失败任务，部分完成',PARTIAL_UNRESOLVED_REFERENCES:'尚有引用未解析',CURRENT_FRONTIER_COMPLETE:'当前前沿处理完成'};
        const u=p.budget.usage,limits=state.draft.limits||{},disabled=state.pending||state.request?' disabled':'';
        const fields=[['max_papers','最多论文数',1],['max_registered_pdf_bytes','登记 PDF 总量（GiB）',1024**3],['max_active_seconds','累计运行时间（小时）',3600],['max_task_attempts','最多任务尝试次数',1]];
        const inputs=fields.map(([key,label,scale])=>'<label class="collect-field"><span>'+label+'（留空表示不限）</span><input type="number" name="'+key+'" data-budget-limit="'+key+'" min="0" step="any" autocomplete="off" value="'+(limits[key]===null?'':limits[key]/scale)+'"'+disabled+'></label>').join('');
        const workers=p.workers.map(row=>'<div class="item"><strong>'+escapeHtml({network:'获取服务',parser:'解析服务',model:'模型处理服务'}[row.role]||row.role)+'</strong><p>'+escapeHtml(row.observation==='STOPPED'?'已报告停止':row.observation==='HEARTBEAT_EXPIRED'?'心跳已过期':row.state==='RUNNING'?'最近报告执行中':'最近报告空闲')+' · '+escapeHtml(collectionTime(row.observed_at))+'</p></div>').join('')||'<p>尚无独立服务心跳记录；任务排队不代表服务正在运行。</p>';
        const refs=p.references.map(row=>'<div class="item"><strong>'+escapeHtml(row.resolution_note)+'</strong><p>'+escapeHtml(row.raw_text)+'</p><small>原文第 '+(row.page_number??'未知')+' 页 · '+escapeHtml(row.location.section||'未记录章节')+'</small>'+(row.target_paper_id?'<button type="button" data-paper="'+escapeHtml(row.target_paper_id)+'">查看已定位论文</button>':'')+'</div>').join('')||'<p>尚无本次原文引用记录。</p>';
        host.innerHTML='<section class="section"><h3>当前前沿与停止原因</h3><p>'+escapeHtml(labels[p.completion]||p.completion)+' · 待处理任务 '+p.frontier_jobs+' · 原文引用 '+p.reference_total+'，未解析 '+p.unresolved_references+'</p><p>本范围已登记 '+u.papers+' 篇／'+(u.registered_pdf_bytes/1024**3).toFixed(3)+' GiB PDF，累计运行 '+Math.round(u.active_seconds)+' 秒，任务尝试 '+u.task_attempts+' 次。</p><p>文件量按登记内容统计，重复文件只计一次；此处不是网络流量或模型费用。</p>'+(u.stop_reason?'<p class="review-note">预算已触限，前沿与原文保留。调整预算后可继续采集。</p>':'')+'</section><section class="section"><h3>预算设置</h3>'+(p.budget.configuration==='LEGACY_UNRECORDED'?'<p>旧任务未记录预算；下方建议值尚未应用，保存后才生效。</p>':'')+inputs+'<label class="collect-field"><span>本次调整原因</span><textarea name="budget_reason" data-budget-reason autocomplete="off" maxlength="4000"'+disabled+'>'+escapeHtml(state.draft.reason)+'</textarea></label>'+(state.comparisonRequired&&!state.request?'<p>采集状态已变，原草稿保留。</p><button type="button" data-compare-collection-budget>对照当前状态后继续</button>':'')+'<button type="button" data-save-collection-budget '+(state.pending||state.storageProblem?'disabled':'')+'>'+(state.pending?'正在保存…':state.request?'核对上次预算请求':'保存预算')+'</button><p id="collection-budget-feedback" role="status" tabindex="-1">'+escapeHtml(state.error||state.storageProblem)+'</p><p>保存预算不会自动恢复采集；仍需点击“继续采集”。</p></section><section class="section"><h3>处理服务独立心跳</h3>'+workers+'<p>心跳与任务租约分别显示；超过 45 秒未报到会标为过期。</p></section><section class="section"><h3>原文引用与未解析前沿</h3>'+refs+'<button type="button" data-reference-page="'+Math.max(0,p.reference_offset-50)+'" '+(!p.reference_offset?'disabled':'')+'>上一页引用</button><button type="button" data-reference-page="'+(p.reference_offset+50)+'" '+(!p.references_have_more?'disabled':'')+'>下一页引用</button><p>没有固定深度截止；当前前沿处理完不代替科学审核。</p></section>';
      }
      async function saveCollectionBudget(){try{await collectionProgress.submit();await openCollectionDetails(collectionProgress.state().id);}catch(error){const feedback=$('collection-budget-feedback');if(feedback){feedback.textContent=errorText(error);feedback.focus();}}}
      const reviewWorkflow=CatalogReviewWorkflow.createController({api,makeKey:()=>crypto.randomUUID(),storage:collectStorage,namespace:'rstv4-review-action',onState:renderReviewWorkflow});
      const scientificReview=CatalogScientificReview.createController({api,makeKey:()=>crypto.randomUUID(),storage:collectStorage,onState:renderScientificReview});
      function renderScientificReview(state){
        if(view!=='scientific_review')return;const host=$('research-workspace'),c=state.context;
        if(!c){host.innerHTML=`<p role="status">${escapeHtml(state.error||'正在读取当前科学依据…')}</p>`;return;}
        const list=(items,source=c)=>items.map(item=>{const record=(item.node_id?source.nodes:source.evidence).find(row=>(row.node_id||row.evidence_id)===(item.node_id||item.evidence_id)),section=source.author_structure?.sections.find(row=>row.id===item.section);return `<div class="item"><strong>${escapeHtml(record?.statement||item.node_id||item.evidence_id)}</strong><p>${item.node_id?`节点修订 ${item.node_revision} · ${escapeHtml(section?.title||item.section||'未放置章节')}`:'固定来源依据'}</p><small translate="no">${escapeHtml(item.node_id||item.evidence_id)}</small></div>`;}).join('')||'<p>尚无绑定。</p>';
        const nodes=c.nodes.map(node=>{const placement=CatalogScientificReview.sectionChoices(c,state.draft,node.node_id);return `<div class="item"><label><input type="checkbox" name="scientific_nodes" data-scientific-node="${escapeHtml(node.node_id)}" ${state.draft.node_ids.includes(node.node_id)?'checked':''} ${(node.status!=='APPROVED'&&!state.draft.node_ids.includes(node.node_id))||state.pending?'disabled':''}>${escapeHtml(node.statement)} · ${escapeHtml(node.status)} · 修订 ${node.revision}</label><label class="collect-field"><span>所选节点的章节</span><select name="scientific_section" data-scientific-section="${escapeHtml(node.node_id)}" aria-label="为所选科研节点选择章节" ${!state.draft.node_ids.includes(node.node_id)||state.pending?'disabled':''}><option value="" ${!placement.current?'selected':''}>未放置章节</option>${placement.legacy?`<option value="${escapeHtml(placement.current)}" selected disabled>旧绑定：${escapeHtml(placement.current)}（需重新选择）</option>`:''}${placement.sections.map(section=>`<option value="${escapeHtml(section.id)}" ${placement.current===section.id?'selected':''}>${escapeHtml(section.title)}</option>`).join('')}</select></label></div>`;}).join('');
        const evidence=c.evidence.map(item=>`<label class="item"><input type="checkbox" name="scientific_evidence" data-scientific-evidence="${escapeHtml(item.evidence_id)}" ${state.draft.evidence_ids.includes(item.evidence_id)?'checked':''} ${(!item.source_available&&!state.draft.evidence_ids.includes(item.evidence_id))||state.pending?'disabled':''}>${escapeHtml(item.statement)} · ${item.source_available?'当前来源可用':'来源需重新审阅'}</label>`).join('');
        const proposals=c.reviews.map(row=>`<article class="item"><h3>${escapeHtml(row.status==='APPLIED'?'已确认的科学绑定':'等待批准的复核提案')}</h3><p>${escapeHtml(row.request.reason)}</p><details><summary>原依据与提议的新绑定</summary><h4>原绑定</h4>${list(row.context.bindings.nodes,row.context)}${list(row.context.bindings.evidence,row.context)}<h4>新绑定</h4>${list(row.context.proposed_bindings.nodes,row.context)}${list(row.context.proposed_bindings.evidence,row.context)}</details>${row.status==='PROPOSED'?`<p>请在 Scholar／Orchestrator 的用户消息中发送以下批准用语；此页面不会代填批准记录。</p><pre translate="no">${escapeHtml(row.approval_phrase)}</pre><button type="button" data-apply-scientific-review="${escapeHtml(row.review_id)}" ${!row.grant_available||state.pending?'disabled':''}>应用已收到用户批准的绑定</button>`:'<p>已保存原／新绑定与批准记录，旧成文保留。</p>'}</article>`).join('');
        host.innerHTML=`<header class="research-head"><div><h1>${escapeHtml(c.manuscript.title)} · 科学依据复核</h1><p>${c.manuscript.needs_scientific_review?'当前稿件需要科学重审':'当前未标为待科学重审'} · 修订 ${c.manuscript.revision}</p></div></header><section class="research-section"><h2>当前绑定</h2>${list(c.bindings.nodes)}${list(c.bindings.evidence)}</section><section class="research-section"><h2>提议的完整新绑定</h2><p>选择新审阅的节点与依据。应用提案会替换当前绑定集合，旧集合保存在历史记录中。</p><div>${nodes||'<p>没有可选择的科研节点。</p>'}</div><div>${evidence||'<p>没有可选择的来源依据。</p>'}</div><label class="collect-field"><span>本次重审说明</span><textarea id="scientific-review-reason" name="scientific_review_reason" autocomplete="off" maxlength="4000" ${state.pending?'disabled':''}>${escapeHtml(state.draft.reason)}</textarea></label>${state.comparisonRequired?'<p class="review-note">依据或稿件状态已改变，原草稿保留。对照后才可提交新的提案。</p><button type="button" data-compare-scientific-review>对照当前依据后继续</button>':''}<button type="button" data-propose-scientific-review ${state.pending||state.storageError||state.comparisonRequired?'disabled':''}>${state.request?'核对上次提案请求':'保存完整新绑定提案'}</button><button type="button" data-refresh-scientific-review>更新当前依据与批准状态</button><p id="scientific-review-feedback" role="status" tabindex="-1">${escapeHtml(state.error)}</p></section><section class="research-section"><h2>复核提案与历史</h2>${proposals||'<p>还没有复核提案。</p>'}</section>`;
      }
      async function scientificReviewAction(kind,id){try{if(kind==='propose')await (scientificReview.state().request?scientificReview.retry():scientificReview.propose());else if(kind==='apply')await scientificReview.apply(id);else await scientificReview.load(scientificReview.state().manuscriptId);}catch(error){if($('scientific-review-feedback')){$('scientific-review-feedback').textContent=errorText(error);$('scientific-review-feedback').focus();}}}
      function renderReviewWorkflow(state){
        const panel=$('review-workflow-panel');if(!panel||selectedCase!==state.caseId||view!=='review_queue')return;
        const c=state.context;
        if(!c){panel.innerHTML=`<h3>复核与继续</h3><p aria-live="polite">${escapeHtml(state.error||'正在读取原文件与任务…')}</p><button type="button" data-refresh-review-workflow>更新复核依据</button>`;return;}
        const isParser=c.kind==='PARSER',missing=c.candidate?.quality?.reference_page_alignment?.missing_source_numbered_references||[];
        for(const control of document.querySelectorAll('[data-annotate-field],[data-review-decision],[data-annotation-comment]'))control.disabled=state.pending||c.file.identity_status!=='NEEDS_REVIEW'||!c.integrity_verified;
        const referenceAction=document.querySelector('[data-parser-reference-selection]');if(referenceAction)referenceAction.disabled=state.pending||state.comparisonRequired||!c.allowed_actions.includes('RECHECK_PARSE');
        const action=isParser?'RECHECK_PARSE':c.file.identity_status==='VERIFIED'?'REOPEN_IDENTITY':'APPROVE_IDENTITY',allowed=c.allowed_actions.includes(action);
        const history=c.history.map(row=>`<div class="item"><strong>${escapeHtml({APPROVED_IDENTITY:'文件身份已批准',IDENTITY_REOPENED:'文件已重新进入审核，原版本保留',IDENTITY_STILL_NEEDS_REVIEW:'身份复核未通过',PARSE_RECHECK_QUEUED:'已请求解析复检'}[row.result.status]||row.result.status)}</strong><p>${escapeHtml(row.reason)} · ${escapeHtml(row.reviewer_label)} · ${escapeHtml(collectionTime(row.created_at))}</p></div>`).join('');
        const currentState=isParser?{NEEDS_HUMAN:'等待本次复检',READY:'已进入解析复检队列',RUNNING:'正在解析与复检',SUCCEEDED:'解析结果已发布新版本'}[c.job.status]||c.job.status:{VERIFIED:'当前文件身份已验证',NEEDS_REVIEW:'当前文件等待复核'}[c.file.identity_status]||c.file.identity_status;
        panel.innerHTML=`<h3>复核与继续</h3><p>${escapeHtml(currentState)}</p>`+
          (!c.integrity_verified?'<p class="error">原文件内容已改变，请注册新文件版本后再复核。</p>':'')+
          (isParser?`<p>${c.candidate?.available?`已保存原解析候选；${missing.length?'仍缺参考文献编号：'+missing.join('、'):'需要重新检查解析结果。'}`:'原解析候选未保存，可重新解析原文件并复检。'}</p>`:'<p>先保存原文核对与修正，再明确批准当前文件身份。解析质量会独立复检。</p>')+
          (action==='REOPEN_IDENTITY'?`<p class="review-note">重新审核会停住 ${c.source_impact.jobs.length} 项相关任务，并标记 ${c.source_impact.nodes.length} 个研究节点与 ${c.source_impact.manuscripts.length} 份稿件待重审。原文、版本、依据与记录保留。</p>`:'')+
          `<div>${state.draft.selections.map((range,index)=>`<div class="item"><strong>第 ${range.page_number} 页原文</strong><p>${escapeHtml(range.text)}</p><button type="button" data-remove-parser-selection="${index}" ${state.pending?'disabled':''}>移除此条补充</button></div>`).join('')}</div>`+
          `<label class="collect-field"><span>本次复核说明</span><textarea id="review-workflow-reason" name="review_reason" autocomplete="off" maxlength="4000" ${state.pending?'disabled':''}>${escapeHtml(state.draft.reason)}</textarea></label>`+
          (state.comparisonRequired?`<div class="review-note"><p>文件、核对记录或任务状态已更新；原说明和选区已保留。</p><button type="button" data-compare-review-workflow ${state.pending||state.request?'disabled':''}>对照新状态后继续</button></div>`:'')+
          (state.request?`<button type="button" data-retry-review-workflow ${state.pending?'disabled':''}>核对上次复核请求</button>`:`<button type="button" class="primary" data-submit-review-workflow="${action}" ${state.pending||state.storageError||state.comparisonRequired||!allowed?'disabled':''}>${state.pending?'正在提交…':isParser?(state.draft.selections.length?'补充并复检':'重新解析并复检'):action==='REOPEN_IDENTITY'?'重新审核当前文件身份':'复核并批准文件身份'}</button>`)+
          `<button type="button" data-refresh-review-workflow ${state.pending?'disabled':''}>更新复核依据</button><p id="review-workflow-feedback" aria-live="polite" class="${state.error?'error':''}">${escapeHtml(state.error)}</p>`+
          `<p>采集暂停状态会保留。重新排队后，任务完成质量检查才会发布解析版本。</p>`+
          (history?`<h4>复核记录</h4>${history}`:'');
      }
      async function submitReviewWorkflow(action,retry=false){
        try{await (retry?reviewWorkflow.retry():reviewWorkflow.submit(action));loadSummary();loadResearchOverview();}
        catch(error){if($('review-workflow-feedback'))$('review-workflow-feedback').textContent=errorText(error);}
      }
      function normalizeCollectDoi(value){
        let doi=value.trim().replace(/^(?:https?:\/\/(?:dx\.)?doi\.org\/|doi:\s*)/i,'').replace(/[.,;]+$/,'').toLowerCase();
        while(doi.endsWith(')')&&(doi.match(/\)/g)||[]).length>(doi.match(/\(/g)||[]).length)doi=doi.slice(0,-1);
        return doi;
      }
      function collectInputSummary(){
        const lines=$('collect-dois').value.split(/\r?\n/).map(line=>line.trim()).filter(Boolean);
        const bibtex=$('collect-bibtex').value;
        const bibDois=[...bibtex.matchAll(/\bdoi\s*=\s*[{\"]?\s*((?:https?:\/\/(?:dx\.)?doi\.org\/)?10\.\d{4,9}\/[^\s},\"]+)/gi)].map(match=>normalizeCollectDoi(match[1]));
        const valid=lines.map(normalizeCollectDoi).filter(doi=>/^10\.\d{4,9}\/\S+$/i.test(doi));
        const all=[...valid,...bibDois];
        return {doiCount:new Set(all).size,bibCount:[...bibtex.matchAll(/@\w+\s*[{(]/g)].length,
          queryCount:$('collect-queries').value.split(/\r?\n/).filter(line=>line.trim()).length,
          duplicateCount:all.length-new Set(all).size,invalidCount:lines.length-valid.length};
      }
      function updateCollectPreview(){
        const summary=collectInputSummary();
        $('collect-doi-count').textContent=summary.doiCount;
        $('collect-bib-count').textContent=summary.bibCount;
        $('collect-query-count').textContent=summary.queryCount;
        $('collect-duplicate-count').textContent=summary.duplicateCount;
        $('collect-invalid-count').textContent=summary.invalidCount;
        $('collect-preview-field').textContent=collectScope?[collectScope.field,collectScope.topic,collectScope.track].filter(Boolean).join(' / '):'从总览选择';
        if(collectScope?.fieldId&&(collectScope.topicId||collectScope.trackId))collectController.change({
          field_id:collectScope.fieldId,topic_id:collectScope.topicId||null,track_id:collectScope.trackId||null,
          name:`${collectScope.track||collectScope.topic} · 文献采集`,scope:{topic:collectScope.topic,track:collectScope.track},
          ...(['collect-max-papers','collect-max-bytes','collect-max-hours','collect-max-attempts'].some(id=>$(id).value.trim())?{budget:{max_papers:$('collect-max-papers').value.trim()?Number($('collect-max-papers').value):500,max_registered_pdf_bytes:$('collect-max-bytes').value.trim()?Math.round(Number($('collect-max-bytes').value)*1024**3):10737418240,max_active_seconds:$('collect-max-hours').value.trim()?Math.round(Number($('collect-max-hours').value)*3600):86400,max_task_attempts:$('collect-max-attempts').value.trim()?Number($('collect-max-attempts').value):null}}:{}),
          paper_ids:collectPaperPicker.paperIds(),dois:$('collect-dois').value.split(/\r?\n/).map(line=>line.trim()).filter(Boolean),
          bibtex:$('collect-bibtex').value||null,queries:$('collect-queries').value.split(/\r?\n/).map(line=>line.trim()).filter(Boolean)});
        else {$('collect-start').disabled=true;$('collect-feedback').textContent='请返回总览，从真实 Topic 或 Track 进入；示例不会创建任务。';}
        return summary;
      }
      async function checkCollectInput(){
        const summary=updateCollectPreview();
        const feedback=$('collect-feedback');
        if(!collectScope)feedback.textContent='请先返回研究总览，从 Topic 或 Track 的采集按钮进入。';
        else if(!summary.doiCount&&!summary.bibCount&&!summary.queryCount&&!collectPaperPicker.paperIds().length)feedback.textContent='请选择已有论文，或填写 DOI、BibTeX／检索式。';
        else if(summary.invalidCount)feedback.textContent=`发现 ${summary.invalidCount} 行无法识别为 DOI；可修改后再检查。`;
        else {try{await collectController.check();}catch{}}
      }
      function findNode(node,id){if(node.id===id)return node;for(const child of node.filters||[]){const found=findNode(child,id);if(found)return found;}return null;}
      function removeNode(node,id){node.filters=node.filters.filter(item=>item.id!==id);node.filters.forEach(item=>{if(item.type==='group')removeNode(item,id);});}
      function ruleOptions(field){
        if(numericFields.has(field))return ['is','is_not','before','after','on_or_before','on_or_after','is_empty','is_not_empty'];
        if(field.endsWith('_at'))return ['is','before','after','on_or_before','on_or_after','is_empty'];
        return ['is','is_not','contains','does_not_contain','is_empty','is_not_empty'];
      }
      const operatorLabels={is:'Is',is_not:'Is not',contains:'Contains',does_not_contain:'Does not contain',is_empty:'Is empty',is_not_empty:'Is not empty',before:'Before / less than',after:'After / greater than',on_or_before:'On or before',on_or_after:'On or after'};
      function renderGroup(node,root=false,depth=0){
        const head=`<div class="group-head"><span>${root?'Where':'Match'}</span><select data-group-mode="${node.id}" aria-label="Filter group logic"><option value="and" ${node.operator==='and'?'selected':''}>All (AND)</option><option value="or" ${node.operator==='or'?'selected':''}>Any (OR)</option></select>${root?'':`<button type="button" class="mini" data-remove="${node.id}">Remove group</button>`}</div>`;
        const children=node.filters.map(item=>item.type==='group'?renderGroup(item,false,depth+1):`<div class="rule"><select data-rule-field="${item.id}" aria-label="Filter field">${options(Object.keys(fields),item.field)}</select><select data-rule-op="${item.id}" aria-label="Filter operator">${ruleOptions(item.field).map(op=>`<option value="${op}" ${op===item.operator?'selected':''}>${operatorLabels[op]}</option>`).join('')}</select>${['is_empty','is_not_empty'].includes(item.operator)?'':statusChoices[item.field]?`<select data-rule-value="${item.id}" aria-label="Filter value"><option value="">Select…</option>${options(statusChoices[item.field],item.value)}</select>`:`<input data-rule-value="${item.id}" aria-label="Filter value" type="${item.field.endsWith('_at')?'date':numericFields.has(item.field)?'number':'text'}" value="${escapeHtml(item.value??'')}" placeholder="Value">`}<button type="button" class="mini" data-remove="${item.id}" aria-label="Remove filter rule">×</button></div>`).join('');
        return `<div class="group ${root?'root':''}">${head}${children}<button type="button" class="mini" data-add-rule="${node.id}">＋ Add filter rule</button>${depth<3?`<button type="button" class="mini" data-add-group="${node.id}">＋ Add group</button>`:''}</div>`;
      }
      function renderFilter(){ $('filter-panel').innerHTML='<h3>Filter</h3>'+renderGroup(filter,true); }
      function renderSort(){ $('sort-panel').innerHTML='<h3>Sort</h3>'+sorts.map((s,i)=>`<div class="sort-row"><select data-sort-field="${i}" aria-label="Sort field">${options(Object.keys(fields),s.field)}</select><select data-sort-direction="${i}" aria-label="Sort direction"><option value="asc" ${s.direction==='asc'?'selected':''}>A→Z / oldest→newest</option><option value="desc" ${s.direction==='desc'?'selected':''}>Z→A / newest→oldest</option></select><button type="button" class="mini" data-sort-remove="${i}" aria-label="Remove sort">×</button></div>`).join('')+'<button type="button" class="mini" data-sort-add="1">＋ Add sort</button>'; }
      function renderColumns(){
        $('columns-panel').innerHTML='<h3>Columns</h3><p class="small muted">Show, hide, reorder, and resize headers. Changes are saved in this browser.</p><div class="columns-list">'+columns.sort((a,b)=>a.order-b.order).map((c,i)=>`<div class="column-row"><label><input type="checkbox" data-column-visible="${c.key}" ${c.visible?'checked':''}>${escapeHtml(fields[c.key])}</label><input type="number" min="70" max="600" value="${c.width}" data-column-width="${c.key}" aria-label="${escapeHtml(fields[c.key])} width in pixels"><button type="button" class="mini" data-column-up="${c.key}" aria-label="Move ${escapeHtml(fields[c.key])} up" ${i===0?'disabled':''}>↑</button><button type="button" class="mini" data-column-down="${c.key}" aria-label="Move ${escapeHtml(fields[c.key])} down" ${i===columns.length-1?'disabled':''}>↓</button></div>`).join('')+'</div><button type="button" class="mini" id="reset-columns">Reset columns</button>';
      }
      function togglePanel(name){
        $('view-menu').hidden=true;$('view-trigger').setAttribute('aria-expanded','false');
        for(const panel of ['filter','sort','columns']){
          const el=$(panel+'-panel');el.hidden=panel!==name||!el.hidden;
          document.querySelector(`[data-panel="${panel}"]`).classList.toggle('active',!el.hidden);
        }
      }
      function displayValue(value){return value===null||value===undefined||value===''?'—':String(value);}
      function section(title,content,target){return `<section class="section" ${target?`data-discussion-section="${escapeHtml(JSON.stringify(target))}"`:''}><h3>${title}</h3>${content}</section>`;}
      function discussionButton(target,label='讨论此部分'){return `<button type="button" class="discussion-select" data-discussion-target="${escapeHtml(JSON.stringify(target))}">${escapeHtml(label)}</button>`;}
      const deepRead=CatalogCollections.createDeepReadController({api,storage:collectStorage,makeKey:()=>crypto.randomUUID(),onState:renderDeepRead});
      function renderDeepRead(state){
        const panel=$('deep-read-panel');if(!panel||!state.paper||panel.dataset.paperId!==state.paper.paper_id)return;
        const disabled=state.pending||Boolean(state.request),draft=state.draft;
        const option=(value,label,selected)=>'<option value="'+escapeHtml(value)+'" '+(selected?'selected':'')+'>'+escapeHtml(label)+'</option>';
        let owners=option('','选择采集',!draft.collection_id)+(state.paper.collections||[]).map(c=>option(c.collection_id,c.name+' · '+c.status,c.collection_id===draft.collection_id)).join('');
        if(draft.collection_id&&!(state.paper.collections||[]).some(c=>c.collection_id===draft.collection_id))owners+=option(draft.collection_id,'原采集未在当前列表中',true);
        let parses=option('','选择已完成的解析版本',!draft.parse_run_id)+(state.paper.parse_runs||[]).filter(p=>p.status==='SUCCEEDED').map(p=>option(p.parse_run_id,p.parser_name+' · '+p.parser_version+' · '+p.parse_run_id,p.parse_run_id===draft.parse_run_id)).join('');
        if(draft.parse_run_id&&!(state.paper.parse_runs||[]).some(p=>p.parse_run_id===draft.parse_run_id))parses+=option(draft.parse_run_id,'原解析版本未在当前列表中',true);
        panel.innerHTML='<p class="small muted">使用所选解析版本请求深读。暂停的采集会保留请求，明确继续后才执行。</p>'+
          '<label>所属采集<select name="deep_read_collection" data-deep-read-field="collection_id" '+(disabled?'disabled':'')+'>'+owners+'</select></label>'+
          '<label>解析版本<select name="deep_read_parse" data-deep-read-field="parse_run_id" '+(disabled?'disabled':'')+'>'+parses+'</select></label>'+
          '<label>深读理由<textarea name="deep_read_reason" data-deep-read-field="reason" maxlength="4000" autocomplete="off" '+(disabled?'disabled':'')+'>'+escapeHtml(draft.reason)+'</textarea></label>'+
          '<p role="status" aria-live="polite" tabindex="-1" data-deep-read-status class="'+(state.error||state.storageProblem?'error':'small')+'">'+escapeHtml(state.storageProblem||state.error||(state.receipt?'请求已保存 · '+state.receipt.status:state.request?'上次响应未确定，请核对同一个请求。':''))+'</p>'+
          '<button type="button" data-submit-deep-read '+(state.pending?'disabled':'')+'>'+(state.pending?'保存深读请求…':state.request?'核对原深读请求':'请求深读')+'</button>';
      }
      document.addEventListener('input',event=>{if(event.target.dataset.deepReadField)deepRead.edit({[event.target.dataset.deepReadField]:event.target.value});});
      document.addEventListener('click',event=>{if(event.target.closest('[data-submit-deep-read]'))deepRead.submit().catch(error=>{const status=document.querySelector('[data-deep-read-status]');if(status){status.textContent=errorText(error);status.classList.add('error');status.focus();}});});
      document.addEventListener('toggle',async event=>{
        const detail=event.target;if(!detail.open||!detail.dataset.modelCallId||detail.dataset.loaded==='true')return;
        const output=detail.querySelector('[data-model-call-output]');output.textContent='读取原调用…';
        try{const data=await api('/api/catalog/papers/'+encodeURIComponent(detail.dataset.paperId)+'/model-calls/'+encodeURIComponent(detail.dataset.modelCallId));if(!detail.isConnected)return;output.textContent=JSON.stringify({source:data.source,input:data.input,output:data.output,contract:data.contract,error_type:data.error_type},null,2);detail.dataset.loaded='true';}
        catch(error){if(detail.isConnected)output.textContent=errorText(error);}
      },true);
      let paperLoadToken=0;
      async function openPaper(id){
        collectionDetailToken++;collectionDetails=null;
        const token=++paperLoadToken;
        const drawer=$('paper-drawer');drawer.hidden=false;drawer.innerHTML='<div class="status-line">Loading paper…</div>';
        try{
          const p=await api('/api/catalog/papers/'+encodeURIComponent(id));
          if(token!==paperLoadToken||drawer.hidden)return;
          const paperTarget={module:'CATALOG',paper_id:id,object_kind:'paper',object_id:id};
          void researchChat.choose(paperTarget,null,false);
          const property=part=>discussionButton({...paperTarget,object_kind:'property',part});
          const brief=p.assessments.find(a=>a.assessment_type==='QUICK_READ');
          const fieldsToShow=['question','method','materials','author_contribution','results','limitations'];
          const briefHtml=brief?fieldsToShow.map(key=>{const target={...paperTarget,object_kind:'assessment',object_id:brief.assessment_id,part:key};return `<p data-discussion-section="${escapeHtml(JSON.stringify(target))}"><strong>${escapeHtml(key.replaceAll('_',' '))}:</strong> ${escapeHtml(displayValue(brief.result?.[key]))}${discussionButton(target)}</p>`;}).join(''):'<p class="muted">QuickRead has not run for this paper.</p>';
          drawer.innerHTML=`<div class="drawer-head"><div><h2>${escapeHtml(p.title)}</h2><span class="muted">${escapeHtml((p.authors||[]).join(', '))} · ${escapeHtml(displayValue(p.published_year))}</span></div><button type="button" id="close-paper" aria-label="Close paper details">✕</button></div>`+
            section('Identity',`<p>${discussionButton(paperTarget,'讨论这篇论文')} ${property('title')}</p><p data-discussion-section="${escapeHtml(JSON.stringify({...paperTarget,object_kind:'property',part:'doi'}))}"><strong>DOI:</strong> ${escapeHtml(displayValue(p.doi))}${property('doi')}</p><p><strong>Catalog:</strong> ${escapeHtml(p.catalog_status)}</p><p data-discussion-section="${escapeHtml(JSON.stringify({...paperTarget,object_kind:'property',part:'abstract'}))}"><strong>Abstract:</strong> ${escapeHtml(displayValue(p.abstract))}${property('abstract')}</p>`,paperTarget)+
            section(`PDF versions (${p.files.length})`,p.files.length?p.files.map(f=>`<div class="item"><span class="badge ${f.identity_status==='NEEDS_REVIEW'?'warn':''}">${escapeHtml(f.identity_status)}</span> ${escapeHtml(f.acquisition_method)} · ${escapeHtml(f.created_at)}<br><span class="small muted">${escapeHtml(f.storage_path)}</span><br><a href="/api/catalog/files/${encodeURIComponent(f.file_version_id)}/pdf" target="_blank" rel="noopener">Open PDF</a> <a href="/?view=review&case=${encodeURIComponent(f.file_version_id)}" data-open-review-file="${escapeHtml(f.file_version_id)}">复核当前文件与记录</a></div>`).join(''):'<p class="muted">No PDF registered.</p>')+
            section('Content brief',briefHtml,brief?{...paperTarget,object_kind:'assessment',object_id:brief.assessment_id}:null)+
            section('Parse and references',`<p>${p.parse_runs.length} parse run(s) · ${p.references.length} reference entries</p>${p.parse_runs.map(run=>`<p>${escapeHtml(run.parser_name)} · ${escapeHtml(run.parser_version)} · ${escapeHtml(run.status)} ${discussionButton({...paperTarget,object_kind:'parse',object_id:run.parse_run_id},'打开解析原文并讨论')}</p>`).join('')}${p.references.slice(0,10).map(r=>`<p class="small">${escapeHtml(r.raw_text)} ${r.page_number?'(p. '+r.page_number+')':''}</p>`).join('')}`)+
            section('PaperSkeleton',`<p>${p.skeletons.length?`${p.skeletons.length} version(s) available`:'Not generated yet.'}</p>${p.skeletons.map(s=>discussionButton({...paperTarget,object_kind:'skeleton',object_id:s.skeleton_id},`讨论 Skeleton v${s.version}`)).join('')}`)+
            section('按需深读',`<div id="deep-read-panel" data-paper-id="${escapeHtml(id)}"></div>`)+
            section('实际模型调用',(p.model_calls||[]).length?(p.model_calls||[]).map(call=>`<details class="item" style="content-visibility:auto;overflow-wrap:anywhere" data-model-call-id="${escapeHtml(call.call_id)}" data-paper-id="${escapeHtml(id)}"><summary>${escapeHtml(call.task)} · ${escapeHtml(call.status)} · ${escapeHtml(call.contract?.actual_model||'实际模型未记录')}</summary><pre data-model-call-output style="white-space:pre-wrap;overflow-wrap:anywhere" role="status" aria-live="polite"></pre></details>`).join(''):'<p class="muted">尚无实际调用记录；旧记录不补造模型信息。</p>')+
            section('Processing history',p.processing.length?p.processing.map(j=>`<p class="small">${escapeHtml(j.job_type)} · ${escapeHtml(j.status)} ${j.last_error_detail?'· '+escapeHtml(j.last_error_detail):''}</p>`).join(''):'<p class="muted">No pipeline jobs have run for this paper.</p>');
          deepRead.load(p);
        }catch(error){if(token===paperLoadToken)drawer.innerHTML=`<button type="button" id="close-paper">✕</button><p class="error">${escapeHtml(errorText(error))}</p>`;}
      }
      async function loadCases(){
        $('case-items').innerHTML='<p class="status-line">Loading review cases…</p>';
        try{cases=await api('/api/catalog/review/cases');renderCases();
          const wanted=new URLSearchParams(location.search).get('case')||selectedCase;
          const matching=matchingCases();
          if(wanted&&!matching.some(c=>c.case_id===wanted)){await openExactReviewCase(wanted);return;}
          const first=matching.find(c=>c.case_id===wanted)||matching[0];
          if(first)showCase(first.case_id);
          else showEmptyCases();
        }
        catch(error){$('case-items').innerHTML=`<p class="error">${escapeHtml(errorText(error))}</p>`;}
      }
      function matchingCases(){const q=$('case-search').value.trim().toLocaleLowerCase();const kind=$('case-kind').value;return cases.filter(c=>(kind==='all'||c.kind===kind)&&(!q||`${c.title} ${c.doi||''}`.toLocaleLowerCase().includes(q)));}
      function reviewCase(id){return cases.find(item=>item.case_id===id)||(locatedReviewCase?.case_id===id?locatedReviewCase:null);}
      async function openExactReviewCase(id){
        const token=++pdfReviewLoadToken;selectedCase=id;
        $('case-detail').innerHTML='<p role="status">正在读取原文件复核记录…</p>';
        try{
          const context=await api(`/api/catalog/review/cases/${encodeURIComponent(id)}/workflow`);
          if(selectedCase!==id||token!==pdfReviewLoadToken||view!=='review_queue')return;
          locatedReviewCase={case_id:id,kind:context.kind,paper_id:context.paper.paper_id,title:context.paper.title,doi:context.paper.doi,
            file_version_id:context.file.file_version_id,created_at:context.file.created_at,detail:context.kind==='PARSER'?context.job.last_error_detail:context.file.validation};
          showPdfReviewCase(locatedReviewCase);
        }catch(error){if(selectedCase===id&&token===pdfReviewLoadToken)$('case-detail').innerHTML=`<p class="error" role="alert">原复核案件无法读取：${escapeHtml(errorText(error))}</p>`;}
      }
      function renderCases(){
        const matching=matchingCases();
        $('review-count').textContent=`待审核 · ${matching.length.toLocaleString()}`;
        $('case-items').innerHTML=matching.map(c=>`<button type="button" class="case ${selectedCase===c.case_id?'active':''}" data-case="${escapeHtml(c.case_id)}"><span class="case-title">${escapeHtml(c.title)}</span><span class="case-sub">${c.kind==='PDF_IDENTITY'?'PDF 身份':'解析质量'} · ${escapeHtml(c.created_at?.slice(0,10))}</span></button>`).join('');
        if(!matching.length)$('case-items').innerHTML='<p class="status-line">没有符合条件的审核记录。</p>';
      }
      function showEmptyCases(){
        selectedCase=null;
        const parser=$('case-kind').value==='PARSER';
        $('case-detail').innerHTML=`<div class="review-empty"><strong>${parser?'目前没有 NEEDS_HUMAN 解析案件':'没有符合条件的审核记录'}</strong><span>${parser?'解析器今后标记 NEEDS_HUMAN 时，这里会显示解析疑点、原文和参考文献核对任务。':'可以切换审核类型或修改搜索条件。'}</span></div>`;
        const url=new URL(location.href);url.searchParams.delete('case');history.replaceState({},'',url);
      }
      function syncCaseSelection(){
        const matching=matchingCases();
        if(!matching.length){renderCases();showEmptyCases();}
        else if(!matching.some(c=>c.case_id===selectedCase))showCase(matching[0].case_id);
        else renderCases();
      }
      function signal(text,detail,ok=false){return `<div class="signal"><span class="signal-mark ${ok?'ok':''}" aria-hidden="true">${ok?'✓':'!'}</span><span>${text}<small>${detail}</small></span></div>`;}
      const assessmentLabels={
        AUTO_CHECK_MISSED:'原文与 Catalog 一致；自动检查漏识别',
        CATALOG_CORRECTION:'Catalog 的值需要修改',
        PDF_MISMATCH:'这份 PDF 不是该论文',
        UNSURE:'暂时无法判断'
      };
      function issueForm(issue,label,observed){
        const parser=issue==='PARSER';
        return `<div class="review-issue"><h4>${label}</h4>${observed}<form class="review-form" data-review-form="${issue}">`+
          `<label>你的核对结果<select name="assessment" required><option value="">请选择…</option>`+
          Object.entries(assessmentLabels).map(([key,value])=>`<option value="${key}">${parser&&key==='CATALOG_CORRECTION'?'解析结果需要修正':escapeHtml(value)}</option>`).join('')+`</select></label>`+
          `<label>${issue==='DOI'?'原文中的 DOI／拟修改值':issue==='TITLE'?'原文中的标题／拟修改值':'拟修正的解析内容'}<input name="proposed_value" maxlength="500" placeholder="可从右侧原文选取后粘贴"></label>`+
          `<label>证据所在页<input name="evidence_page" type="number" min="1" placeholder="例如 1"></label>`+
          `<label>原文摘录<textarea name="evidence_quote" maxlength="3000" placeholder="在右侧原文拖选文字，再点击“引用选中文字”"></textarea></label>`+
          `<div class="review-form-actions"><button type="button" data-use-selection="${issue}">引用选中文字</button></div>`+
          `<label>补充说明<textarea name="note" maxlength="4000" placeholder="说明自动检查错在哪里，或 Catalog 需要怎样修改"></textarea></label>`+
          `<div class="review-form-actions"><span class="review-feedback" aria-live="polite"></span><button type="submit">保存这项核对意见</button></div>`+
          `<div class="finding-history" data-finding-history="${issue}">尚未保存人工核对意见。</div></form></div>`;
      }
      function renderPdfTextLayer(){
        const layer=$('pdf-text-layer'),image=$('pdf-image'),layout=currentTextLayout;
        if(!layer||!image||!layout||!image.clientWidth||!layout.width)return;
        const scale=image.clientWidth/layout.width,fragment=document.createDocumentFragment();
        for(const word of layout.words){
          const span=document.createElement('span');
          span.textContent=word.text+' ';
          span.style.left=`${word.x*scale}px`;span.style.top=`${word.y*scale}px`;
          span.style.width=`${word.width*scale}px`;span.style.height=`${word.height*scale}px`;
          span.style.fontSize=`${word.height*scale*.95}px`;
          span.style.lineHeight=`${word.height*scale}px`;
          fragment.appendChild(span);
        }
        layer.replaceChildren(fragment);
      }
      async function loadPdfText(caseId,page){
        const c=reviewCase(caseId),layer=$('pdf-text-layer');
        if(!c?.file_version_id||!layer)return;
        currentTextLayout=null;layer.replaceChildren();
        $('pdf-selection-status').textContent='正在加载可选取的文字…';
        try{
          const layout=await api(`/api/catalog/files/${encodeURIComponent(c.file_version_id)}/pages/${page}/text`);
          if(selectedCase!==caseId||currentPdfPage!==page)return;
          currentTextLayout=layout;renderPdfTextLayer();
          $('pdf-selection-status').textContent=layout.words.length?'在原文上拖选文字，可直接复制或引用为证据。':'本页没有可选文字；扫描件需要 OCR 后才能复制。';
        }catch(error){if(selectedCase===caseId&&currentPdfPage===page)$('pdf-selection-status').textContent=`文字层暂不可用：${errorText(error)}`;}
      }
      async function loadFindings(caseId){
        try{
          const findings=await api(`/api/catalog/review/cases/${encodeURIComponent(caseId)}/findings`);
          if(selectedCase!==caseId)return;
          for(const issue of ['DOI','TITLE','PARSER']){
            const target=document.querySelector(`[data-finding-history="${issue}"]`);
            if(!target)continue;
            const records=findings.filter(f=>f.issue_type===issue);
            target.innerHTML=records.length?records.map((f,i)=>`<div class="finding-item"><strong>${i===0?'最近意见：':'历史意见：'}${escapeHtml(assessmentLabels[f.assessment]||f.assessment)}</strong><br>${escapeHtml(f.proposed_value||'')}${f.evidence_page?` · 第 ${f.evidence_page} 页`:''}<br>${escapeHtml(f.evidence_quote||f.note||'')}<br>${escapeHtml(f.reviewer_label)} · ${escapeHtml(f.created_at.slice(0,16).replace('T',' '))}</div>`).join(''):'尚未保存人工核对意见。';
          }
        }catch(error){if(selectedCase===caseId)document.querySelectorAll('[data-finding-history]').forEach(el=>el.textContent=`无法读取历史意见：${errorText(error)}`);}
      }
      function setPdfPage(number){
        if(!selectedCase||number<1||number>currentPdfPages)return;
        const c=reviewCase(selectedCase);
        if(!c?.file_version_id)return;
        currentPdfPage=number;
        $('pdf-image').src=`/api/catalog/files/${encodeURIComponent(c.file_version_id)}/pages/${number}.png`;
        $('pdf-image').alt=`原文第 ${number} 页`;
        $('pdf-page-count').textContent=`${number} / ${currentPdfPages}`;
        $('pdf-prev').disabled=number===1;
        $('pdf-next').disabled=number===currentPdfPages;
        $('pdf-preview-message').hidden=true;
        loadPdfText(c.case_id,number);
      }
      function showCase(id){
        const c=reviewCase(id);if(!c)return;
        if(c.kind==='PDF_IDENTITY'||(c.kind==='PARSER'&&c.file_version_id)){showPdfReviewCase(c);return;}
        selectedCase=id;renderCases();
        const url=new URL(location.href);
        if(view==='review_queue'){url.searchParams.set('case',id);history.replaceState({},'',url);}
        const matching=matchingCases(),index=matching.findIndex(item=>item.case_id===id);
        const next=index>=0&&index<matching.length-1?matching[index+1]:null;
        const pdfUrl=c.file_version_id?`/api/catalog/files/${encodeURIComponent(c.file_version_id)}/pdf`:null;
        const pdf=c.file_version_id?`<div class="pdf-panel"><div class="pdf-toolbar"><strong>原始 PDF</strong><div class="pdf-controls"><button type="button" id="pdf-prev" aria-label="上一页" disabled>‹</button><span id="pdf-page-count">1 / …</span><button type="button" id="pdf-next" aria-label="下一页" disabled>›</button><button type="button" id="pdf-zoom" aria-label="放大原文">放大</button></div><a href="${pdfUrl}" target="_blank" rel="noopener">打开完整 PDF ↗</a></div><div class="pdf-selection-bar"><span id="pdf-selection-status">正在加载可选取的文字…</span><button type="button" id="copy-selection">复制选中文字</button></div><div class="pdf-preview" id="pdf-preview"><div class="pdf-page"><img id="pdf-image" alt="原文第 1 页" src="/api/catalog/files/${encodeURIComponent(c.file_version_id)}/pages/1.png"><div class="pdf-text-layer" id="pdf-text-layer" aria-label="可选取的原文文字"></div></div><p class="pdf-preview-message" id="pdf-preview-message" hidden>预览暂不可用。请点击“打开完整 PDF”核对原文。</p></div></div>`:
          '<div class="pdf-panel"><div class="pdf-toolbar"><strong>原始 PDF</strong></div><p class="review-note">此审核记录没有可打开的 PDF。请先检查文件获取状态。</p></div>';
        const detail=c.detail;
        const issueCards=c.kind==='PDF_IDENTITY'?
          issueForm('DOI','1 · DOI 核对',signal(detail?.doi_match?'自动识别到 DOI':'自动检查未识别到 DOI',detail?.doi_match?'请仍与论文首页核对。':'在原文中选取 DOI，可说明自动检查漏识别或提出修正。',!!detail?.doi_match))+
          issueForm('TITLE','2 · 标题核对',signal(`标题词重合 ${(Number(detail?.title_token_ratio||0)*100).toFixed(0)}%`,'在原文首页选取正确标题，说明是自动检查误判还是 Catalog 标题需修改。',Number(detail?.title_token_ratio)>=0.6)):
          issueForm('PARSER','解析质量核对',signal('解析任务需要人工介入',escapeHtml(displayValue(detail))));
        const guidance=c.kind==='PDF_IDENTITY'?
          'DOI 与标题分别保存核对结果。核对意见有署名和时间记录；Catalog 的正式值与 PDF 身份状态须经后续复核流程更新。':
          '对照原文的正文、表格及参考文献页，记录缺失或错位的内容及页码证据。';
        $('case-detail').innerHTML=`<div class="review-head"><div><span class="eyebrow">${c.kind==='PDF_IDENTITY'?'PDF identity · NEEDS_REVIEW':'Parser quality · NEEDS_HUMAN'}</span><h2>${escapeHtml(c.title)}</h2><div class="case-meta"><span>${escapeHtml(c.doi||'无 DOI')}</span><span>· ${escapeHtml(c.created_at?.slice(0,10)||'')}</span></div></div><button type="button" data-paper="${escapeHtml(c.paper_id)}">Catalog 详情 ↗</button></div>`+
          `<div class="review-split"><div class="evidence"><div class="review-block"><h3>自动检查与人工修正</h3><label class="reviewer-field">审核人（记录署名）<input id="reviewer-label" maxlength="100" value="${escapeHtml(localStorage.getItem('rstv4-reviewer-label')||'')}" placeholder="填写你的名字或标识"></label>${issueCards}</div>`+
          `<div class="review-block"><h3>Catalog 记录</h3><dl><dt>标题</dt><dd>${escapeHtml(c.title)}</dd><dt>DOI</dt><dd>${escapeHtml(c.doi||'—')}</dd><dt>作者</dt><dd id="review-authors">读取中…</dd><dt>年份</dt><dd id="review-year">读取中…</dd></dl></div>`+
          `<div class="review-block"><h3>人工要核对什么</h3><p>${guidance}</p></div>`+
          `<div class="review-block"><h3>状态回写</h3><div class="review-note">核对意见会保存为有时间和署名的历史记录。保存后不会自动把 PDF 标为 VERIFIED，也不会直接改 Catalog 的 DOI 或标题；正式变更仍需复核。</div></div>`+
          `${next?`<div class="review-block"><button type="button" data-case="${escapeHtml(next.case_id)}">下一条待审核 →</button></div>`:''}</div>${pdf}</div>`;
        currentPdfPage=1;currentPdfPages=1;currentTextLayout=null;lastSelectedText='';
        if(c.file_version_id){
          $('pdf-image').addEventListener('error',()=>{$('pdf-preview-message').hidden=false;});
          $('pdf-image').addEventListener('load',renderPdfTextLayer);
          loadPdfText(id,1);
          api(`/api/catalog/files/${encodeURIComponent(c.file_version_id)}/pdf-info`).then(info=>{
            if(selectedCase!==id)return;
            currentPdfPages=Math.max(1,info.pages||1);
            $('pdf-page-count').textContent=`1 / ${currentPdfPages}`;
            $('pdf-next').disabled=currentPdfPages<=1;
          }).catch(()=>{if(selectedCase===id)$('pdf-page-count').textContent='1 / ?';});
        }
        api('/api/catalog/papers/'+encodeURIComponent(c.paper_id)).then(p=>{
          if(selectedCase!==id)return;
          $('review-authors').textContent=p.authors?.length?p.authors.join(', '):'—';
          $('review-year').textContent=p.published_year||'—';
        }).catch(()=>{if(selectedCase===id){$('review-authors').textContent='暂不可用';$('review-year').textContent='暂不可用';}});
        loadFindings(id);
      }
      function showPdfReviewCase(c){
        if(pdfReviewObserver)pdfReviewObserver.disconnect();
        pdfReviewLoadToken++;pdfReviewLayouts=new Map();latestAnnotations={};pendingPdfSelection=null;
        for(const timer of Object.values(commentSaveTimers))clearTimeout(timer);
        commentSaveTimers={};selectedCase=c.case_id;renderCases();
        const url=new URL(location.href);url.searchParams.set('case',c.case_id);history.replaceState({},'',url);
        const isParser=c.kind==='PARSER';
        const needDoi=!isParser&&!c.detail?.doi_match;
        const needTitle=!isParser&&Number(c.detail?.title_token_ratio??0)<0.6;
        const needs=[needDoi?'DOI':null,needTitle?'标题':null].filter(Boolean);
        const focus=isParser?'对照原文检查解析缺失。选择一条完整的漏掉的参考文献，再点“补充这条参考文献”；复检通过后才会发布新版本。':needs.length?`请核对：${needs.join('、')}。在右侧 PDF 中拖选对应文字，再点“标为 DOI”或“标为标题”。`:
          '自动检查没有指出 DOI 或标题问题；可检查这份 PDF 是否确实属于该论文。';
        const field=(name,value,flag,hint,choice)=>`<div class="identity-field" data-identity-field="${name}">`+
          `<span class="property-name">${name==='DOI'?'DOI':'标题'}</span><strong class="property-value" data-catalog-value="${name}">${escapeHtml(value||'—')}</strong>`+
          `${flag?`<div class="check-hint">${escapeHtml(hint)}</div><div class="annotation-state" data-annotation-state="${name}">尚未核对；可从原文拖选并标注。</div>`+
          `${choice||''}<textarea data-annotation-comment="${name}" maxlength="2000" placeholder="添加批注；离开输入框自动保存"></textarea><span class="comment-status" data-comment-status="${name}"></span>`:''}</div>`;
        $('case-detail').innerHTML=`<div class="review-head"><div><span class="eyebrow">${isParser?'解析质量 · 待人工处理':'PDF 身份 · 待核对'}</span>`+
          `<h2 id="review-case-title">${escapeHtml(c.title)}</h2><div class="case-meta"><span id="review-case-doi">${escapeHtml(c.doi||'无 DOI')}</span><span>· ${escapeHtml(c.created_at?.slice(0,10)||'')}</span></div></div>`+
          `<button type="button" data-paper="${escapeHtml(c.paper_id)}">Catalog 详情 ↗</button></div>`+
          `<div class="review-split"><div class="evidence"><div class="review-block"><h3>人工要核对什么</h3><p>${escapeHtml(focus)}</p></div>`+
          `<div class="review-block"><h3>Catalog 记录与原文批注</h3>`+
          (isParser?`<dl><dt>标题</dt><dd>${escapeHtml(c.title)}</dd><dt>DOI</dt><dd>${escapeHtml(c.doi||'未记录')}</dd></dl><p class="review-note">${escapeHtml(c.detail||'解析需要人工复检')}</p>`:
          field('DOI',c.doi,needDoi,'自动检查未识别到 DOI。',`<button type="button" class="review-choice" data-review-decision="ABSENT">PDF 没有 DOI</button>`)+
          field('TITLE',c.title,needTitle,`标题词重合 ${Math.round(Number(c.detail?.title_token_ratio||0)*100)}%。`,'')+
          `<button type="button" class="review-choice danger" data-review-decision="WRONG_PDF">这份 PDF 不是该论文</button><button type="button" class="review-choice" data-review-decision="REOPEN" hidden>撤回“PDF 不是该论文”判定</button>`)+
          `<p class="review-action-notice" id="review-action-notice" aria-live="polite"></p></div><div class="review-block" id="review-workflow-panel">正在读取复核依据…</div></div>`+
          `<div class="pdf-panel"><div class="pdf-toolbar"><strong>原始 PDF</strong><div class="pdf-controls"><span id="pdf-scroll-position">第 1 页</span><button type="button" id="pdf-scroll-zoom">放大</button></div>`+
          `<a href="/api/catalog/files/${encodeURIComponent(c.file_version_id)}/pdf" target="_blank" rel="noopener">打开完整 PDF ↗</a></div>`+
          `<div class="pdf-selection-bar"><span id="pdf-selection-status">按页加载原文…</span><button type="button" id="copy-selection">复制选中文字</button></div>`+
          `<div class="pdf-preview" id="pdf-preview"><div class="pdf-pages" id="pdf-pages"></div></div></div></div>`+
          `<div class="selection-menu" id="annotation-menu" hidden><div class="selection-preview" id="annotation-preview"></div>`+
          `${needDoi?'<button type="button" data-annotate-field="DOI">标为 DOI（自动核对并修正 Catalog）</button>':''}`+
          `${needTitle?'<button type="button" data-annotate-field="TITLE">标为标题（自动核对并修正 Catalog）</button>':''}${isParser?'<button type="button" data-parser-reference-selection>补充这条参考文献</button>':''}<button type="button" data-discuss-pdf-selection>讨论这段原文／添加讨论批注</button></div>`;
        loadPdfReviewDocument(c);
        if(!isParser)loadPdfReviewAnnotations(c.case_id);
        reviewWorkflow.load(c.case_id).catch(()=>{});
      }
      async function loadPdfReviewDocument(c){
        const token=pdfReviewLoadToken;
        try{
          const info=await api(`/api/catalog/files/${encodeURIComponent(c.file_version_id)}/pdf-info`);
          if(selectedCase!==c.case_id||token!==pdfReviewLoadToken)return;
          currentPdfPages=info.pages;
          $('pdf-pages').innerHTML=info.page_sizes.map((size,index)=>{
            const page=index+1;
            return `<div class="pdf-page" data-pdf-page="${page}" style="aspect-ratio:${size.width}/${size.height}">`+
              `<img alt="原文第 ${page} 页"><div class="pdf-text-layer" aria-label="第 ${page} 页可选文字"></div>`+
              `<span class="page-placeholder">第 ${page} 页</span></div>`;
          }).join('');
          $('pdf-scroll-position').textContent=`第 1 / ${info.pages} 页`;
          const preview=$('pdf-preview');
          preview.addEventListener('scroll',updatePdfScrollPosition,{passive:true});
          if('IntersectionObserver' in window){
            pdfReviewObserver=new IntersectionObserver(entries=>{
              for(const entry of entries)if(entry.isIntersecting)loadPdfReviewPage(c,entry.target,token);
            },{root:preview,rootMargin:'700px 0px'});
            preview.querySelectorAll('[data-pdf-page]').forEach(page=>pdfReviewObserver.observe(page));
          }else preview.querySelectorAll('[data-pdf-page]').forEach(page=>loadPdfReviewPage(c,page,token));
          $('pdf-selection-status').textContent='向下滚动可连续阅读各页；拖选文字后可直接标注。';
        }catch(error){if(selectedCase===c.case_id)$('pdf-selection-status').textContent=`PDF 暂不可预览：${errorText(error)}`;}
      }
      function updatePdfScrollPosition(){
        const preview=$('pdf-preview');if(!preview)return;
        const top=preview.getBoundingClientRect().top+70;
        let current=1;
        for(const page of preview.querySelectorAll('[data-pdf-page]')){
          if(page.getBoundingClientRect().top<=top)current=Number(page.dataset.pdfPage);
          else break;
        }
        $('pdf-scroll-position').textContent=`第 ${current} / ${currentPdfPages} 页`;
      }
      async function loadPdfReviewPage(c,pageEl,token){
        if(pageEl.dataset.loading)return;
        pageEl.dataset.loading='1';
        const page=Number(pageEl.dataset.pdfPage),image=pageEl.querySelector('img');
        image.onload=()=>{pageEl.querySelector('.page-placeholder').hidden=true;renderPdfReviewText(pageEl);};
        image.onerror=()=>{pageEl.querySelector('.page-placeholder').textContent=`第 ${page} 页无法显示`;};
        image.src=`/api/catalog/files/${encodeURIComponent(c.file_version_id)}/pages/${page}.png`;
        try{
          const layout=await api(`/api/catalog/files/${encodeURIComponent(c.file_version_id)}/pages/${page}/text`);
          if(selectedCase!==c.case_id||token!==pdfReviewLoadToken)return;
          pdfReviewLayouts.set(page,layout);renderPdfReviewText(pageEl);
        }catch{if(selectedCase===c.case_id)pageEl.dataset.noText='1';}
      }
      function renderPdfReviewText(pageEl){
        const page=Number(pageEl.dataset.pdfPage),layout=pdfReviewLayouts.get(page);
        const image=pageEl.querySelector('img'),layer=pageEl.querySelector('.pdf-text-layer');
        if(!layout||!image?.complete||!image.naturalWidth||!image.clientWidth)return;
        const scale=image.clientWidth/layout.width,fragment=document.createDocumentFragment();
        layout.words.forEach((word,index)=>{
          const span=document.createElement('span');span.textContent=word.text+' ';
          span.dataset.wordIndex=String(index);
          span.style.left=`${word.x*scale}px`;span.style.top=`${word.y*scale}px`;
          span.style.width=`${word.width*scale}px`;span.style.height=`${word.height*scale}px`;
          span.style.fontSize=`${word.height*scale*.95}px`;span.style.lineHeight=`${word.height*scale}px`;
          fragment.appendChild(span);
        });
        layer.replaceChildren(fragment);applyAnnotationHighlights();
      }
      function applyAnnotationHighlights(){
        for(const page of document.querySelectorAll('[data-pdf-page]')){
          const spans=page.querySelectorAll('.pdf-text-layer span');
          spans.forEach(span=>span.classList.remove('annotated-doi','annotated-title'));
          for(const field of ['DOI','TITLE']){
            const a=latestAnnotations[field];
            if(!a||a.decision!=='FOUND'||a.page_number!==Number(page.dataset.pdfPage))continue;
            for(let index=a.word_start;index<=a.word_end;index++)spans[index]?.classList.add(field==='DOI'?'annotated-doi':'annotated-title');
          }
        }
      }
      function sourceWord(node){
        const element=node?.nodeType===1?node:node?.parentElement;
        return element?.closest?.('.pdf-text-layer span')||null;
      }
      function capturePdfSelection(){
        if(latestAnnotations.PDF?.decision==='WRONG_PDF'){
          $('pdf-selection-status').textContent='请先撤回“PDF 不是该论文”的判定。';return;
        }
        const selection=window.getSelection(),first=sourceWord(selection?.anchorNode),last=sourceWord(selection?.focusNode);
        if(!selection||selection.isCollapsed||!first||!last)return;
        const firstPage=first.closest('[data-pdf-page]'),lastPage=last.closest('[data-pdf-page]');
        if(firstPage!==lastPage){$('pdf-selection-status').textContent='请在同一页内选择完整原文。';return;}
        const start=Math.min(Number(first.dataset.wordIndex),Number(last.dataset.wordIndex));
        const end=Math.max(Number(first.dataset.wordIndex),Number(last.dataset.wordIndex));
        const layout=pdfReviewLayouts.get(Number(firstPage.dataset.pdfPage));if(!layout)return;
        pendingPdfSelection={page_number:Number(firstPage.dataset.pdfPage),word_start:start,word_end:end,
          text:layout.words.slice(start,end+1).map(word=>word.text).join(' ')};
        lastSelectedText=pendingPdfSelection.text;
        const menu=$('annotation-menu');if(!menu)return;
        const looksDoi=/10\.\d{4,9}\//i.test(pendingPdfSelection.text);
        const doiAction=menu.querySelector('[data-annotate-field="DOI"]');
        const titleAction=menu.querySelector('[data-annotate-field="TITLE"]');
        if(doiAction)doiAction.hidden=!looksDoi;
        if(titleAction)titleAction.hidden=looksDoi||pendingPdfSelection.text.split(/\s+/).length<2;
        $('annotation-preview').textContent=`第 ${pendingPdfSelection.page_number} 页 · ${pendingPdfSelection.text}`;
        const rect=selection.getRangeAt(0).getBoundingClientRect();
        menu.style.left=`${Math.max(10,Math.min(window.innerWidth-290,rect.left))}px`;
        menu.style.top=`${Math.max(10,Math.min(window.innerHeight-125,rect.bottom+8))}px`;
        menu.hidden=false;
        $('pdf-selection-status').textContent=`已选第 ${pendingPdfSelection.page_number} 页原文；请选择批注类型。`;
      }
      async function loadPdfReviewAnnotations(caseId){
        try{
          const records=await api(`/api/catalog/review/cases/${encodeURIComponent(caseId)}/annotations`);
          if(selectedCase!==caseId)return;
          latestAnnotations={};
          for(const record of records)if(!latestAnnotations[record.field_name])latestAnnotations[record.field_name]=record;
          for(const field of ['DOI','TITLE']){
            const a=latestAnnotations[field],status=document.querySelector(`[data-annotation-state="${field}"]`);
            if(!status)continue;
            status.classList.toggle('done',!!a);
            status.textContent=!a?'尚未核对；可从原文拖选并标注。':
              a.decision==='REVERTED'?'已撤回：这份 PDF 已标为不是该论文。':
              a.decision==='ABSENT'?'已记录：这份 PDF 没有 DOI。':
              `${a.value_before!==a.value_after?'已修正 Catalog':'已核对原文'} · 第 ${a.page_number} 页 · ${a.selected_text}`;
            const editor=document.querySelector(`[data-annotation-comment="${field}"]`);
            editor.classList.toggle('available',!!a&&a.decision!=='REVERTED');
            if(a&&document.activeElement!==editor)editor.value=a.comment||'';
          }
          const wrong=latestAnnotations.PDF?.decision==='WRONG_PDF';
          document.querySelector('[data-review-decision="WRONG_PDF"]').hidden=wrong;
          document.querySelector('[data-review-decision="REOPEN"]').hidden=!wrong;
          if(wrong)$('review-action-notice').textContent='已记录：这份 PDF 不是该论文。';
          applyAnnotationHighlights();
        }catch(error){if(selectedCase===caseId)$('review-action-notice').textContent=`批注读取失败：${errorText(error)}`;}
      }
      async function savePdfAnnotation(field,decision,range=null,comment=''){
        const caseId=selectedCase,notice=$('review-action-notice');
        if(!caseId||!notice)return;
        notice.textContent='正在自动保存…';notice.classList.remove('error');
        try{
          const saved=await api(`/api/catalog/review/cases/${encodeURIComponent(caseId)}/annotations`,{
            submission_id:crypto.randomUUID(),field_name:field,decision,
            page_number:range?.page_number??null,word_start:range?.word_start??null,
            word_end:range?.word_end??null,comment
          });
          if(selectedCase!==caseId)return;
          const c=reviewCase(caseId);
          c.title=saved.catalog_title;c.doi=saved.catalog_doi;
          $('review-case-title').textContent=c.title;$('review-case-doi').textContent=c.doi||'无 DOI';
          document.querySelector('[data-catalog-value="DOI"]').textContent=c.doi||'—';
          document.querySelector('[data-catalog-value="TITLE"]').textContent=c.title;
          notice.textContent='已自动保存。';
          $('annotation-menu').hidden=true;
          await loadPdfReviewAnnotations(caseId);renderCases();
          reviewWorkflow.load(caseId).catch(()=>{});
          loadSummary();
        }catch(error){notice.textContent=`未保存：${errorText(error)}`;notice.classList.add('error');}
      }
      function scheduleAnnotationComment(field,immediate=false){
        clearTimeout(commentSaveTimers[field]);
        const editor=document.querySelector(`[data-annotation-comment="${field}"]`);
        const a=latestAnnotations[field];if(!a||!editor)return;
        const comment=editor.value.trim();
        if(comment===(a.comment||''))return;
        const save=()=>savePdfAnnotation(field,a.decision,a.decision==='FOUND'?a:null,comment);
        if(immediate)save();else commentSaveTimers[field]=setTimeout(save,700);
      }
      document.addEventListener('pointerdown',event=>{
        const link=event.target.closest('a[data-research-nav],a[data-workspace-nav]');if(!link)return;
        if(view==='overview')overviewList.capture();
        const target=new URL(link.href),current=new URL(location.href);
        if(current.searchParams.get('overview_state'))target.searchParams.set('overview_state',current.searchParams.get('overview_state'));
        link.href=target.href;
      });
      document.addEventListener('click',event=>{
        const link=event.target.closest('a[data-research-nav],a[data-workspace-nav]');
        if(link&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey&&!event.altKey&&event.button===0){
          event.preventDefault();if(view==='overview')overviewList.capture();
          const target=new URL(link.href),current=new URL(location.href);
          if(current.searchParams.get('overview_state'))target.searchParams.set('overview_state',current.searchParams.get('overview_state'));
          history.pushState({},'',target);setView(viewFromUrl(),false);window.scrollTo(0,0);return;
        }
        const t=event.target.closest('button');
        const clickedSection=event.target.closest('[data-discussion-section]');
        if(clickedSection&&!t&&!event.target.closest('a,input,textarea,select')){document.querySelectorAll('.discussion-selected').forEach(el=>el.classList.remove('discussion-selected'));clickedSection.classList.add('discussion-selected');void researchChat.choose(JSON.parse(clickedSection.dataset.discussionSection));return;}
        if(!t)return;
        if(t.dataset.discussionTarget){void researchChat.choose(JSON.parse(t.dataset.discussionTarget));return;}
        if(t.hasAttribute('data-discuss-pdf-selection')){
          const c=reviewCase(selectedCase),selected=pendingPdfSelection,layout=pdfReviewLayouts.get(selected?.page_number);
          if(c&&selected&&layout){const before=layout.words.slice(0,selected.word_start).map(word=>word.text).join(' ');const start=before.length+(selected.word_start?1:0);void researchChat.choose({module:'CATALOG',paper_id:c.paper_id,object_kind:'pdf_page',object_id:c.file_version_id,page_number:selected.page_number},{text:selected.text,start,end:start+selected.text.length,offset_unit:'utf16'});$('annotation-menu').hidden=true;}return;
        }
        if(t.id==='view-trigger'){
          const menu=$('view-menu');menu.hidden=!menu.hidden;t.setAttribute('aria-expanded',String(!menu.hidden));
          for(const panel of ['filter','sort','columns']){$(panel+'-panel').hidden=true;document.querySelector(`[data-panel="${panel}"]`).classList.remove('active');}
        }
        if(t.dataset.view){history.replaceState({},'',RSTV4Overview.clearLiteratureScope(location.href));setView(t.dataset.view);}
        if(t.dataset.panel)togglePanel(t.dataset.panel);
        if(t.dataset.toggleNode)toggleOverviewNode(t.dataset.toggleNode);
        if(t.id==='overview-add-field')researchEditor.open('CREATE_FIELD');
        if(t.dataset.researchOperation)researchEditor.open(t.dataset.researchOperation,overviewList.find(t.dataset.researchKey));
        if(t.dataset.manuscriptId){
          const url=new URL('http://127.0.0.1:3000/');
          url.searchParams.set('manuscript',t.dataset.manuscriptId);
          url.searchParams.set('from','catalog');
          if(t.dataset.trackId)url.searchParams.set('track',t.dataset.trackId);
          location.assign(url.href);
        }
        if(t.dataset.demoPaper){
          const url=new URL('http://127.0.0.1:3000/');
          url.searchParams.set('demo',t.dataset.demoPaper);
          url.searchParams.set('from','catalog');
          location.assign(url.href);
        }
        if(t.dataset.overviewPapers)openOverviewPaperInfo(t.dataset.overviewPapers);
        if(t.dataset.collectionId)openCollectionDetails(t.dataset.collectionId);
        if(t.dataset.demoCollection)openCollectionDetails('',t.dataset.demoCollection);
        if(t.dataset.refreshCollection){openCollectionDetails(t.dataset.refreshCollection);loadResearchOverview();}
        if(t.dataset.moreCollection)openCollectionDetails(t.dataset.moreCollection,'',Number(t.dataset.offset));
        if(t.dataset.collectionControl)controlCollection(t,t.dataset.collectionControl);
        if(t.dataset.retryCollectionJob)controlCollection(t,'retry',t.dataset.retryCollectionJob);
        if(t.dataset.openCollectionReview!==undefined)setView('review_queue');
        if(t.dataset.collectScope)openCollectFor(t);
        if(t.id==='overview-catalog-count'||t.id==='overview-open-catalog'){
          $('paper-drawer').hidden=true;setView('all');window.scrollTo(0,0);
        }
        if(t.id==='open-review')setView('review_queue');
        if(t.id==='open-collect'){collectReturnView=view;setView('collect');}
        if(t.id==='back-catalog')setView('all');
        if(t.id==='collect-back')setView(collectReturnView);
        if(t.dataset.saveCollectionBudget!==undefined)saveCollectionBudget();
        if(t.dataset.compareCollectionBudget!==undefined)collectionProgress.compare();
        if(t.dataset.referencePage!==undefined)collectionProgress.load(collectionProgress.state().id,Number(t.dataset.referencePage)).catch(()=>{});
        if(t.dataset.removeCollectPaper)collectPaperPicker.toggle(t.dataset.removeCollectPaper,false);
        if(t.dataset.collectPaperPage!==undefined)collectPaperPicker.load($('collect-paper-search').value,Number(t.dataset.collectPaperPage)).catch(()=>{});
        if(t.id==='collect-check')checkCollectInput();
        if(t.id==='collect-start'){updateCollectPreview();collectController.start().catch(()=>{});}
        if(t.id==='overview-refresh'){loadResearchOverview();loadSummary();}
        if(t.id==='refresh'){loadSummary();loadResearchOverview();if(view==='review_queue')loadCases();else if(view!=='overview')loadPapers();}
        if(t.id==='prev-page'&&page>1){page--;loadPapers();}
        if(t.id==='next-page'&&result?.has_more){page++;loadPapers();}
        if(t.id==='toggle-scope-excluded'){
          const url=new URL(location.href);url.searchParams.set('scope_excluded',url.searchParams.get('scope_excluded')==='true'?'false':'true');history.pushState({},'',url);page=1;loadPapers();
        }
        if(t.dataset.paper)openPaper(t.dataset.paper);
        if(t.dataset.reviewPaper)setView('review_queue').then(()=>{
          const found=cases.find(c=>c.paper_id===t.dataset.reviewPaper&&c.kind===t.dataset.reviewKind);
          if(found)showCase(found.case_id);
        });
        if(t.id==='close-paper'){deepRead.leave();$('paper-drawer').hidden=true;collectionDetailToken++;collectionDetails=null;paperLoadToken++;}
        if(t.dataset.case)showCase(t.dataset.case);
        if(t.id==='pdf-prev')setPdfPage(currentPdfPage-1);
        if(t.id==='pdf-next')setPdfPage(currentPdfPage+1);
        if(t.id==='pdf-zoom'){
          const zoomed=$('pdf-preview').classList.toggle('zoomed');t.textContent=zoomed?'缩小':'放大';
          requestAnimationFrame(renderPdfTextLayer);
        }
        if(t.id==='pdf-scroll-zoom'){
          const zoomed=$('pdf-preview').classList.toggle('zoomed');t.textContent=zoomed?'缩小':'放大';
          requestAnimationFrame(()=>document.querySelectorAll('[data-pdf-page]').forEach(renderPdfReviewText));
        }
        if(t.dataset.annotateField&&pendingPdfSelection){
          savePdfAnnotation(t.dataset.annotateField,'FOUND',pendingPdfSelection);
        }
        if(t.dataset.reviewDecision==='ABSENT')savePdfAnnotation('DOI','ABSENT');
        if(t.dataset.reviewDecision==='WRONG_PDF')savePdfAnnotation('PDF','WRONG_PDF');
        if(t.dataset.reviewDecision==='REOPEN')savePdfAnnotation('PDF','REOPEN');
        if(t.dataset.parserReferenceSelection!==undefined&&pendingPdfSelection){reviewWorkflow.addSelection(pendingPdfSelection);$('annotation-menu').hidden=true;}
        if(t.dataset.removeParserSelection!==undefined)reviewWorkflow.removeSelection(Number(t.dataset.removeParserSelection));
        if(t.dataset.submitReviewWorkflow)submitReviewWorkflow(t.dataset.submitReviewWorkflow);
        if(t.dataset.retryReviewWorkflow!==undefined)submitReviewWorkflow(null,true);
        if(t.dataset.compareReviewWorkflow!==undefined)reviewWorkflow.compare();
        if(t.dataset.refreshReviewWorkflow!==undefined)reviewWorkflow.load(selectedCase).catch(()=>{});
        if(t.dataset.proposeScientificReview!==undefined)scientificReviewAction('propose');
        if(t.dataset.applyScientificReview)scientificReviewAction('apply',t.dataset.applyScientificReview);
        if(t.dataset.refreshScientificReview!==undefined)scientificReviewAction('refresh');
        if(t.dataset.compareScientificReview!==undefined)scientificReview.compare();
        if(t.id==='copy-selection'){
          if(!lastSelectedText){$('pdf-selection-status').textContent='请先在原文上拖选文字。';return;}
          if(!navigator.clipboard?.writeText){$('pdf-selection-status').textContent='可直接按 Ctrl+C 复制选中文字。';return;}
          navigator.clipboard.writeText(lastSelectedText).then(()=>{
            $('pdf-selection-status').textContent=`已复制 ${lastSelectedText.length} 个字符。`;
          }).catch(()=>{$('pdf-selection-status').textContent='复制未获浏览器许可；可直接按 Ctrl+C。';});
        }
        if(t.dataset.useSelection){
          const form=document.querySelector(`[data-review-form="${t.dataset.useSelection}"]`);
          if(!form)return;
          const feedback=form.querySelector('.review-feedback');
          if(!lastSelectedText){feedback.textContent='请先在右侧原文上拖选文字。';feedback.classList.add('error');return;}
          const quote=form.elements.namedItem('evidence_quote');
          quote.value=[quote.value.trim(),lastSelectedText].filter(Boolean).join('\n');
          form.elements.namedItem('evidence_page').value=currentPdfPage;
          feedback.textContent=`已引用第 ${currentPdfPage} 页的选中文字。`;feedback.classList.remove('error');
        }
        if(t.dataset.addRule){findNode(filter,Number(t.dataset.addRule)).filters.push({type:'rule',id:nextId++,field:'title',operator:'contains',value:''});renderFilter();}
        if(t.dataset.addGroup){findNode(filter,Number(t.dataset.addGroup)).filters.push({type:'group',id:nextId++,operator:'or',filters:[{type:'rule',id:nextId++,field:'pdf_status',operator:'is',value:'NEEDS_REVIEW'}]});renderFilter();loadPapers();}
        if(t.dataset.remove){removeNode(filter,Number(t.dataset.remove));renderFilter();page=1;loadPapers();}
        if(t.dataset.sortAdd){sorts.push({field:'title',direction:'asc'});renderSort();loadPapers();}
        if(t.dataset.sortRemove!==undefined){sorts.splice(Number(t.dataset.sortRemove),1);renderSort();loadPapers();}
        if(t.dataset.columnUp||t.dataset.columnDown){const key=t.dataset.columnUp||t.dataset.columnDown;const ordered=columns.sort((a,b)=>a.order-b.order);const index=ordered.findIndex(c=>c.key===key);const swap=index+(t.dataset.columnUp?-1:1);if(ordered[swap]){[ordered[index].order,ordered[swap].order]=[ordered[swap].order,ordered[index].order];saveColumns();renderColumns();renderTable();}}
        if(t.id==='reset-columns'){columns=defaults.map(c=>({...c}));saveColumns();renderColumns();renderTable();}
      });
      document.addEventListener('mouseup',event=>{
        if(event.target.closest('#pdf-preview')&&document.querySelector('#annotation-menu')){
          requestAnimationFrame(capturePdfSelection);
        }
      });
      document.addEventListener('input',event=>{
        if(event.target.dataset.budgetReason!==undefined)collectionProgress.edit({reason:event.target.value});
        if(event.target.dataset.budgetLimit){const key=event.target.dataset.budgetLimit,raw=event.target.value.trim(),value=raw?Number(raw):null,scale=key==='max_registered_pdf_bytes'?1024**3:key==='max_active_seconds'?3600:1;collectionProgress.edit({limits:{...collectionProgress.state().draft.limits,[key]:value===null?null:Math.round(value*scale)}});}
        if(event.target.id==='scientific-review-reason')scientificReview.edit({reason:event.target.value});
        if(event.target.id==='review-workflow-reason')reviewWorkflow.setReason(event.target.value);
        const field=event.target.dataset.annotationComment;
        if(field)scheduleAnnotationComment(field);
        if(event.target.dataset.collectInput!==undefined){
          updateCollectPreview();
        }
      });
      document.addEventListener('focusout',event=>{
        const field=event.target.dataset.annotationComment;
        if(field)scheduleAnnotationComment(field,true);
      });
      document.addEventListener('submit',async event=>{
        const form=event.target.closest('form[data-review-form]');if(!form)return;
        event.preventDefault();
        const feedback=form.querySelector('.review-feedback'),reviewer=$('reviewer-label').value.trim();
        const data=new FormData(form);
        const assessment=String(data.get('assessment')||'');
        const proposed=String(data.get('proposed_value')||'').trim();
        const quote=String(data.get('evidence_quote')||'').trim();
        const note=String(data.get('note')||'').trim();
        let problem='';
        if(!reviewer)problem='请先填写审核人名字或标识。';
        else if(!assessment)problem='请选择核对结果。';
        else if(assessment==='CATALOG_CORRECTION'&&!proposed)problem='请填写拟修改的正确值。';
        else if(!quote&&!note)problem='请引用原文，或写下你看到的情况。';
        if(problem){feedback.textContent=problem;feedback.classList.add('error');return;}
        const caseId=selectedCase,button=form.querySelector('button[type=submit]');
        const payload={submission_id:crypto.randomUUID(),issue_type:form.dataset.reviewForm,
          assessment,proposed_value:proposed||null,
          evidence_page:data.get('evidence_page')?Number(data.get('evidence_page')):null,
          evidence_quote:quote||null,note:note||null,reviewer_label:reviewer};
        button.disabled=true;feedback.textContent='正在保存…';feedback.classList.remove('error');
        try{
          await api(`/api/catalog/review/cases/${encodeURIComponent(caseId)}/findings`,payload);
          localStorage.setItem('rstv4-reviewer-label',reviewer);
          if(selectedCase===caseId){feedback.textContent='已保存核对意见；Catalog 状态未改变。';await loadFindings(caseId);}
        }catch(error){feedback.textContent=`保存失败：${errorText(error)}`;feedback.classList.add('error');}
        finally{button.disabled=false;}
      });
      document.addEventListener('selectionchange',()=>{
        const selection=window.getSelection(),layer=$('pdf-text-layer');
        if(!selection||selection.isCollapsed||!layer?.contains(selection.anchorNode))return;
        const text=selection.toString().replace(/\s+/g,' ').trim();
        if(!text)return;
        lastSelectedText=text;
        const status=$('pdf-selection-status');
        if(status)status.textContent=`已选 ${text.length} 个字符；可复制或引用为核对证据。`;
      });
      window.addEventListener('resize',renderPdfTextLayer);
      document.addEventListener('change',event=>{
        const t=event.target,d=t.dataset;
        if(d.collectPaper)collectPaperPicker.toggle(d.collectPaper,t.checked);
        if(d.scientificNode){if(!scientificReview.selectNode(d.scientificNode,t.checked)){t.checked=false;return;}const placement=t.closest('.item').querySelector('[data-scientific-section]');if(placement)placement.disabled=!t.checked;}
        if(d.scientificSection&&!scientificReview.placeNode(d.scientificSection,t.value))return;
        if(d.scientificEvidence){if(t.checked&&!scientificReview.state().context.evidence.find(item=>item.evidence_id===d.scientificEvidence)?.source_available){t.checked=false;return;}const ids=new Set(scientificReview.state().draft.evidence_ids);if(t.checked)ids.add(d.scientificEvidence);else ids.delete(d.scientificEvidence);scientificReview.edit({evidence_ids:[...ids]});}
        if(d.groupMode){findNode(filter,Number(d.groupMode)).operator=t.value;page=1;loadPapers();}
        if(d.ruleField){const node=findNode(filter,Number(d.ruleField));node.field=t.value;node.operator=ruleOptions(t.value)[0];node.value='';renderFilter();page=1;loadPapers();}
        if(d.ruleOp){findNode(filter,Number(d.ruleOp)).operator=t.value;renderFilter();page=1;loadPapers();}
        if(d.ruleValue){findNode(filter,Number(d.ruleValue)).value=t.value;page=1;loadPapers();}
        if(d.sortField!==undefined){sorts[Number(d.sortField)].field=t.value;loadPapers();}
        if(d.sortDirection!==undefined){sorts[Number(d.sortDirection)].direction=t.value;loadPapers();}
        if(d.columnVisible){const c=columns.find(x=>x.key===d.columnVisible);if(columns.filter(x=>x.visible).length===1&&!t.checked){t.checked=true;return;}c.visible=t.checked;saveColumns();renderTable();}
        if(d.columnWidth){const c=columns.find(x=>x.key===d.columnWidth);c.width=Math.max(70,Math.min(600,Number(t.value)||130));saveColumns();renderTable();}
        if(t.id==='case-kind')syncCaseSelection();
        if(t.id==='collect-bib-file'&&t.files?.[0]){
          const file=t.files[0];
          if(file.size>5_000_000){$('collect-file-note').textContent='文件超过本版 5 MB 预览上限；请改用较小的 .bib 文件。';return;}
          file.text().then(content=>{$('collect-bibtex').value=content;
            $('collect-file-note').textContent=`已读入 ${file.name}；文件没有上传。`;updateCollectPreview();
          }).catch(error=>{$('collect-file-note').textContent=`无法读取文件：${errorText(error)}`;});
        }
      });
      let collectPaperSearchTimer;
      $('collect-paper-search').addEventListener('input',event=>{if(event.isComposing)return;clearTimeout(collectPaperSearchTimer);collectPaperSearchTimer=setTimeout(()=>collectPaperPicker.load(event.target.value).catch(()=>{}),250);});
      $('case-search').addEventListener('input',syncCaseSelection);
      let filterTimer;
      $('filter-panel').addEventListener('input',event=>{const id=event.target.dataset.ruleValue;if(!id)return;findNode(filter,Number(id)).value=event.target.value;clearTimeout(filterTimer);filterTimer=setTimeout(()=>{page=1;loadPapers();},250);});
      $('paper-head').addEventListener('pointerdown',event=>{
        const key=event.target.dataset.resize;if(!key)return;event.preventDefault();
        const c=columns.find(x=>x.key===key),startX=event.clientX,startWidth=c.width;
        const move=e=>{c.width=Math.max(70,Math.min(600,startWidth+e.clientX-startX));renderTable();};
        const stop=()=>{document.removeEventListener('pointermove',move);document.removeEventListener('pointerup',stop);saveColumns();};
        document.addEventListener('pointermove',move);document.addEventListener('pointerup',stop);
      });
      window.addEventListener('popstate',()=>void setView(viewFromUrl(),false).then(restoreDiscussionLink));
      renderFilter();renderSort();renderColumns();renderTable();loadSummary();void setView(viewFromUrl(),false).then(restoreDiscussionLink);
    })();
  