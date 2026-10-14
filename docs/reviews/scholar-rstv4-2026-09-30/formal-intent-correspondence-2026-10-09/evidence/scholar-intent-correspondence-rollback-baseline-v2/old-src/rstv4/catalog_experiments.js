/* Plans retain reviewed files; an uncertain start reconciles the original receipt. */
(function (root) {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const empty = () => ({ project_id: '', method_node_id: '', working_directory: '.', script_path: '', executable: '', input_files: [], artifact_paths: '', metrics_json_path: 'metrics.json', arguments: '[]', environment: '{}', timeout_seconds: 600,
    project: { slug: '', title: '', scope: '', goals: '', location: '', data: '', time: '', research_type: '', type_payload: '{}' }, results: {}, bound: null });
  function createController({ api, storage, namespace, makeKey, onState = () => {} }) {
    let trackId = '', context = null, files = null, draft = empty(), manifest = null, request = null, pending = false, epoch = 0, error = '', storageError = false;
    const key = id => `${namespace}:${id}`;
    const state = () => ({ trackId, context, files, draft: clone(draft), manifest, request: clone(request), pending, error, storageError,
      comparisonRequired: !!(context && draft.bound && draft.bound !== context.context_sha256) });
    const publish = () => onState(state());
    function persist(id, value) {
      try { const raw = JSON.stringify(value); storage.setItem(key(id), raw); if (storage.getItem(key(id)) !== raw) throw Error('Not retained'); return true; } catch { return false; }
    }
    function save() { storageError = !persist(trackId, { draft, manifest, request }); if (storageError) error = '原请求无法保存，请恢复本机存储后继续。'; }
    async function load(id) {
      const token = ++epoch;
      if (id !== trackId) {
        if (trackId) save(); trackId = id; context = files = manifest = null; draft = empty(); request = null; error = '';
        try { const saved = JSON.parse(storage.getItem(key(id)) || 'null'); if (saved) { draft = saved.draft; manifest = saved.manifest; request = saved.request; } } catch { error = '原实验草稿无法读取。'; }
      }
      publish();
      try {
        const loaded = await api(`/api/catalog/tracks/${encodeURIComponent(id)}/experiments`);
        if (token !== epoch || id !== trackId) return null;
        context = loaded; if (!draft.bound) draft.bound = context.context_sha256; save(); publish(); return loaded;
      } catch (failure) { if (token === epoch) { error = `实验状态读取失败：${failure.message}`; publish(); } throw failure; }
    }
    function edit(values) { if (pending || request) return false; const next = { ...draft, ...clone(values) }; if (JSON.stringify(next) !== JSON.stringify(draft)) { if (next.project_id !== draft.project_id || next.working_directory !== draft.working_directory) files = null; draft = next; manifest = null; } save(); return true; }
    function compare() { if (pending || request || !context) return; draft.bound = context.context_sha256; manifest = null; error = ''; save(); publish(); }
    function fresh() { if (pending || request) return; draft = empty(); draft.bound = context?.context_sha256; manifest = files = null; error = ''; save(); publish(); }
    function removeInput(path) { if (pending || request) return false; edit({ input_files: draft.input_files.filter(value => value !== path) }); publish(); return true; }
    async function readFiles() {
      const token = epoch, owner = trackId, project = draft.project_id, cwd = draft.working_directory;
      const query = new URLSearchParams({ working_directory: cwd }); if (project) query.set('project_id', project);
      try {
        const result = await api(`/api/catalog/tracks/${encodeURIComponent(owner)}/experiment-files?${query}`);
        if (token === epoch && owner === trackId && project === draft.project_id && cwd === draft.working_directory) { files = result; manifest = null; publish(); }
        return result;
      } catch (failure) { if (token === epoch) { error = failure.message; publish(); } throw failure; }
    }
    function selection() {
      const script = files?.files.find(file => file.path === draft.script_path);
      if (!script) throw Error('请读取工作目录并选择实际脚本。');
      const args = JSON.parse(draft.arguments), environment = JSON.parse(draft.environment);
      if (!Array.isArray(args) || args.some(v => typeof v !== 'string')) throw Error('额外参数应为字符串数组。');
      if (!environment || Array.isArray(environment) || typeof environment !== 'object' || Object.values(environment).some(v => typeof v !== 'string')) throw Error('环境变量应为字符串值的对象。');
      return { project_id: draft.project_id || null,
        plan: { method_node_id: draft.method_node_id, argv: [draft.executable || context.python_executable, draft.script_path, ...args], working_directory: draft.working_directory, script_path: draft.script_path, script_sha256: script.sha256, timeout_seconds: Number(draft.timeout_seconds), metrics_json_path: draft.metrics_json_path || null },
        input_files: draft.input_files, artifact_paths: draft.artifact_paths.split('\n').map(v => v.trim()).filter(Boolean), environment };
    }
    async function preview() {
      if (!context || state().comparisonRequired || pending || request) throw Error('请先核对当前实验依据。');
      const chosen = selection(), token = epoch;
      const loaded = await api(`/api/catalog/tracks/${encodeURIComponent(trackId)}/experiment-manifest`, chosen);
      if (token === epoch && JSON.stringify(chosen) === JSON.stringify(selection())) { manifest = loaded; error = ''; save(); publish(); }
      return loaded;
    }
    function base(operation) {
      if (!context || pending || request || state().comparisonRequired) throw Error('请先核对原请求与当前实验依据。');
      return { operation, request_id: makeKey(), track_id: trackId, expected_context_sha256: context.context_sha256, confirmed: true };
    }
    async function submit(body) {
      if (pending) return null;
      if (!request) request = { trackId, body };
      save(); if (storageError) { publish(); throw Error(error); }
      const original = clone(request), originalDraft = clone(draft), originalManifest = clone(manifest), token = epoch;
      pending = true; error = ''; publish();
      try {
        const result = await api('/api/catalog/experiment-actions', original.body);
        const nextDraft = original.body.operation === 'PROPOSE_PLAN' ? { ...empty(), project: originalDraft.project, results: originalDraft.results || {} } : original.body.operation === 'CREATE_PROJECT' ? { ...originalDraft, project: empty().project } : originalDraft;
        nextDraft.bound = null;
        const retained = persist(original.trackId, { draft: nextDraft, manifest: null, request: null });
        if (token === epoch) {
          if (retained) { request = null; draft = nextDraft; manifest = files = null; } else { storageError = true; error = '服务返回回执，但本机未保存；请核对原请求。'; }
          await load(trackId);
        }
        return result;
      } catch (failure) {
        const terminal = [403, 404, 409, 422].includes(failure.status);
        persist(original.trackId, { draft: originalDraft, manifest: originalManifest, request: terminal ? null : original });
        if (token === epoch) { error = failure.message; if (terminal) request = null; save(); publish(); }
        throw failure;
      } finally { pending = false; publish(); }
    }
    function propose() { if (!manifest) throw Error('请先核对完整文件与环境清单。'); return submit({ ...base('PROPOSE_PLAN'), ...selection(), expected_manifest_sha256: manifest.manifest_sha256 }); }
    function createProject() {
      const p = draft.project, payload = JSON.parse(p.type_payload);
      return submit({ ...base('CREATE_PROJECT'), project: { track_id: trackId, slug: p.slug, title: p.title, scope: p.scope || null, research_type: p.research_type || null,
        type_payload: { ...payload, goals: p.goals, location: p.location, data_description: p.data, time: p.time } } });
    }
    function planAction(operation, planId) {
      const plan = context.plans.find(p => p.plan_id === planId);
      if (!plan?.reviewed_manifest) throw Error('此旧计划没有完整审阅清单，请提出新计划。');
      if (operation === 'APPLY_PLAN' && !plan.grant_available) throw Error('尚无真实用户批准记录。');
      if (operation === 'START_PLAN' && (plan.status !== 'APPROVED' || plan.run_id)) throw Error('请先批准该计划或核对原执行回执。');
      return submit({ ...base(operation), plan_id: planId, expected_revision: plan.revision });
    }
    function recordResult(runId, statement, metricKey) {
      if (!statement.trim()) throw Error('请填写结果证据陈述。');
      return submit({ ...base('RECORD_RESULT'), run_id: runId, statement: statement.trim(), metric_key: metricKey || null });
    }
    return { load, edit, readFiles, preview, propose, createProject, planAction, recordResult, compare, fresh, removeInput, state,
      leave: () => { epoch++; if (trackId) save(); context = null; },
      retry: () => { if (!request) throw Error('没有待核对的原请求。'); return submit(request.body); } };
  }
  function render(s) {
    if (!s.context) return `<p role="status">${esc(s.error || '正在读取实验状态…')}</p><button type="button" data-exp-refresh>更新实验状态</button>`;
    const c = s.context, d = s.draft, locked = s.pending || !!s.request, dis = locked ? ' disabled' : '';
    const choice = (value, current, label) => `<option value="${esc(value)}"${value === current ? ' selected' : ''}>${esc(label)}</option>`;
    const methods = c.science.nodes.filter(n => n.node_type === 'method');
    const plans = c.plans.map(p => `<article class="item"><h3>实验计划 · ${esc(p.status)}</h3><p>${esc(p.plan_id)} · Method ${esc(p.method_node_id)} · ${esc(p.project_id || 'Track 直属')}</p><p>命令：${esc(p.argv.join(' '))}</p>${p.reviewed_manifest ? `<details><summary>已固定的脚本、输入与环境清单</summary><pre>${esc(JSON.stringify(p.reviewed_manifest, null, 2))}</pre></details>` : '<p>旧计划未保留完整审阅清单，请提出新计划。</p>'}${p.status === 'PROPOSED' ? `<p>在 Scholar／Orchestrator 真实用户消息中审阅并发送：<code>${esc(p.approval_phrase)}</code></p><p>${p.grant_available ? '已读回用户批准记录。' : '尚无真实用户批准记录。'}</p><button type="button" data-exp-apply="${esc(p.plan_id)}"${locked || !p.grant_available || !p.reviewed_manifest ? ' disabled' : ''}>应用已批准计划</button>` : `<button type="button" data-exp-start="${esc(p.plan_id)}"${locked || p.status !== 'APPROVED' || p.run_id || !p.reviewed_manifest ? ' disabled' : ''}>执行此计划一次</button>`}${p.run_id ? `<p>已有执行回执 ${esc(p.run_id)}，请更新状态核对。</p>` : ''}</article>`).join('');
    const results = c.runs.filter(r => r.detail.plan_id).map(r => `<article class="item"><h3>执行 ${esc(r.run_id)} · ${esc(r.status)}</h3><p>计划 ${esc(r.detail.plan_id)} · ${esc(r.detail.cwd)}</p>${r.status === 'RUNNING' ? '<p>这是保存的回执状态；尚未确认进程仍在运行。更新后核对原请求，不重新执行。</p>' : ''}${r.detail.validation_error ? `<p role="alert">${esc(r.detail.validation_error)}</p>` : ''}<details><summary>本次原输出与结果</summary><pre>${esc(r.detail.stdout || '')}</pre><pre>${esc(r.detail.stderr || '')}</pre><pre>${esc(JSON.stringify(r.detail.metrics || {}, null, 2))}</pre></details>${r.status === 'COMPLETED' ? `<form data-exp-result="${esc(r.run_id)}"><label>结果证据陈述<textarea name="statement" required${dis}>${esc(d.results?.[r.run_id]?.statement || "")}</textarea></label><label>指标<select name="metric_key"${dis}>${choice('', '', '全部结果')}${Object.keys(r.detail.metrics || {}).map(k => choice(k, d.results?.[r.run_id]?.metric_key || '', k)).join('')}</select></label><button type="submit"${dis}>保存结果证据，供 Claim 提案选择</button></form>` : '<p>当前状态不能保存有效结果证据。</p>'}</article>`).join('');
    const files = s.files?.files || [];
    const missingInputs = d.input_files.filter(path => !files.some(file => file.path === path)).map(path => `<p>原输入选择${s.files ? '在当前目录不可用' : '尚未核实'}：${esc(path)} <button type="button" data-exp-remove-input="${esc(path)}"${dis}>明确移除此输入选择</button></p>`).join('');
    const unverifiedScript = d.script_path && !files.some(file => file.path === d.script_path) ? choice(d.script_path, d.script_path, `${d.script_path} · 原选择尚未核实`) : '';
    return `<p role="status" aria-live="polite">${esc(s.error || (s.pending ? '正在核对原请求结果…' : '实验状态已读取。'))}</p><button type="button" data-exp-refresh${s.pending ? ' disabled' : ''}>更新实验状态</button>${s.request ? `<details open><summary>结果尚未确认，原请求保留</summary><pre>${esc(JSON.stringify(s.request, null, 2))}</pre></details><button type="button" data-exp-retry${s.pending ? ' disabled' : ''}>核对原请求</button>` : ''}${s.comparisonRequired ? `<p>原草稿依据 ${esc(d.bound)} 与当前依据 ${esc(c.context_sha256)} 不同。计划和执行状态见下方。</p><button type="button" data-exp-compare${dis}>已比较，使用当前依据</button>` : ''}
      <details><summary>新建实施 Project</summary><form data-exp-project><label>名称<input name="title" required value="${esc(d.project.title)}"${dis}></label><label>目录名<input name="slug" required pattern="[a-z0-9][a-z0-9_-]{0,63}" value="${esc(d.project.slug)}"${dis}></label>${[['scope', '实施范围'], ['goals', '目标'], ['location', '地点'], ['data', '数据'], ['time', '时间安排']].map(([key, label]) => `<label>${label}<textarea name="${key}"${dis}>${esc(d.project[key])}</textarea></label>`).join('')}<label>研究类型<select name="research_type"${dis}>${choice('', d.project.research_type, '沿用 Track 类型')}${Object.keys(c.project_types).map(k => choice(k, d.project.research_type, k)).join('')}</select></label><p>本类型需要：${esc((c.project_types[d.project.research_type || c.science.track.research_type] || []).join('、'))}</p><label>类型内容（JSON 对象）<textarea name="type_payload" required${dis}>${esc(d.project.type_payload)}</textarea></label><button type="submit"${dis}>保存 Project</button></form></details>
      <form data-exp-plan><h3>新建待审阅实验计划</h3><label>实施归属<select name="project_id"${dis}>${choice('', d.project_id, 'Track 直属')}${c.projects.map(p => choice(p.project_id, d.project_id, p.title)).join('')}</select></label><label>Method<select name="method_node_id" required${dis}>${choice('', d.method_node_id, '选择已批准 Method')}${methods.map(n => `<option value="${esc(n.node_id)}"${n.node_id === d.method_node_id ? ' selected' : ''}${n.status !== 'APPROVED' ? ' disabled' : ''}>${esc(n.statement)} · ${esc(n.status)}</option>`).join('')}</select></label><label>工作目录<input name="working_directory" value="${esc(d.working_directory)}" required${dis}></label><button type="button" data-exp-files${dis}>读取实际文件</button><p>${esc(s.files ? s.files.cwd : '尚未读取目录。')}${s.files && !s.files.exists ? ' · 目录尚未创建' : ''}</p><label>脚本<select name="script_path" required${dis}>${choice('', d.script_path, '选择实际脚本')}${unverifiedScript}${files.map(f => choice(f.path, d.script_path, `${f.path} · ${f.size} bytes`)).join('')}</select></label><fieldset><legend>输入文件</legend>${files.map(f => `<label><input type="checkbox" name="input_files" value="${esc(f.path)}"${d.input_files.includes(f.path) ? ' checked' : ''}${dis}>${esc(f.path)} · ${esc(f.sha256)}</label>`).join('') || '<p>先读取实际文件。</p>'}</fieldset>${missingInputs}<label>Python 执行环境<input name="executable" value="${esc(d.executable || c.python_executable)}" required${dis}></label><label>额外参数（JSON 字符串数组）<textarea name="arguments"${dis}>${esc(d.arguments)}</textarea></label><label>环境变量覆盖（JSON 字符串对象）<textarea name="environment"${dis}>${esc(d.environment)}</textarea></label><label>超时秒数<input name="timeout_seconds" type="number" min="1" max="86400" value="${esc(d.timeout_seconds)}" required${dis}></label><label>指标文件<input name="metrics_json_path" value="${esc(d.metrics_json_path)}"${dis}></label><label>产物路径（每行一个）<textarea name="artifact_paths"${dis}>${esc(d.artifact_paths)}</textarea></label><button type="button" data-exp-preview${locked || s.comparisonRequired ? ' disabled' : ''}>核对完整文件与环境清单</button>${s.manifest ? `<details open><summary>本次将提交审阅的完整清单</summary><pre>${esc(JSON.stringify(s.manifest, null, 2))}</pre></details>` : ''}<button type="submit"${locked || !s.manifest || s.comparisonRequired ? ' disabled' : ''}>保存待审阅计划</button><button type="button" data-exp-fresh${dis}>开始新计划草稿</button></form><h3>计划与批准</h3>${plans || '<p>尚无实验计划。</p>'}<h3>本次执行与结果证据</h3>${results || '<p>尚无此工作台的执行回执。</p>'}`;
  }
  function mount({ host, api, storage, namespace, onChanged }) {
    let visible = false;
    const panel = () => host.querySelector('[data-track-experiments]');
    const controller = createController({ api, storage, namespace, makeKey: () => root.crypto.randomUUID(), onState: s => { if (visible && panel()) panel().innerHTML = render(s); } });
    function read(form) {
      const values = new FormData(form), s = controller.state();
      if (form.hasAttribute('data-exp-plan')) controller.edit({ ...Object.fromEntries(values), input_files: [...values.getAll('input_files'), ...s.draft.input_files.filter(p => !(s.files?.files || []).some(f => f.path === p))] });
      if (form.hasAttribute('data-exp-plan') && !controller.state().manifest) {
        const submit = form.querySelector('[type="submit"]'); if (submit) submit.disabled = true;
        const preview = form.querySelector('details'); if (preview) preview.hidden = true;
      }
      if (form.hasAttribute('data-exp-project')) controller.edit({ project: Object.fromEntries(values) });
      if (form.hasAttribute('data-exp-result')) controller.edit({ results: { ...(s.draft.results || {}), [form.dataset.expResult]: Object.fromEntries(values) } });
    }
    async function run(action, refresh = false) {
      try { await action(); if (visible && refresh) await onChanged(); }
      catch (error) { if (visible && panel()) { const status = panel().querySelector('[role="status"]'); if (status) status.textContent = `${error.message}。原草稿和回执保留。`; } }
    }
    host.addEventListener('input', event => { const form = event.target.closest('[data-exp-plan], [data-exp-project], [data-exp-result]'); if (form) read(form); });
    host.addEventListener('change', event => { const form = event.target.closest('[data-exp-plan], [data-exp-project], [data-exp-result]'); if (form) read(form); });
    host.addEventListener('submit', event => {
      const form = event.target.closest('[data-exp-plan], [data-exp-project], [data-exp-result]'); if (!form) return; event.preventDefault();
      if (form.hasAttribute('data-exp-result')) { const values = new FormData(form); void run(() => controller.recordResult(form.dataset.expResult, values.get('statement'), values.get('metric_key')), true); }
      else { read(form); void run(() => form.hasAttribute('data-exp-plan') ? controller.propose() : controller.createProject(), true); }
    });
    host.addEventListener('click', event => {
      const button = event.target.closest('button'); if (!button || button.disabled) return; const d = button.dataset;
      if ('expRefresh' in d) void run(() => controller.load(controller.state().trackId));
      if ('expFiles' in d) void run(() => controller.readFiles());
      if ('expPreview' in d) void run(() => controller.preview());
      if ('expCompare' in d) controller.compare();
      if ('expFresh' in d) controller.fresh();
      if (d.expRemoveInput) controller.removeInput(d.expRemoveInput);
      if ('expRetry' in d) void run(() => controller.retry(), true);
      if (d.expApply) void run(() => controller.planAction('APPLY_PLAN', d.expApply), true);
      if (d.expStart) void run(() => controller.planAction('START_PLAN', d.expStart), true);
    });
    return { controller, load: id => { visible = true; return controller.load(id); }, leave: () => { visible = false; controller.leave(); } };
  }
  root.CatalogExperiments = { createController, render, mount };
})(typeof window === 'undefined' ? globalThis : window);
