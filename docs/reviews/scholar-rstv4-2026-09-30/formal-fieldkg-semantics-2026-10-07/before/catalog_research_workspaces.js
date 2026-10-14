/* Selected-Field knowledge and independently owned Track work surfaces. */
(function (root) {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const id = (kind, value) => JSON.stringify([kind, value]);
  const dates = value => { const date = new Date(value); return value && !Number.isNaN(date.getTime()) ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date) : '—'; };
  const badge = value => `<span class="badge">${esc(value || '尚未记录')}</span>`;
  function graphModel(sources, candidates = [], gaps = [], citations = [], evidence = []) {
    const nodes = new Map(), edges = [];
    for (const source of sources) {
      const paper = id('paper', source.paper_id);
      nodes.set(paper, { key: paper, kind: 'paper', label: source.title, record: source });
      for (const unit of source.units) {
        const unitKey = id('unit', unit.unit_id);
        nodes.set(unitKey, { key: unitKey, kind: 'unit', label: unit.raw_text, record: { ...unit, source } });
        edges.push({ key: id('source', unit.unit_id), from: paper, to: unitKey, label: '原文', source: unitKey });
      }
      for (const triplet of source.triplets) {
        const from = id('term', triplet.subject), to = id('term', triplet.object);
        for (const [key, label] of [[from, triplet.subject], [to, triplet.object]]) {
          if (!nodes.has(key)) nodes.set(key, { key, kind: 'concept', label, record: { occurrences: [] } });
          nodes.get(key).record.occurrences.push({ triplet, source });
        }
        edges.push({ key: id('triplet', triplet.triplet_id), from, to, label: triplet.predicate,
          source: id('unit', triplet.unit_id), record: triplet });
      }
    }
    for (const context of candidates) {
      const record = context.record || context, key = id('candidate', record.candidate_id);
      nodes.set(key, { key, kind: 'candidate', label: record.statement, record: context });
      if (nodes.has(id('unit', record.unit_id))) edges.push({ key: id('candidate-source', record.candidate_id), from: id('unit', record.unit_id), to: key, label: record.relation, source: id('unit', record.unit_id) });
    }
    for (const record of evidence) {
      const key = id('evidence', record.evidence_id);
      nodes.set(key, { key, kind: 'evidence', label: record.statement, record });
    }
    for (const context of gaps) {
      const record = context.record || context, key = id('gap', record.candidate_gap_id);
      nodes.set(key, { key, kind: 'gap', label: record.statement, record: context });
      for (const reference of context.references || []) {
        const referenceId = reference.record?.candidate_id || reference.record?.evidence_id;
        const from = id(reference.kind, referenceId);
        if (nodes.has(from)) edges.push({ key: id('gap-reference', [record.candidate_gap_id, referenceId]), from, to: key, label: '候选依据', source: from });
      }
    }
    for (const record of citations) {
      const from = id('paper', record.citing_paper_id), to = id('paper', record.cited_paper_id);
      if (nodes.has(from) && nodes.has(to)) edges.push({ key: id('citation', record.citation_id), from, to, label: record.role || '引用', record });
    }
    return { nodes: [...nodes.values()], edges };
  }

  function buildStages(build) {
    const sourceCount = build.sources.length;
    return [
      ['COLLECTING', '采集', build.retrieval_scope?.source === 'EXISTING_PAPERSKELETON' ? '复用已选来源' : '未记录此步产物'],
      ['DOWNLOADING', '下载', build.sources.every(s => s.pdf_digest) && sourceCount ? '已有文件摘要；获取运行未记录' : '文件获取状态未知'],
      ['PARSING', '解析', sourceCount ? '复用原文结构；独立解析运行可能未知' : '缺少原文结构'],
      ['BUILDING_SKELETON', 'Skeleton', sourceCount ? `${sourceCount} 个固定 Skeleton` : '缺少 Skeleton'],
      ['FORGING_FIELDKG', 'Forge', build.sources.some(s => s.triplets.length) ? '来源三元组可回查；Forge 运行未记录' : '无三元组／Forge 运行记录'],
      ['EXTRACTING_EVIDENCE', 'Evidence', `${build.evidence_candidates.length} 个机器候选${build.semantic_coverage?.unclassified_units.length ? `；${build.semantic_coverage.unclassified_units.length} 个来源单元缺结构化 Intent，不能密封` : ''}`],
      ['DETECTING_GAPS', 'Gaps', `${build.candidate_gaps.length} 个候选 Gap`],
      ['READY_FOR_REVIEW', '待审阅', build.status === 'READY_FOR_REVIEW' || build.status === 'SEALED' ? '已明确进入审阅' : '尚未进入'],
      ['SEALED', '密封', build.status === 'SEALED' ? '已有固定快照' : '尚未密封'],
    ].map(([key, label, detail]) => ({ key, label, detail, current: build.status === key }));
  }

  function snapshotGraph(snapshot) {
    const sources = snapshot.sources || [];
    const candidates = (snapshot.manifest.reviewed_candidates || []).map(record => ({ record }));
    const gaps = (snapshot.frozen_candidate_gaps || []).map(record => ({ record, references: snapshot.manifest.gap_references?.[record.candidate_gap_id] || [] }));
    const evidence = (snapshot.frozen_evidence || []).map(record => ({ ...record, location: record.location || JSON.parse(record.location_json || '{}') }));
    return graphModel(sources, candidates, gaps, snapshot.manifest.citations || [], evidence);
  }

  function section(title, html) { return `<section class="research-section"><h2>${esc(title)}</h2>${html}</section>`; }
  function objectButton(node) { return `<button type="button" class="research-object" data-research-select="${esc(node.key)}"><span>${esc(node.kind)}</span> ${esc(node.label)}</button>`; }
  function sourceHtml(source) {
    return `<p><strong>${esc(source.title)}</strong> · Paper v${esc(source.paper_version)} · Skeleton v${esc(source.version)}</p><p class="small">文件版本：${esc(source.file_version_id || '未知')} · 解析版本：${esc(source.parse_run_id || '未知')}<br>原文摘要：${esc(source.parsed_digest || '未知')} · PDF 摘要：${esc(source.pdf_digest || '未知')}<br>模型：${esc(source.extractor_model || '未知')} · 契约：${esc(source.prompt_version || '未知')}</p><a href="/?view=all&paper=${encodeURIComponent(source.paper_id)}" data-research-nav>回查目录论文</a>`;
  }
  function graphHtml(model) {
    const shown = model.nodes.slice(0, 90), keys = new Set(shown.map(node => node.key));
    const positions = new Map(shown.map((node, i) => [node.key, { x: 30 + (i % 3) * 290, y: 25 + Math.floor(i / 3) * 105 }]));
    const edges = model.edges.filter(edge => keys.has(edge.from) && keys.has(edge.to));
    if (!shown.length) return '<p>此范围尚无图谱对象。可选择真实 PaperSkeleton 创建 Build。</p>';
    return `<div class="research-graph-scroll"><svg width="890" height="${Math.max(130, Math.ceil(shown.length / 3) * 105)}" role="group" aria-label="当前范围的来源、概念、候选与证据关系；相同对象也可在下方列表选择"><g fill="none" stroke="#9db8cf" stroke-width="1.5">${edges.map(edge => { const a = positions.get(edge.from), b = positions.get(edge.to); return `<path d="M ${a.x + 125} ${a.y + 34} L ${b.x + 125} ${b.y + 34}"/>`; }).join('')}</g>${shown.map(node => { const p = positions.get(node.key); return `<foreignObject x="${p.x}" y="${p.y}" width="250" height="75"><div xmlns="http://www.w3.org/1999/xhtml">${objectButton(node)}</div></foreignObject>`; }).join('')}</svg></div>${model.nodes.length > 90 ? '<p>图中显示前 90 个对象；完整对象与关系在下方列表中。</p>' : ''}`;
  }
  function categoryRows(model, sources) {
    const kinds = [['Papers', 'paper'], ['Concepts', 'concept'], ['原文单元', 'unit'], ['Evidence Candidates', 'candidate'], ['Candidate Gaps', 'gap'], ['已接受 Evidence', 'evidence']];
    const list = kinds.map(([label, kind]) => section(label, model.nodes.filter(node => node.kind === kind).map(objectButton).join('') || '<p>此范围尚无记录。</p>')).join('');
    const methods = sources.flatMap(source => source.units.filter(unit => /Method/i.test(unit.layer3?.intent || '')).map(unit => ({ key: id('unit', unit.unit_id), kind: unit.layer3.intent, label: unit.raw_text })));
    const opposing = model.nodes.filter(node => ['CONTRADICTS', 'OPPOSES', 'COUNTEREVIDENCE'].includes((node.record.record || node.record).relation));
    return list + section('来源版本', sources.map(source => `<article class="item">${sourceHtml(source)}</article>`).join('') || '<p>此范围暂无来源版本。</p>') + section('Methods（来源 Intent）', methods.map(objectButton).join('') || '<p>未记录带 Method Intent 的来源单元。</p>') + section('Findings / Counterevidence', opposing.map(objectButton).join('') || '<p>已接受 Evidence 可在上方查看；当前未记录独立反证。</p>') + section('Debates / Idea Mergers', '<p>当前权威数据尚无独立争论或 Idea Merger 对象；不能由三元组自动推断。此部分仍待接通。</p>');
  }

  function createWorkspace({ host, dialog, storage, location, history, request, overviewCapture, returnOverview, openPaper, draftNamespace, selectDiscussion = () => {} }) {
    let data = null, model = { nodes: [], edges: [] }, serial = 0, pending = null, pendingKey = '', sending = false, needsComparison = false;
    const form = dialog.querySelector('form'), body = dialog.querySelector('[data-fieldkg-action-body]'), status = dialog.querySelector('[role="status"]');
    const submit = form.querySelector('[type="submit"]');
    const trackDecisions = root.CatalogTrackDecisions?.mount({ host, api: request, storage, namespace: `rstv4-track-scientific-v1:${location.origin}:${draftNamespace}`, onChanged: () => show('track'), onNode: nodeId => nodeDetail(id('node', nodeId)) });
    function researchUrl(view, field, track, snapshot) {
      const url = new URL(location.href); url.searchParams.set('view', view);
      for (const [name, value] of [['field', field], ['track', track], ['snapshot', snapshot]]) {
        if (value) url.searchParams.set(name, value); else url.searchParams.delete(name);
      }
      url.searchParams.delete('research_object'); return url.href;
    }
    function writePending() {
      try { storage.setItem(pendingKey, JSON.stringify(pending)); return true; } catch { return false; }
    }
    function actionDialog(payload, title, summary, reasonRequired = false) {
      pendingKey = `rstv4-fieldkg-action-v1:${location.origin}:${draftNamespace}:${id(payload.operation, payload.object_id || payload.build_id || payload.track_id || payload.field_id)}`;
      let saved; try { saved = JSON.parse(storage.getItem(pendingKey)); } catch { /* unavailable draft */ }
      pending = saved || { payload: { ...payload, request_id: root.crypto.randomUUID(), confirmed: true }, reasonRequired, draftReason: '', submitted: false };
      needsComparison = !!saved && !saved.submitted && (saved.payload.expected_context_sha256 !== payload.expected_context_sha256 || saved.payload.expected_snapshot_digest !== payload.expected_snapshot_digest || saved.payload.decision !== payload.decision || saved.payload.snapshot_id !== payload.snapshot_id || JSON.stringify(saved.payload.sources) !== JSON.stringify(payload.sources));
      dialog.querySelector('h2').textContent = title;
      body.innerHTML = `<p>${esc(summary)}</p>${reasonRequired ? `<label>审阅理由<textarea name="rationale" required maxlength="8000" autocomplete="off">${esc(pending.draftReason)}</textarea></label>` : ''}<p>只执行这里列出的操作。Candidate Gap 仍是候选；采用 Snapshot 不批准科研决定。</p>`;
      if(saved)body.innerHTML+=`<details><summary>原草稿／提交的固定对象与版本</summary><pre>${esc(JSON.stringify(saved.payload,null,2))}</pre></details>`;
      if(saved?.submitted)body.innerHTML+=`<p role="alert">将核对原提交：${esc(saved.payload.operation)} ${esc(saved.payload.decision || '')} · ${esc(saved.payload.object_id || saved.payload.build_id || saved.payload.snapshot_id || saved.payload.field_id)}。本次只会重试这份原请求。</p>`;
      if(needsComparison){
        const comparison=dialog.ownerDocument.createElement('div');
        comparison.innerHTML='<p>原草稿的对象或来源已改变，请比较当前资料与原记录。</p><button type="button">已比较，使用当前对象版本继续</button>';
        comparison.querySelector('button').addEventListener('click',()=>{
          pending.payload={...payload,request_id:root.crypto.randomUUID(),confirmed:true};needsComparison=false;writePending();comparison.remove();submit.disabled=false;
          status.textContent='已采用当前版本作为比较基准，请再次核对后确认。';
        });body.append(comparison);
      }
      status.textContent = pending.submitted ? '上次提交结果尚未确认；将核对原请求，避免重复操作。' : '请先核对固定对象与版本，再明确确认。';
      submit.textContent = pending.submitted ? '核对原提交' : '确认此操作';
      submit.disabled=needsComparison;
      for (const input of body.querySelectorAll('textarea')) input.disabled = pending.submitted;
      dialog.showModal();
    }
    function nodeDetail(key) {
      const node = model.nodes.find(item => item.key === key) || model.edges.find(item => item.key === key);
      if (!node) return;
      const [kind, value] = JSON.parse(key);
      selectDiscussion(data.track ? {module:'TRACK',track_id:data.track.track_id,field_id:data.track.field_id,object_kind:kind,object_id:value} : {module:'FIELDKG',field_id:data.field.field_id,object_kind:kind==='term'?'concept':model.edges.some(item=>item.key===key)?'relationship':kind,object_id:kind==='term'?value:model.edges.some(item=>item.key===key)?key:value,snapshot_id:data.selected_snapshot?.snapshot_id||null});
      const url = new URL(location.href); url.searchParams.set('research_object', key); history.replaceState(history.state, '', url);
      host.querySelectorAll('[data-research-select]').forEach(el => { el.classList.toggle('selected', el.dataset.researchSelect === key); el.setAttribute('aria-pressed', String(el.dataset.researchSelect === key)); });
      const details = host.querySelector('[data-research-detail]');
      const record = node.record?.record || node.record || {};
      let source = node.record?.source;
      if (node.kind === 'paper') source = record;
      if (node.kind === 'unit') source = record.source;
      if (node.kind === 'candidate') source = node.record.source;
      const activeSources = data.selected_snapshot ? data.selected_snapshot.sources : data.sources || [];
      const origin = model.nodes.find(item => item.key === node.source);
      if (origin?.kind === 'unit') source = origin.record.source;
      const knownSource = source || activeSources.find(s => s.units.some(unit => unit.unit_id === (record.unit_id || record.location?.unit_id)));
      let html = `<button type="button" data-source-close aria-label="关闭研究来源详情">关闭</button><h2>${esc(node.label || node.key)}</h2><p>${badge(record.status)} · ${esc(node.kind || '关系')}</p>`;
      if (record.raw_text || record.excerpt) html += `<blockquote>${esc(record.raw_text || record.excerpt)}</blockquote>`;
      if (node.kind === 'concept') html += record.occurrences.map(item => { const raw = item.source.units.find(unit => unit.unit_id === item.triplet.unit_id); return `<p>${esc(item.triplet.subject)} → ${esc(item.triplet.predicate)} → ${esc(item.triplet.object)}</p>${raw ? `<blockquote>${esc(raw.raw_text)}</blockquote><p>页标记 ${esc(raw.page_idx ?? '未知')} · 序号 ${raw.seq_idx}</p>` : ''}${sourceHtml(item.source)}`; }).join('');
      if (origin?.kind === 'unit' && !record.raw_text && !record.excerpt) html += `<blockquote>${esc(origin.record.raw_text)}</blockquote>`;
      if (knownSource) html += sourceHtml(knownSource);
      const unit = knownSource?.units.find(item => item.unit_id === (record.unit_id || record.location?.unit_id || origin?.record.unit_id));
      if (unit) html += `<p>来源页标记：${esc(unit.page_idx ?? '未知')} · ${esc(unit.section || '章节未知')} · 序号 ${unit.seq_idx}</p><details><summary>Layer 1–4 与原文版本</summary><pre>${esc(JSON.stringify({ layer1: unit.layer1, layer2: unit.layer2, layer3: unit.layer3, layer4: unit.layer4, content_digest: unit.content_digest }, null, 2))}</pre></details>`;
      if (node.kind === 'gap') html += `<p>来源理由：${esc(record.rationale)}</p><p>条件：${esc(JSON.parse(record.conditions_json || '[]').join('；') || '未记录')}</p>${(node.record.references || []).map(ref => ref.record?`<button type="button" data-research-select="${esc(id(ref.kind,ref.record.candidate_id||ref.record.evidence_id))}">${esc(ref.kind)} · ${esc(ref.record.statement)}</button>`:`<p>来源不可用：${esc(ref.id)}</p>`).join('')}<p>这不是 Track 内已获批准的 Gap。</p>`;
      if(record.node_id)html+=(data.node_evidence||[]).filter(link=>link.node_id===record.node_id).map(link=>data.evidence.find(e=>e.evidence_id===link.evidence_id)).filter(Boolean).map(e=>`<p>${esc(e.statement)}</p><blockquote>${esc(e.excerpt)}</blockquote><pre>${esc(JSON.stringify(e.location,null,2))}</pre>`).join('');
      if ((node.kind === 'candidate' || node.kind === 'gap') && record.status === 'PROPOSED' && !data.selected_snapshot) {
        html += `<div class="research-actions"><button type="button" data-review-key="${esc(key)}" data-review-decision="ACCEPTED">接受候选</button><button type="button" data-review-key="${esc(key)}" data-review-decision="REJECTED">拒绝候选</button></div>`;
      }
      if (record.location) html += `<pre>${esc(JSON.stringify(record.location, null, 2))}</pre>`;
      if (record.node_id || record.edge_id) html += `<details><summary>科研对象与关系的原始记录</summary><pre>${esc(JSON.stringify(record, null, 2))}</pre></details>`;
      details.innerHTML = html; details.hidden = false;
      const close = details.querySelector('[data-source-close]');
      function closeDetail() { details.hidden = true; const current = new URL(location.href); current.searchParams.delete('research_object'); history.replaceState(history.state, '', current); let restored = false; host.querySelectorAll('[data-research-select]').forEach(el => { if (el.dataset.researchSelect === key) { el.setAttribute('aria-pressed', 'false'); el.classList.remove('selected'); if (!restored) { el.focus(); restored = true; } } }); }
      close.addEventListener('click', closeDetail);
      details.onkeydown = event => { if (event.key === 'Escape') { event.preventDefault(); closeDetail(); } };
      close.focus();
    }
    function fieldHtml() {
      const snapshot = data.selected_snapshot;
      const sources = snapshot ? snapshot.sources : data.sources;
      model = snapshot ? snapshotGraph(snapshot) : graphModel(sources, data.candidates, data.candidate_gaps, data.citations, data.evidence);
      const builds = data.builds.map(build => `<article class="research-build"><h3>${esc(build.build_id)}</h3><p>${badge(build.status)} · revision ${build.revision} · ${dates(build.updated_at)}</p><ol class="research-stages">${buildStages(build).map(stage => `<li class="${stage.current ? 'current' : ''}"><strong>${stage.label}</strong><span>${esc(stage.detail)}</span></li>`).join('')}</ol><p>${build.papers.map(paper => `${esc(paper.status)} ${esc(paper.detail || '')}`).join('；')}</p>${build.semantic_coverage?.unclassified_units.length ? `<details open><summary>来源语义未完成，需明确重新深读</summary><p>原模型描述不等于结构化分类，原结果保持。请进入该论文详情，选择原解析版本并重新深读，再选择新 Skeleton 创建 Build。</p>${build.semantic_coverage.unclassified_units.map(item => `<p>单元 ${esc(item.unit_id)}</p><blockquote>${esc(item.raw_text)}</blockquote><pre>${esc(JSON.stringify(item.layer3,null,2))}</pre><a href="/?view=all&paper=${encodeURIComponent(build.sources.find(s=>s.skeleton_id===item.skeleton_id)?.paper_id||'')}">回到原论文详情</a>`).join('')}</details>` : ''}${build.status !== 'SEALED' ? `<button type="button" data-build-ready="${esc(build.build_id)}">进入审阅</button> <button type="button" data-build-seal="${esc(build.build_id)}">密封 Snapshot</button>` : ''}</article>`).join('');
      const notice = snapshot ? `Snapshot v${snapshot.version} · ${snapshot.digest_matches && snapshot.members_match ? '摘要与成员清单一致' : '摘要或成员清单不符，停止采用'} · ${snapshot.source_records_available ? '保留当时来源记录' : '旧快照未保存完整来源副本'}` : '当前 Field 的权威记录；Living 更新不会自动更换 Track 已采用的 Snapshot。';
      const versions = data.snapshots.map(s => `<a href="${esc(researchUrl('fieldkg', data.field.field_id, null, s.snapshot_id))}" data-research-nav>Snapshot v${s.version}</a>`).join('');
      const relations = model.edges.map(edge => `<button type="button" class="research-edge" data-research-select="${esc(edge.key)}">${esc(model.nodes.find(n => n.key === edge.from)?.label || edge.from)} → ${esc(edge.label)} → ${esc(model.nodes.find(n => n.key === edge.to)?.label || edge.to)}</button>`).join('');
      const projection = data.projection.outbox.map(item => `<p>${esc(item.aggregate_type)} · ${badge(item.status)} · 重试 ${item.attempts} · ${esc(item.last_error || '')}</p>`).join('');
      const tracks = data.tracks.map(t => `<a class="research-link" href="${esc(researchUrl('track', data.field.field_id, t.track.track_id))}" data-research-nav>${esc(t.track.title)}</a>`).join('');
      return [
        `<header class="research-head"><div><p class="eyebrow">FieldKG · ${snapshot ? '固定 Snapshot' : 'Living'}</p><h1>${esc(data.field.name)}</h1><p>${esc(data.field.description || '')}</p></div>${snapshot ? '' : '<button type="button" data-build-create>从已保存 Skeleton 创建 Build</button>'}</header>`,
        `<p class="status-line" role="status">${notice}</p><nav class="research-tabs" aria-label="FieldKG 版本"><a href="${esc(researchUrl('fieldkg', data.field.field_id))}" data-research-nav>Living</a>${versions}</nav>`,
        section('来源复核记录', sourceReviewHtml()),
        section('图谱', graphHtml(model)), section('对象与来源列表', categoryRows(model, sources)),
        section('关系 / Citation Network', relations || '<p>此范围尚无关系记录。</p>'),
        snapshot ? section('固定依据与采用记录', `<p>摘要：${esc(snapshot.content_digest)}</p><p>${snapshot.adoptions.map(a => `${esc(a.title)} · ${dates(a.adopted_at)}`).join('<br>') || '尚未被 Track 采用。'}</p><details><summary>固定成员清单</summary><pre>${esc(JSON.stringify(snapshot.members, null, 2))}</pre></details>`) : section('Build / Pipeline', builds || '<p>此 Field 尚无 Build。</p>'),
        section('查询投影', `<p>实时服务健康：尚未探测。权威资料仍在 RSTV4。</p>${projection || '<p>此 Field 尚无待同步记录。</p>'}`),
        section('该 Field 的 Tracks', tracks || '<p>尚无 Track。</p>'),
        '<aside class="research-source-detail" aria-label="来源详情" data-research-detail hidden></aside>',
      ].join('');
    }
    function sourceReviewHtml() {
      return (data.source_reviews || []).map(review => `<article class="item"><strong>原来源需要重新审视</strong><p>${esc(review.reason)}</p><p>文件当前：${esc(review.current_file_status)} · ${review.impact.affected_manuscripts.length} 份稿件受影响。旧版本与原批准记录保留；文件复核不会自动批准科研决定。</p><a href="/?view=review&case=${encodeURIComponent(review.case_id)}">查看原文件复核记录</a></article>`).join('') || '<p>没有来源撤回记录。</p>';
    }
    function trackHtml() {
      model = { nodes: data.nodes.map(record => ({ key: id('node', record.node_id), kind: record.node_type, label: record.statement, record })), edges: data.edges.map(record => ({ key: id('edge', record.edge_id), from: id('node', record.source_node_id), to: id('node', record.target_node_id), label: record.relation, record })) };
      const milestones = ['SCOPE', 'SNAPSHOT_ADOPTION', 'GAP', 'IDEA', 'RESEARCH_QUESTION', 'HYPOTHESIS', 'METHOD', 'EXPERIMENT', 'CLAIM'];
      const snapshotRows = data.available_snapshots.map(s => { const adopted = data.adoptions.find(a => a.snapshot_id === s.snapshot_id); return `<div class="item"><a href="${esc(researchUrl('fieldkg', data.track.field_id, null, s.snapshot_id))}" data-research-nav>Snapshot v${s.version}</a> · ${badge(s.status)} ${adopted ? `已明确采用 · ${dates(adopted.adopted_at)}` : `<button type="button" data-adopt-snapshot="${esc(s.snapshot_id)}">明确采用此版本</button>`}</div>`; }).join('');
      return `<header class="research-head"><div><p class="eyebrow">${esc(data.field?.name || 'Field 待映射')} / Track</p><h1>${esc(data.track.title)}</h1><p>${badge(data.track.status)} · ${esc(data.track.research_type)} · revision ${data.track.revision}</p></div></header>${section('Scope', `<p>${esc(data.track.scope || '尚未设置研究范围。')}</p><p>${esc(data.track.mapping_status)}</p>`)}${section('来源复核记录', sourceReviewHtml())}${section('采用的 Snapshot', snapshotRows || '<p>该 Field 尚无 Snapshot；没有推断固定研究基础。</p>')}${section('科研里程碑', `<div class="research-milestones">${milestones.map(name => { const item = data.milestones.find(m => m.milestone === name); return `<div><strong>${name}</strong>${badge(item?.status)}<span>${esc(item?.blocker || '')}</span></div>`; }).join('')}</div>`)}${section('Research Graph', graphHtml(model) + model.nodes.map(objectButton).join('') + model.edges.map(edge => `<button type="button" class="research-edge" data-research-select="${esc(edge.key)}">${esc(edge.from)} → ${esc(edge.label)} → ${esc(edge.to)}</button>`).join(''))}${section('科研操作', '<div data-track-scientific></div>')}${section('科研审阅提案', data.decisions.map(d => `<div class="item"><p>${esc(d.kind)} · ${badge(d.status)} · revision ${d.expected_revision}</p><p>批准用语：${esc(d.approval_phrase)}</p><p>${esc(d.rejection_reason || d.confirmation_text || '尚无批准／拒绝记录。')}</p></div>`).join('') || '<p>尚无提案。讨论和 Snapshot 采用均不构成科学批准。</p>')}${section('Projects（各自唯一 Owner Track）', data.projects.map(p => `<article class="item"><h3>${esc(p.title)}</h3><p>${badge(p.status)} · ${esc(p.scope || '范围尚未设置')}</p><details><summary>目标／数据／时间与实施内容</summary><pre>${esc(JSON.stringify(p.type_payload, null, 2))}</pre></details><h4>计划与执行</h4>${data.plans.filter(plan => plan.project_id === p.project_id).map(plan => `<p>${badge(plan.status)} · Method ${esc(plan.method_node_id)} · ${esc(plan.argv.join(' '))} · 脚本摘要 ${esc(plan.script_sha256 || '未知')}</p>`).join('') || '<p>尚无计划。</p>'}${data.runs.filter(run => run.project_id === p.project_id).map(run => `<details><summary>${esc(run.operation)} · ${esc(run.status)} · ${dates(run.updated_at)}</summary><pre>${esc(JSON.stringify(run.detail, null, 2))}</pre></details>`).join('')}</article>`).join('') || '<p>此 Track 暂无 Project；综述／概念研究可以没有 Project。</p>')}${section('Track 证据', data.evidence.map(e => `<article class="item"><p>${esc(e.statement)}</p><blockquote>${esc(e.excerpt)}</blockquote><p>${esc(e.scope_kind)} · ${esc(e.relation)} · ${esc(e.paper_version_id || e.experiment_run_id || '来源版本未知')}</p><pre>${esc(JSON.stringify(e.location, null, 2))}</pre></article>`).join('') || '<p>尚无证据记录。</p>')}${section('Manuscripts / 投稿事件', data.manuscripts.map(ms => { const url = new URL('http://127.0.0.1:3000/'); url.searchParams.set('manuscript', ms.manuscript_id); url.searchParams.set('from', 'catalog'); url.searchParams.set('track', ms.track_id); const back = new URL(location.href); back.searchParams.delete('view'); back.searchParams.delete('field'); back.searchParams.delete('snapshot'); back.searchParams.delete('research_object'); url.searchParams.set('return', back.href); return `<article class="item"><a href="${esc(url.href)}">${esc(ms.title)} ↗</a> <a href="/?view=scientific_review&manuscript=${encodeURIComponent(ms.manuscript_id)}">重审与替换当前依据</a><p>${badge(ms.workflow_stage)} · 写作记录 ${esc(ms.writing_status)} · ${ms.needs_scientific_review ? '需要科学复核' : '未标记科学复核'}</p><p>${esc(ms.blocker || '')} ${esc(ms.next_step || '')}</p>${data.submission_events.filter(e => e.manuscript_id === ms.manuscript_id).map(e => `<p>${esc(e.venue)} · Round ${e.round} · ${badge(e.status)} · ${dates(e.created_at)}</p>`).join('')}</article>`; }).join('') || '<p>此 Track 暂无稿件。</p>')}<aside class="research-source-detail" data-research-detail hidden></aside>`;
    }
    async function show(view) {
      const token = ++serial, params = new URL(location.href).searchParams;
      trackDecisions?.leave();
      data = null; model = { nodes: [], edges: [] };
      host.innerHTML = '<p class="status-line" role="status">正在读取固定研究范围…</p>';
      try {
        const fieldId = params.get('field'), trackId = params.get('track');
        if (view === 'fieldkg' && !fieldId) {
          const overview = await request('/api/catalog/research-overview');
          if (token !== serial) return;
          host.innerHTML = section('选择一个 Field', overview.fields.map(field => `<a class="research-link" href="${esc(researchUrl('fieldkg', field.field_id))}" data-research-nav>${esc(field.name)}</a>`).join('') || '<p>尚无 Field。返回研究总览先新增。</p>');
          return;
        }
        const loaded = await request(view === 'track' ? `/api/catalog/tracks/${encodeURIComponent(trackId || '')}/workspace` : `/api/catalog/fields/${encodeURIComponent(fieldId)}/workspace${params.get('snapshot') ? `?snapshot=${encodeURIComponent(params.get('snapshot'))}` : ''}`);
        if (token !== serial) return;
        data = loaded;
        host.innerHTML = view === 'track' ? trackHtml() : fieldHtml();
        selectDiscussion(view==='track'?{module:'TRACK',track_id:data.track.track_id,field_id:data.track.field_id,object_kind:'track',object_id:data.track.track_id}:data.selected_snapshot?{module:'FIELDKG',field_id:data.field.field_id,object_kind:'snapshot',object_id:data.selected_snapshot.snapshot_id,snapshot_id:data.selected_snapshot.snapshot_id}:{module:'FIELDKG',field_id:data.field.field_id,object_kind:'field',object_id:data.field.field_id},false);
        if (params.get('research_object')) nodeDetail(params.get('research_object'));
        if (view === 'track' && trackDecisions) { try { await trackDecisions.load(data.track.track_id); } catch { /* The scientific panel shows its own read failure. */ } }
      } catch (error) { if (token === serial) host.innerHTML = `<p role="alert">${esc(error.message)}。可以更新状态或返回总览，当前资料未被修改。</p>`; }
    }
    async function chooseBuild() {
      const token = serial, field = data.field;
      let sources;
      try { sources = (await request('/api/catalog/research/skeletons')).sources; }
      catch (error) {
        if (token === serial) { const message = host.ownerDocument.createElement('p'); message.setAttribute('role', 'alert'); message.textContent = `无法读取来源：${error.message}。可以重试；尚未创建 Build。`; host.prepend(message); }
        return;
      }
      if (token !== serial) return;
      const picker = host.ownerDocument.createElement('section'); picker.className = 'research-section';
      picker.innerHTML = `<h2>选择已保存的原文与 Skeleton 版本</h2><p>这里明确从全部目录中选择输入；不会自动扩大当前 Field 的查询范围。</p><form data-build-picker>${sources.map(source => `<label class="research-source-choice"><input type="checkbox" name="source" value="${esc(source.skeleton_id)}">${esc(source.title)} · Paper v${source.paper_version} · Skeleton v${source.version}</label>`).join('') || '<p>目录中尚无可用 Skeleton。完整采集与解析入口仍须接通。</p>'}<button type="submit">核对所选来源并创建</button><button type="button" data-picker-close>关闭</button></form>`;
      host.prepend(picker);
      picker.querySelector('[data-picker-close]').addEventListener('click', () => picker.remove());
      picker.querySelector('form').addEventListener('submit', event => {
        event.preventDefault(); const selected = [...new FormData(event.target).getAll('source')];
        if (!selected.length) return;
        const chosen = Object.fromEntries(sources.filter(source => selected.includes(source.skeleton_id)).map(source => [source.skeleton_id, source.context_sha256]));
        if (token !== serial) return;
        actionDialog({ operation: 'CREATE_BUILD', field_id: field.field_id, sources: chosen }, '确认创建 Build', `Field：${field.name}；复用 ${selected.length} 个固定 Skeleton。`);
      });
    }
    host.addEventListener('click', async event => {
      const target = event.target.closest('button'); if (!target) return;
      if (target.dataset.researchSelect) nodeDetail(target.dataset.researchSelect);
      if (target.hasAttribute('data-build-create')) await chooseBuild();
      const buildId = target.dataset.buildReady || target.dataset.buildSeal;
      if (buildId) {
        const build = data.builds.find(item => item.build_id === buildId);
        actionDialog({ operation: target.dataset.buildSeal ? 'SEAL_SNAPSHOT' : 'READY_BUILD', field_id: data.field.field_id, build_id: buildId, expected_context_sha256: build.context_sha256 }, target.dataset.buildSeal ? '确认密封 Snapshot' : '确认进入审阅', `${buildId} · revision ${build.revision}；${build.evidence_candidates.length} 个证据候选、${build.candidate_gaps.length} 个候选 Gap。`);
      }
      if (target.dataset.reviewKey) {
        const node = model.nodes.find(item => item.key === target.dataset.reviewKey), context = node.record;
        actionDialog({ operation: node.kind === 'candidate' ? 'REVIEW_CANDIDATE' : 'REVIEW_GAP', field_id: data.field.field_id, object_id: context.record.candidate_id || context.record.candidate_gap_id, expected_context_sha256: context.context_sha256, decision: target.dataset.reviewDecision }, `${target.dataset.reviewDecision === 'ACCEPTED' ? '接受' : '拒绝'}候选`, `${node.label} · revision ${context.record.revision}`, true);
      }
      if (target.dataset.adoptSnapshot) {
        const snapshot = data.available_snapshots.find(item => item.snapshot_id === target.dataset.adoptSnapshot);
        actionDialog({ operation: 'ADOPT_SNAPSHOT', field_id: data.track.field_id, track_id: data.track.track_id, snapshot_id: snapshot.snapshot_id, expected_context_sha256: data.context_sha256, expected_snapshot_digest: snapshot.content_digest }, '确认 Track 采用 Snapshot', `${data.track.title} 明确采用 Snapshot v${snapshot.version}。保留此前已采用的版本；不批准科研节点。`);
      }
    });
    form.addEventListener('input', () => { if (pending && !pending.submitted) { pending.draftReason = new FormData(form).get('rationale') || ''; status.textContent = writePending() ? '审阅草稿已保存在本机。' : '无法保存本机草稿，请保留此窗口。'; } });
    form.addEventListener('submit', async event => {
      event.preventDefault(); if (!pending || sending || needsComparison) return;
      if (!pending.submitted) {
        if (pending.reasonRequired) pending.payload.rationale = new FormData(form).get('rationale');
        pending.submitted = true;
        if (!writePending()) { pending.submitted = false; status.textContent = '无法保存提交凭据，请恢复本机存储后重试。'; return; }
      }
      sending = true; submit.disabled = true;
      for (const input of body.querySelectorAll('textarea')) input.disabled = true;
      status.textContent = '正在核对保存结果…';
      try {
        await request('/api/catalog/fieldkg-actions', pending.payload);
        try { storage.removeItem(pendingKey); } catch { /* server receipt persists */ }
        pending = null; dialog.close(); await show(new URL(location.href).searchParams.get('view'));
      } catch (error) {
        if (error.status >= 400 && error.status < 500 && ![408, 429].includes(error.status)) {
          pending.submitted = false; writePending();
          for (const input of body.querySelectorAll('textarea')) input.disabled = false;
          status.textContent = `${error.message}。草稿仍在，请关闭窗口后更新、比较最新记录。`;
        } else status.textContent = `${error.message}。结果尚未确认，再次核对将使用原请求。`;
        submit.textContent = pending.submitted ? '核对原提交' : '确认此操作';
      } finally { sending = false; submit.disabled = false; }
    });
    dialog.querySelector('[data-fieldkg-action-close]').addEventListener('click', () => { if (!sending) dialog.close(); });
    dialog.addEventListener('cancel', event => { if (sending) event.preventDefault(); });
    function locateTarget(target) {
      if(!data)return false;
      if(target.module==='TRACK'&&data.track?.track_id!==target.track_id||target.module==='FIELDKG'&&data.field?.field_id!==target.field_id)return false;
      if(target.module==='FIELDKG'&&(target.snapshot_id||null)!==(data.selected_snapshot?.snapshot_id||null))return false;
      if(['field','track','snapshot'].includes(target.object_kind)){
        const heading=host.querySelector('.research-head');if(!heading)return false;heading.classList.add('discussion-selected');heading.setAttribute('tabindex','-1');heading.focus();return true;
      }
      const kind=target.object_kind==='concept'?'term':target.object_kind;
      const key=kind==='relationship'?target.object_id:id(kind,target.object_id);
      if(![...model.nodes,...model.edges].some(item=>item.key===key))return false;
      nodeDetail(key);
      const button=[...host.querySelectorAll('[data-research-select]')].find(item=>item.dataset.researchSelect===key);
      if(button){button.scrollIntoView({block:'center',behavior:'instant'});button.focus();}
      return true;
    }
    return { show, nodeDetail, locateTarget, researchUrl, cancelLoad: () => { serial++; trackDecisions?.leave(); }, capture: overviewCapture,
      back: returnOverview, openPaper };
  }
  root.RSTV4ResearchWorkspaces = { graphModel, snapshotGraph, buildStages, createWorkspace };
})(typeof window === 'undefined' ? globalThis : window);
