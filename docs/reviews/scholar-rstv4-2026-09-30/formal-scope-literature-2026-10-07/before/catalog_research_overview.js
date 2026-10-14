/* The existing blue research list: stable identity, navigation state and explicit metadata edits. */
(function (root) {
  'use strict';
  const key = (...parts) => JSON.stringify(parts);
  const storageRead = (storage, name) => {
    try { return JSON.parse(storage.getItem(name)); } catch { return null; }
  };
  const storageWrite = (storage, name, value) => {
    try { storage.setItem(name, JSON.stringify(value)); return true; } catch { return false; }
  };

  function buildRows(data) {
    const rows = [];
    const add = (level, id, parent, record, extra = {}) => {
      const row = { level, key: id, parent, record, title: record.name || record.title || record.statement,
        ...extra, depth: parent ? rows.find(r => r.key === parent).depth + 1 : 1 };
      rows.push(row);
      return row;
    };
    function trackRows(field, topic, track, parent) {
      const id = key('track', track.track_id);
      add('track', id, parent, track, { field, topic, track });
      const papers = data.manuscripts.filter(p => p.track_id === track.track_id);
      const placed = new Set();
      for (const question of data.questions.filter(q => q.track_id === track.track_id)) {
        const qkey = key('question', question.node_id);
        add('question', qkey, id, question, { field, topic, track });
        for (const paper of papers.filter(p => data.manuscript_questions.some(
          link => link.manuscript_id === p.manuscript_id && link.node_id === question.node_id))) {
          add('paper', key('paper', paper.manuscript_id, qkey), qkey, paper, { field, topic, track });
          placed.add(paper.manuscript_id);
        }
      }
      for (const paper of papers.filter(p => !placed.has(p.manuscript_id))) {
        add('paper', key('paper', paper.manuscript_id, id), id, paper, { field, topic, track });
      }
    }
    for (const field of data.fields) {
      const fkey = key('field', field.field_id);
      add('field', fkey, '', field, { field });
      const topics = data.topics.filter(t => data.field_topics.some(
        link => link.field_id === field.field_id && link.topic_id === t.topic_id));
      for (const topic of topics) {
        const tkey = key('topic', field.field_id, topic.topic_id);
        add('topic', tkey, fkey, topic, { field, topic });
        for (const track of data.tracks.filter(t => t.field_id === field.field_id &&
          t.primary_topic_id === topic.topic_id)) trackRows(field, topic, track, tkey);
      }
      for (const track of data.tracks.filter(t => t.field_id === field.field_id &&
        !topics.some(topic => topic.topic_id === t.primary_topic_id))) {
        trackRows(field, null, track, fkey);
      }
    }
    const parents = new Set(rows.map(r => r.parent));
    rows.forEach(row => { row.expandable = parents.has(row.key); });
    return rows;
  }

  function visibleRows(rows, collapsed) {
    const visible = new Map();
    return rows.filter(row => {
      const show = !row.parent || (visible.get(row.parent) && !collapsed.has(row.parent));
      visible.set(row.key, show);
      return show;
    });
  }

  function reconcileState(rows, state) {
    const known = new Set(rows.map(r => r.key));
    return { collapsed: (Array.isArray(state?.collapsed) ? state.collapsed : []).filter(id => known.has(id)),
      focus: known.has(state?.focus) ? state.focus : '',
      anchor: known.has(state?.anchor) ? state.anchor : '',
      offset: Number.isFinite(state?.offset) ? state.offset : 0,
      scroll: Number.isFinite(state?.scroll) ? Math.max(0, state.scroll) : 0 };
  }

  function keyboardTarget(rows, collapsed, currentKey, code) {
    const visible = visibleRows(rows, collapsed);
    const index = visible.findIndex(r => r.key === currentKey), row = visible[index];
    if (!row) return null;
    if (code === 'Home') return { focus: visible[0].key };
    if (code === 'End') return { focus: visible.at(-1).key };
    if (code === 'ArrowDown') return { focus: visible[Math.min(index + 1, visible.length - 1)].key };
    if (code === 'ArrowUp') return { focus: visible[Math.max(index - 1, 0)].key };
    if (code === 'ArrowRight') {
      if (row.expandable && collapsed.has(row.key)) return { toggle: row.key };
      const child = visible[index + 1];
      return child?.parent === row.key ? { focus: child.key } : null;
    }
    if (code === 'ArrowLeft') {
      if (row.expandable && !collapsed.has(row.key)) return { toggle: row.key };
      return row.parent ? { focus: row.parent } : null;
    }
    if (code === 'Enter' || code === ' ') return row.expandable ? { toggle: row.key } : { activate: row.key };
    return null;
  }

  function createList({ tree, renderRow, storage, location, history, viewport }) {
    let rows = [], elements = new Map(), state = reconcileState([], null), workspace = '';
    let storageKey = '', scheduled = false;
    const saved = () => ({ ...state, workspace });
    function persist() {
      if (!workspace) return;
      storageWrite(storage, storageKey, saved());
      const url = new URL(location.href);
      url.searchParams.set('overview_state', JSON.stringify(saved()));
      history.replaceState(history.state, '', url);
      refreshLinks();
    }
    function refreshLinks() {
      for (const link of tree.querySelectorAll('a[data-manuscript-id]')) {
        const url = new URL('http://127.0.0.1:3000/');
        url.searchParams.set('manuscript', link.dataset.manuscriptId);
        url.searchParams.set('track', link.dataset.trackId);
        url.searchParams.set('from', 'catalog');
        url.searchParams.set('return', location.href);
        link.href = url.href;
      }
    }
    function capture() {
      if (tree.closest('[hidden]')) return;
      state.scroll = viewport.scrollY;
      const active = tree.ownerDocument.activeElement?.closest('.overview-row');
      if (active) state.focus = active.dataset.node;
      const anchor = [...elements.values()].find(el => !el.hidden && el.getBoundingClientRect().bottom > 0);
      if (anchor) { state.anchor = anchor.dataset.node; state.offset = anchor.getBoundingClientRect().top; }
      persist();
    }
    function apply() {
      const collapsed = new Set(state.collapsed), visible = new Set(visibleRows(rows, collapsed).map(r => r.key));
      const focus = visible.has(state.focus) ? state.focus : visibleRows(rows, collapsed)[0]?.key;
      for (const row of rows) {
        const el = elements.get(row.key), open = !collapsed.has(row.key);
        el.hidden = !visible.has(row.key);
        el.tabIndex = row.key === focus ? 0 : -1;
        if (row.expandable) {
          el.setAttribute('aria-expanded', String(open));
          const button = el.querySelector('[data-toggle-node]');
          button.setAttribute('aria-expanded', String(open));
          button.setAttribute('aria-label', `${open ? '收起' : '展开'} ${row.title}`);
        }
      }
    }
    function toggle(id) {
      const row = rows.find(r => r.key === id);
      if (!row?.expandable) return;
      const collapsed = new Set(state.collapsed);
      if (collapsed.has(id)) collapsed.delete(id); else collapsed.add(id);
      state.collapsed = [...collapsed]; state.focus = id;
      apply(); capture();
    }
    function focus(id) {
      state.focus = id; apply(); elements.get(id)?.focus({ preventScroll: true });
    }
    function restore() {
      const anchor = elements.get(state.anchor);
      if (anchor && !anchor.hidden) viewport.scrollBy(0, anchor.getBoundingClientRect().top - state.offset);
      else viewport.scrollTo(0, state.scroll);
      if (state.focus && !elements.get(state.focus)?.hidden) focus(state.focus);
    }
    function load(data, captureCurrent = true) {
      const same = workspace === data.workspace_id;
      if (same && captureCurrent) capture();
      workspace = data.workspace_id; storageKey = `rstv4-overview-v1:${location.origin}:${workspace}`;
      let incoming;
      try { incoming = JSON.parse(new URL(location.href).searchParams.get('overview_state')); } catch { /* malformed URL */ }
      if (incoming?.workspace !== workspace) incoming = storageRead(storage, storageKey);
      if (incoming?.workspace !== workspace) incoming = null;
      rows = buildRows(data);
      state = reconcileState(rows, same ? state : incoming?.workspace === workspace ? incoming : null);
      const urlTrack = new URL(location.href).searchParams.get('track');
      if (!same && !incoming && urlTrack) {
        const row = rows.find(r => r.level === 'track' && r.record.track_id === urlTrack);
        if (row) { state.anchor = row.key; state.focus = row.key; state.offset = 100; }
      }
      tree.innerHTML = rows.map(renderRow).join('');
      elements = new Map([...tree.querySelectorAll('.overview-row')].map(el => [el.dataset.node, el]));
      apply(); restore(); persist();
    }
    tree.addEventListener('keydown', event => {
      if (event.target.getAttribute('role') !== 'treeitem') return;
      const action = keyboardTarget(rows, new Set(state.collapsed), event.target.dataset.node, event.key);
      if (!action) return;
      event.preventDefault();
      if (action.toggle) toggle(action.toggle);
      if (action.focus) { focus(action.focus); elements.get(action.focus)?.scrollIntoView({ block: 'nearest' }); capture(); }
      if (action.activate) elements.get(action.activate)?.querySelector('a,button')?.click();
    });
    tree.addEventListener('focusin', capture);
    tree.addEventListener('pointerdown', capture);
    viewport.addEventListener('scroll', () => {
      if (!scheduled) { scheduled = true; viewport.requestAnimationFrame(() => { scheduled = false; capture(); }); }
    }, { passive: true });
    viewport.addEventListener('pagehide', capture);
    return { load, toggle, capture, find: id => rows.find(row => row.key === id) };
  }

  const researchTypes = {
    experimental: '实验研究', engineering_system: '工程系统', method_algorithm: '方法／算法',
    systematic_review: '系统综述', sota_review: '领域进展综述', critical_review: '批判性综述',
    bibliometric_review: '文献计量综述', conceptual_framework: '概念框架', case_study: '案例研究',
  };

  function createEditor({ dialog, storage, getData, onSaved, fetchAction, escapeHtml, draftNamespace }) {
    const form = dialog.querySelector('form'), body = dialog.querySelector('[data-editor-body]');
    const message = dialog.querySelector('[role="status"]'), submit = form.querySelector('[type="submit"]');
    let draft = null, draftKey = '', saving = false, needsComparison = false;
    const persist = () => storageWrite(storage, draftKey, draft);
    const inputs = () => Object.fromEntries(new FormData(form).entries());
    const labels = { CREATE_FIELD: '新增 Field', EDIT_FIELD: '修改 Field', CREATE_TOPIC: '新增 Topic',
      LINK_TOPIC: '关联已有 Topic', EDIT_TOPIC: '修改 Topic', CREATE_TRACK: '新增 Track', EDIT_TRACK: '修改 Track 名称' };
    function open(operation, row) {
      const data = getData();
      if (!data) return;
      const context = { operation, field_id: row?.field?.field_id, topic_id: row?.topic?.topic_id,
        track_id: row?.track?.track_id };
      draftKey = `rstv4-research-draft-v1:${draftNamespace}:${data.workspace_id}:${key(operation, context.field_id, context.topic_id, context.track_id)}`;
      const record = operation === 'EDIT_FIELD' ? row.field : operation === 'EDIT_TOPIC' ? row.topic : row?.track;
      needsComparison = false;
      draft = storageRead(storage, draftKey) || { context, expected_digest: record?.metadata_digest,
        values: { name: record?.name || '', title: record?.title || '', description: record?.description || '',
          scope: '', research_type: '', topic_id: '' }, pending: null };
      dialog.querySelector('h2').textContent = labels[operation];
      const value = name => escapeHtml(draft.values[name] || '');
      const text = (name, label, max) => `<label>${label}<input name="${name}" value="${value(name)}" required maxlength="${max}" autocomplete="off"></label>`;
      let content = `<p>${escapeHtml([row?.field?.name, row?.topic?.name, row?.track?.title].filter(Boolean).join(' / ') || '全局研究结构')}</p>`;
      if (operation === 'LINK_TOPIC') {
        const topics = data.topics.filter(t => !data.field_topics.some(link => link.field_id === context.field_id && link.topic_id === t.topic_id));
        content += `<label>选择已有 Topic<select name="topic_id" required><option value="">请选择</option>${topics.map(t => `<option value="${escapeHtml(t.topic_id)}" ${draft.values.topic_id === t.topic_id ? 'selected' : ''}>${escapeHtml(t.name)}</option>`).join('')}</select></label><p>这会建立明确关联；已有 Track 的归属和科学状态保持独立。</p>`;
      } else if (operation.endsWith('TRACK')) {
        content += text('title', 'Track 名称', 500);
        if (operation === 'CREATE_TRACK') content += `<label>研究范围<textarea name="scope" maxlength="4000">${value('scope')}</textarea></label><label>研究类型<select name="research_type" required><option value="">请选择</option>${Object.entries(researchTypes).map(([id, label]) => `<option value="${id}" ${draft.values.research_type === id ? 'selected' : ''}>${label}</option>`).join('')}</select></label><p>创建后为 ACTIVE；尚未批准 Gap、采用 Snapshot 或启动 Project。</p>`;
        else content += `<p>研究范围：${escapeHtml(record.scope || '尚未设置')}<br>研究类型：${escapeHtml(researchTypes[record.research_type] || record.research_type)}。此处只修改名称。</p>`;
      } else {
        content += text('name', operation.includes('FIELD') ? 'Field 名称' : 'Topic 名称', 300);
        content += `<label>说明<textarea name="description" maxlength="4000">${value('description')}</textarea></label>`;
      }
      if (operation === 'EDIT_TOPIC') {
        const shared = data.field_topics.filter(link => link.topic_id === context.topic_id).map(link => data.fields.find(f => f.field_id === link.field_id)?.name).filter(Boolean);
        content += `<p>这是同一个 Topic，名称与说明会同步显示于：${escapeHtml(shared.join('、'))}。</p>`;
      }
      body.innerHTML = content;
      if (operation.startsWith('EDIT_') && draft.expected_digest !== record.metadata_digest && !draft.pending) {
        needsComparison = true;
        const comparison = dialog.ownerDocument.createElement('div');
        comparison.innerHTML = `<p>此草稿开始后，记录已经改变。当前保存的内容：</p><p>${escapeHtml(record.name || record.title)}<br>${escapeHtml(record.description || '')}</p><button type="button">已比较，使用当前版本继续此草稿</button>`;
        comparison.querySelector('button').addEventListener('click', () => {
          draft.expected_digest = record.metadata_digest;
          needsComparison = false;
          persist(); comparison.remove(); submit.disabled = false;
          message.textContent = '已采用当前版本作为比较基准；请核对草稿后保存。';
        });
        body.append(comparison);
      }
      message.textContent = draft.pending ? '上次提交结果尚未确认。再次提交将核对原请求，避免重复新增。' : '草稿会保存在本机；关闭后可以继续。';
      for (const input of body.querySelectorAll('input,textarea,select')) input.disabled = !!draft.pending;
      submit.disabled = operation.startsWith('EDIT_') && draft.expected_digest !== record.metadata_digest && !draft.pending;
      submit.textContent = draft.pending ? '核对原提交' : '保存';
      dialog.showModal();
    }
    form.addEventListener('input', () => {
      if (draft && !draft.pending) { draft.values = inputs(); message.textContent = persist() ? '草稿已保存到本机。' : '本机无法保存草稿，请保留此窗口。'; }
    });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (saving || !draft || needsComparison) return;
      if (!draft.pending) {
        draft.values = inputs();
        const c = draft.context, values = draft.values;
        const payload = { operation: c.operation, request_id: root.crypto.randomUUID() };
        if (c.operation !== 'CREATE_FIELD' && c.operation !== 'EDIT_FIELD') payload.field_id = c.field_id;
        if (c.operation === 'EDIT_FIELD') payload.field_id = c.field_id;
        if (c.operation === 'EDIT_TOPIC') payload.topic_id = c.topic_id;
        if (c.operation === 'LINK_TOPIC') payload.topic_id = values.topic_id;
        if (c.operation === 'EDIT_TRACK') payload.track_id = c.track_id;
        if (c.operation.startsWith('EDIT_')) payload.expected_digest = draft.expected_digest;
        if (c.operation === 'CREATE_TRACK') {
          payload.primary_topic_id = c.topic_id; payload.scope = values.scope || null; payload.research_type = values.research_type;
        }
        if (c.operation.endsWith('TRACK')) payload.title = values.title;
        else if (c.operation !== 'LINK_TOPIC') { payload.name = values.name; payload.description = values.description || null; }
        draft.pending = payload;
        if (!persist()) { draft.pending = null; message.textContent = '无法保存提交凭据；请恢复本机存储后重试。'; return; }
      }
      saving = true; submit.disabled = true; message.textContent = '正在核对保存结果…';
      for (const input of body.querySelectorAll('input,textarea,select')) input.disabled = true;
      let successfulResult;
      try {
        successfulResult = await fetchAction(draft.pending);
        try { storage.removeItem(draftKey); } catch { /* submitted receipt remains on server */ }
        draft = null; dialog.close();
      } catch (error) {
        if (error.status >= 400 && error.status < 500 && ![408, 429].includes(error.status)) {
          draft.pending = null; persist();
          for (const input of body.querySelectorAll('input,textarea,select')) input.disabled = false;
          message.textContent = `${error.message} 草稿仍在；关闭后更新列表，再比较最新内容。`;
        } else message.textContent = `${error.message} 提交结果尚未确认，保留原请求后再次核对。`;
        submit.textContent = draft.pending ? '核对原提交' : '保存';
      } finally { saving = false; submit.disabled = false; }
      if (successfulResult) await onSaved(successfulResult);
    });
    dialog.querySelector('[data-editor-close]').addEventListener('click', () => { if (!saving) dialog.close(); });
    dialog.addEventListener('cancel', event => { if (saving) event.preventDefault(); });
    return { open };
  }

  root.RSTV4Overview = { key, buildRows, visibleRows, reconcileState, keyboardTarget, createList, createEditor };
})(typeof window === 'undefined' ? globalThis : window);
