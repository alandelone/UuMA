/* Scientific proposals keep their original basis and never mint approval grants. */
(function (root) {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const kinds = { gap: 'Gap', idea: 'Idea', research_question: 'Research Question', hypothesis: 'Hypothesis', method: 'Method', claim: 'Claim' };
  const emptyDraft = () => ({ kind: 'gap', statement: '', rationale: '', evidence_ids: [], upstream_node_ids: [], supersedes_node_id: null, bound: null });
  function createController({ api, storage, makeKey, namespace, onState = () => {} }) {
    let trackId = '', context = null, draft = emptyDraft(), request = null, pending = false, epoch = 0, error = '', storageError = false;
    const key = id => `${namespace}:${id}`;
    const state = () => ({ trackId, context, draft: clone(draft), request: clone(request), pending, error, storageError,
      comparisonRequired: Boolean(context && draft.bound && context.context_sha256 !== draft.bound.context_sha256) });
    const publish = () => onState(state());
    function persist(id, value) {
      try { const raw = JSON.stringify(value); storage.setItem(key(id), raw); if (storage.getItem(key(id)) !== raw) throw Error('Not retained'); return true; }
      catch { return false; }
    }
    function save() { storageError = !persist(trackId, { draft, request }); if (storageError) error = '无法保存原请求，请恢复本机存储后重试。'; }
    async function load(id) {
      const token = ++epoch;
      if (id !== trackId) {
        if (trackId) save(); trackId = id; draft = emptyDraft(); request = null; error = ''; context = null;
        try { const saved = JSON.parse(storage.getItem(key(id)) || 'null'); if (saved) { draft = saved.draft; request = saved.request; } } catch { error = '原草稿无法读取，请先恢复本机存储。'; }
      }
      publish();
      try {
        const loaded = await api(`/api/catalog/tracks/${encodeURIComponent(id)}/scientific-context`);
        if (token !== epoch || trackId !== id) return null;
        context = loaded; if (!draft.bound) draft.bound = clone(context); save(); publish(); return loaded;
      } catch (failure) { if (token === epoch) { context = null; error = `科研依据读取失败：${failure.message}。请更新后重试。`; publish(); } throw failure; }
    }
    function edit(values) { if (pending || request) return false; draft = { ...draft, ...clone(values) }; save(); return true; }
    function compare() { if (!context || pending || request) return; draft.bound = clone(context); error = ''; save(); publish(); }
    async function submit(body) {
      if (pending) return null;
      if (!request) request = { trackId, body };
      save(); if (storageError) { publish(); throw Error(error); }
      const original = clone(request), originalDraft = clone(draft), token = epoch;
      pending = true; error = ''; publish();
      try {
        const result = await api('/api/catalog/track-scientific-actions', original.body);
        const retained = persist(original.trackId, { draft: originalDraft, request: null });
        if (token === epoch) { if (retained) request = null; else { storageError = true; error = '服务已返回结果，但本机回执未更新；请核对原请求。'; } await load(trackId); }
        return result;
      } catch (failure) {
        if (token === epoch) {
          error = failure.message;
          if ([403, 404, 409, 422].includes(failure.status)) request = null;
          save(); publish();
          if (failure.status === 409) { try { await load(trackId); } catch { /* preserve read error */ } }
        }
        throw failure;
      } finally { pending = false; if (token === epoch || trackId) publish(); }
    }
    function base(operation) {
      if (!context) throw Error('请先读取当前科研依据。');
      if (request) throw Error('上次结果尚未确认，请先核对原请求。');
      return { operation, request_id: makeKey(), confirmed: true, field_id: context.track.field_id,
        track_id: trackId, expected_context_sha256: context.context_sha256 };
    }
    async function propose() {
      if (state().comparisonRequired) throw Error('科研依据已变化，请先比较原草稿与当前版本。');
      if (!draft.statement.trim() || !draft.rationale.trim()) throw Error('请填写科学陈述和提出理由。');
      return submit({ ...base('PROPOSE_DECISION'), proposal: { kind: draft.kind, statement: draft.statement.trim(),
        rationale: draft.rationale.trim(), evidence_ids: draft.evidence_ids, upstream_node_ids: draft.upstream_node_ids,
        supersedes_node_id: draft.supersedes_node_id, track_id: trackId } });
    }
    async function apply(proposalId) {
      const proposal = context?.proposals.find(p => p.proposal_id === proposalId);
      if (!proposal || proposal.status !== 'PROPOSED' || !proposal.grant_available || !proposal.basis_captured) throw Error('请先通过 Scholar／Orchestrator 的真实用户消息审阅此提案。');
      return submit({ ...base('APPLY_DECISION'), proposal_id: proposalId, expected_revision: proposal.revision });
    }
    function replace(nodeId) {
      if (pending || request || !context) return false;
      const node = context.nodes.find(n => n.node_id === nodeId);
      if (!node || !['APPROVED', 'STALE'].includes(node.status)) return false;
      draft = { kind: node.node_type, statement: node.statement, rationale: '', evidence_ids: node.payload.evidence_ids || [],
        upstream_node_ids: node.payload.upstream_node_ids || [], supersedes_node_id: node.node_id, bound: clone(context) };
      save(); publish(); return true;
    }
    function fresh() { if (pending || request) return; draft = emptyDraft(); draft.bound = context && clone(context); error = ''; save(); publish(); }
    function leave() { epoch++; if (trackId) save(); context = null; }
    return { load, edit, compare, propose, apply, replace, fresh, leave, state,
      retry: () => { if (!request) throw Error('没有待核对的原请求。'); return submit(request.body); } };
  }

  function render(state) {
    if (!state.context) return `<p role="${state.error ? 'alert' : 'status'}">${esc(state.error || '正在读取科研提案依据…')}</p><button type="button" data-science-refresh>更新科研依据</button>`;
    const { context: c, draft: d } = state, locked = state.pending || !!state.request, disabled = locked ? ' disabled' : '';
    const evidence = c.evidence.map(e => `<label class="research-source-choice"><input type="checkbox" name="evidence" value="${esc(e.evidence_id)}"${d.evidence_ids.includes(e.evidence_id) ? ' checked' : ''}${locked || !e.selectable && !d.evidence_ids.includes(e.evidence_id) ? ' disabled' : ''}>${esc(e.statement)} · ${esc(e.relation)} · ${e.selectable ? '可选依据' : '需审阅或尚未采用'}<span>${esc(e.evidence_id)}</span></label><details><summary>原文、条件与来源版本</summary><blockquote>${esc(e.excerpt)}</blockquote><p>PaperVersion ${esc(e.paper_version_id || '未知')} · Run ${esc(e.experiment_run_id || '未知')}</p><pre>${esc(JSON.stringify(e.location, null, 2))}</pre>${e.adopted_in.map(a => `<a href="/?view=fieldkg&field=${encodeURIComponent(c.track.field_id)}&snapshot=${encodeURIComponent(a.snapshot_id)}">已采用 Snapshot v${a.version}</a>`).join('')}</details>`).join('');
    const upstream = c.nodes.map(n => `<label class="research-source-choice"><input type="checkbox" name="upstream" value="${esc(n.node_id)}"${d.upstream_node_ids.includes(n.node_id) ? ' checked' : ''}${locked || n.status !== 'APPROVED' && !d.upstream_node_ids.includes(n.node_id) ? ' disabled' : ''}>${esc(kinds[n.node_type] || n.node_type)} · ${esc(n.status)} · ${esc(n.statement)}</label><button type="button" data-science-node="${esc(n.node_id)}">查看该节点并带入 Chat</button>${['APPROVED', 'STALE'].includes(n.status) ? `<button type="button" data-science-replace="${esc(n.node_id)}"${disabled}>提出替代决定</button>` : ''}`).join('');
    const missing = [['evidence_ids', c.evidence.map(e => e.evidence_id)], ['upstream_node_ids', c.nodes.map(n => n.node_id)]].flatMap(([name, available]) => d[name].filter(id => !available.includes(id)).map(id => `<p>原依据已不可用：${esc(id)} <button type="button" data-science-remove-kind="${name}" data-science-remove-id="${esc(id)}"${disabled}>明确移除此项依据</button></p>`)).join('');
    const proposals = c.proposals.map(p => `<article class="item"><h3>${esc(kinds[p.kind])} · ${esc(p.status)}</h3><p>${esc(p.statement)}</p><p>${esc(p.rationale)}</p><p>提案 ${esc(p.proposal_id)} · revision ${p.revision}${p.supersedes_node_id ? ` · 替代 ${esc(p.supersedes_node_id)}` : ''}</p><button type="button" data-science-node="${esc(p.node_id)}">查看节点与来源</button><details><summary>固定依赖与原提案依据</summary><pre>${esc(JSON.stringify(p.payload, null, 2))}</pre>${c.receipts.filter(r => r.object_id === p.proposal_id).map(r => `<p>${esc(r.operation)} · 原请求 ${esc(r.request_id)}</p><pre>${esc(JSON.stringify(r.dependency_basis, null, 2))}</pre>`).join('') || '<p>旧提案未保留此工作台的固定依据，需重新提出。</p>'}</details>${p.status === 'PROPOSED' ? `<p>请在 Scholar／Orchestrator 的真实用户消息中审阅并发送：<code>${esc(p.approval_phrase)}</code></p><p>${p.grant_available ? '已读回用户批准记录。' : '尚无真实用户批准记录。'}</p><button type="button" data-science-apply="${esc(p.proposal_id)}"${locked || !p.grant_available || !p.basis_captured ? ' disabled' : ''}>应用已批准提案</button>` : `<p>${esc(p.confirmation_text || p.rejection_reason || '')}</p>`}</article>`).join('');
    return `<p>每个科研对象独立提出与审阅。替代上游决定后，依赖节点与稿件将要求复核。</p><p role="status" aria-live="polite">${esc(state.error || (state.pending ? '正在核对保存结果…' : '已读取当前科学依据。'))}</p><button type="button" data-science-refresh${state.pending ? ' disabled' : ''}>更新科研依据</button>${state.request ? `<details open><summary>结果尚未确认：原请求与固定目标</summary><pre>${esc(JSON.stringify(state.request, null, 2))}</pre></details><button type="button" data-science-retry${state.pending ? ' disabled' : ''}>核对原请求</button>` : ''}${state.comparisonRequired ? `<details open><summary>原草稿依据与当前依据已有变化</summary><h3>原依据</h3><pre>${esc(JSON.stringify(d.bound, null, 2))}</pre><h3>当前依据</h3><pre>${esc(JSON.stringify(c, null, 2))}</pre></details><button type="button" data-science-compare${disabled}>已比较，使用当前依据继续</button>` : ''}${missing}<form data-science-proposal><h3>${d.supersedes_node_id ? '提出替代决定' : '新建科研提案'}</h3>${d.supersedes_node_id ? `<p>原节点：${esc(d.supersedes_node_id)}。原批准与成文版本保留。</p>` : ''}<label>科研对象类型<select name="kind"${disabled}>${Object.entries(kinds).map(([value, label]) => `<option value="${value}"${d.kind === value ? ' selected' : ''}>${label}</option>`).join('')}</select></label><label>科学陈述<textarea name="statement" required maxlength="16000" autocomplete="off"${disabled}>${esc(d.statement)}</textarea></label><label>提出／替代理由<textarea name="rationale" required maxlength="16000" autocomplete="off"${disabled}>${esc(d.rationale)}</textarea></label><fieldset><legend>选择依据：Track 证据或明确采用的 Snapshot</legend>${evidence || '<p>尚无证据，请先审阅来源并采用 Snapshot。</p>'}</fieldset><fieldset><legend>选择已批准的上游科学节点</legend>${upstream || '<p>尚无科研节点；Gap 需先选择证据。</p>'}</fieldset><button type="submit"${locked || state.comparisonRequired ? ' disabled' : ''}>保存待审阅提案</button><button type="button" data-science-fresh${disabled}>开始新的提案</button></form><h3>全部提案与独立状态</h3>${proposals || '<p>尚无提案。</p>'}`;
  }
  function mount({ host, api, storage, namespace, onChanged, onNode }) {
    let visible = false;
    const controller = createController({ api, storage, namespace, makeKey: () => root.crypto.randomUUID(),
      onState: state => { const panel = host.querySelector('[data-track-scientific]'); if (visible && panel) panel.innerHTML = render(state); } });
    const readForm = form => { const values = new FormData(form), state = controller.state(); controller.edit({ kind: values.get('kind'), statement: values.get('statement'), rationale: values.get('rationale'), evidence_ids: [...values.getAll('evidence'), ...state.draft.evidence_ids.filter(id => !state.context.evidence.some(e => e.evidence_id === id))], upstream_node_ids: [...values.getAll('upstream'), ...state.draft.upstream_node_ids.filter(id => !state.context.nodes.some(n => n.node_id === id))] }); };
    async function run(action, refresh = false) {
      try { await action(); if (visible && refresh) await onChanged(); }
      catch (error) { const panel = host.querySelector('[data-track-scientific]'); if (visible && panel) { const status = panel.querySelector('[role="status"]'); if (status) status.textContent = `${error.message}。原草稿与回执已保留。`; } }
    }
    host.addEventListener('input', event => { const form = event.target.closest('[data-science-proposal]'); if (form) readForm(form); });
    host.addEventListener('change', event => { const form = event.target.closest('[data-science-proposal]'); if (form) readForm(form); });
    host.addEventListener('submit', event => { const form = event.target.closest('[data-science-proposal]'); if (!form) return; event.preventDefault(); readForm(form); void run(() => controller.propose(), true); });
    host.addEventListener('click', event => {
      const button = event.target.closest('button'); if (!button || button.disabled) return;
      const d = button.dataset;
      if ('scienceRefresh' in d) void run(() => controller.load(controller.state().trackId));
      if ('scienceRetry' in d) void run(() => controller.retry(), true);
      if ('scienceCompare' in d) controller.compare();
      if ('scienceFresh' in d) controller.fresh();
      if (d.scienceReplace) controller.replace(d.scienceReplace);
      if (d.scienceApply) void run(() => controller.apply(d.scienceApply), true);
      if (d.scienceRemoveId && ['evidence_ids', 'upstream_node_ids'].includes(d.scienceRemoveKind)) { controller.edit({ [d.scienceRemoveKind]: controller.state().draft[d.scienceRemoveKind].filter(id => id !== d.scienceRemoveId) }); const panel = host.querySelector('[data-track-scientific]'); if (panel) panel.innerHTML = render(controller.state()); }
      if (d.scienceNode) onNode(d.scienceNode);
    });
    return { controller, load: id => { visible = true; return controller.load(id); }, leave: () => { visible = false; controller.leave(); } };
  }
  root.CatalogTrackDecisions = { createController, render, mount };
})(typeof window === 'undefined' ? globalThis : window);
