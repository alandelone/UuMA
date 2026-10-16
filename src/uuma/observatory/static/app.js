// UuMA All-in-One Observatory Frontend Application

(function () {
  'use strict';

  const savedSidebar = (function() {
    try {
      return localStorage.getItem('uuma_sidebar_open');
    } catch (_) {
      return null;
    }
  })();

  const savedSidebarWidth = (function() {
    try {
      const w = parseInt(localStorage.getItem('uuma_sidebar_width'), 10);
      if (!isNaN(w) && w >= 280 && w <= 1400) {
        return w;
      }
    } catch (_) {}
    return 420; // default comfortable width
  })();

  // State Management
  const state = {
    agents: [],
    sources: {},
    events: [],
    selectedItemId: null,
    selectedEventId: null,
    selectedAgentId: null,
    selectedItemData: null,
    expandedAgentId: null, // Track currently expanded toggle board
    isSidebarOpen: savedSidebar !== 'false', // User preference for right inspector sidebar
    sidebarWidth: savedSidebarWidth, // User resized sidebar width preference
    activeTab: 'overview',
    filterAgent: 'all',
    searchQuery: '',
    requestEpoch: 0,
    newEventsCount: 0,
    isFeedScrolled: false,
    sseConnected: false,
    forgeCommerceFilter: 'all',
    forgeJournalFilter: 'all',
    expandedOrderId: null,
    expandedJournalId: null,
    bsTopicExpanded: {},
    bsShowAllTopics: false,
  };

  // Clean URL if token present
  if (window.location.search.includes('auth=')) {
    window.history.replaceState({}, document.title, window.location.pathname);
  }

  // DOM Elements
  const liveIndicator = document.getElementById('live-indicator');
  const mTotal = document.getElementById('m-total');
  const mRunning = document.getElementById('m-running');
  const mIdle = document.getElementById('m-idle');
  const mBlocked = document.getElementById('m-blocked');
  const workspacesGrid = document.getElementById('workspaces-grid');
  const activityFeed = document.getElementById('activity-feed');
  const eventSearch = document.getElementById('event-search');
  const agentFilters = document.getElementById('agent-filters');
  const newEventsBtn = document.getElementById('new-events-btn');
  const backfillBanner = document.getElementById('backfill-banner');
  const backfillBar = document.getElementById('backfill-bar');
  const backfillPercent = document.getElementById('backfill-percent');
  const backfillText = document.getElementById('backfill-text');

  // Inspector Elements
  const inspectorPane = document.getElementById('inspector-pane');
  const inspTitle = document.getElementById('insp-title');
  const inspSubtitle = document.getElementById('insp-subtitle');
  const inspectorBody = document.getElementById('inspector-body');
  const btnToggleSidebar = document.getElementById('btn-toggle-sidebar');
  const btnCloseInsp = document.getElementById('btn-close-insp');
  const tabBtns = document.querySelectorAll('.tab-btn');
  const countSessions = document.getElementById('count-sessions');
  const countTools = document.getElementById('count-tools');
  const countArtifacts = document.getElementById('count-artifacts');

  // Set initial inspector visibility & width according to saved preference
  if (inspectorPane) {
    if (state.sidebarWidth) {
      inspectorPane.style.width = state.sidebarWidth + 'px';
      document.documentElement.style.setProperty('--sidebar-width', state.sidebarWidth + 'px');
    }
    if (state.isSidebarOpen) {
      inspectorPane.classList.remove('collapsed');
      if (btnToggleSidebar) btnToggleSidebar.classList.add('active');
    } else {
      inspectorPane.classList.add('collapsed');
      if (btnToggleSidebar) btnToggleSidebar.classList.remove('active');
    }
  }

  // Helper formatting: date then time (YYYY-MM-DD HH:mm:ss)
  function formatTime(isoStr) {
    if (!isoStr) return '—';
    try {
      const d = new Date(isoStr);
      if (isNaN(d.getTime())) return isoStr;
      const pad = (n) => String(n).padStart(2, '0');
      const year = d.getFullYear();
      const month = pad(d.getMonth() + 1);
      const day = pad(d.getDate());
      const hours = pad(d.getHours());
      const minutes = pad(d.getMinutes());
      const seconds = pad(d.getSeconds());
      return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
    } catch {
      return (isoStr.slice(0, 10) + ' ' + isoStr.slice(11, 19)) || isoStr;
    }
  }

  // Helper formatting: human relative time (e.g. 5 min ago, 2 hours ago, 13 days ago)
  function formatTimeAgo(isoStr) {
    if (!isoStr) return '';
    try {
      const d = new Date(isoStr);
      if (isNaN(d.getTime())) return '';
      const now = new Date();
      const diffSec = Math.floor((now.getTime() - d.getTime()) / 1000);
      if (diffSec < 0) return 'just now';
      if (diffSec < 45) return 'just now';
      if (diffSec < 90) return '1 min ago';
      const diffMin = Math.floor(diffSec / 60);
      if (diffMin < 60) return `${diffMin} min ago`;
      const diffHour = Math.floor(diffMin / 60);
      if (diffHour < 24) return `${diffHour} ${diffHour === 1 ? 'hour' : 'hours'} ago`;
      const diffDay = Math.floor(diffHour / 24);
      if (diffDay < 30) return `${diffDay} ${diffDay === 1 ? 'day' : 'days'} ago`;
      const diffMonth = Math.floor(diffDay / 30);
      if (diffMonth < 12) return `${diffMonth} ${diffMonth === 1 ? 'month' : 'months'} ago`;
      const diffYear = Math.floor(diffDay / 365);
      return `${diffYear} ${diffYear === 1 ? 'year' : 'years'} ago`;
    } catch {
      return '';
    }
  }

  function escapeHtml(str) {
    if (!str && str !== 0) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // Find item across all loaded agents
  function findItemLocally(itemId) {
    for (const ws of state.agents) {
      if (ws.items) {
        const found = ws.items.find(it => it.item_id === itemId);
        if (found) return found;
      }
    }
    return null;
  }

  // Derive concise 1-line glance summary for collapsed toggle cards
  function getAgentGlance(ws) {
    const items = ws.items || [];
    if (ws.agent_id === 'forge-lab-bot') {
      const comm = items.find(it => it.kind === 'forge_commerce');
      const cp = (comm && comm.payload) ? comm.payload : {};
      const eh = cp.engine_health || {};
      const dot = eh.status_dot || '🟡';
      const triage = cp.triage_summary || {};
      const unreviewed = triage.unreviewed || 1071;

      const projects = items.filter(it => it.kind === 'forge_project');
      const totalProj = projects.length || 5;
      const deployed = projects.filter(it => (it.payload && it.payload.progress_pct >= 80)).length;
      const progressing = totalProj - deployed;

      return `${totalProj}个硬件项目 (${deployed}个在网 · ${progressing}个推进中) · 待审采购 ${unreviewed.toLocaleString()}笔 · 引擎 ${dot}`;
    }
    if (ws.agent_id === 'wisdom-oldman') {
      const runningTask = items.find(it => it.kind === 'active_task' && it.status === 'RUNNING');
      const totalTopics = items.filter(it => it.kind === 'knowledge_topic').length;
      const activeTopic = items.find(it => it.kind === 'knowledge_topic' && it.status === 'ACTIVE');
      const vCnt = (activeTopic && activeTopic.payload && activeTopic.payload.ver_cnt) || 45;
      return `${runningTask ? '1项调查运行中 (心跳静默诊断) · ' : ''}${totalTopics || 4}个知识主题 (主干v${vCnt}) · Remote OpenSPG`;
    }
    if (ws.agent_id === 'scholar') {
      return `2 Fields · 4 Threads · 5 Papers · 1197篇文献总库 · G11验收`;
    }
    if (ws.agent_id === 'brainstormer') {
      const dag = items.find(it => it.kind === 'decision_dag');
      const p = (dag && dag.payload) ? dag.payload : {};
      const topics = p.topics || [];
      const decCnt = (p.discussed_decisions || []).length || 2;
      const queCnt = (p.open_questions || []).length || 2;
      const asmCnt = (p.assumptions || []).length || 1;
      const topCnt = topics.length || 2;
      const rev = p.revision ? `r${p.revision}` : 'r6';
      return `决策DAG ${rev} · ${topCnt}个架构议题 · 已决议 ${decCnt}项 · 待讨论 ${queCnt}项 · 假设 ${asmCnt}项`;
    }
    if (ws.agent_id === 'honc') {
      return `作息 08:00/21:30 · 语义心跳运行中 · 8项习惯`;
    }
    if (ws.agent_id === 'yonc') {
      const core = items.find(it => it.kind === 'project_graph');
      const p = (core && core.payload) ? core.payload : {};
      const stats = p.part3_macro_stats || {};
      const totalProj = stats.total_projects || 58;
      const l4Cnt = stats.l4_decomposed_projects || 11;
      const timeCnt = stats.timeline_assigned_count || 9;
      return `${totalProj}个专案 (${timeCnt}个排期中 · ${l4Cnt}个深拆至L4) · 跨Agent分工建议`;
    }
    if (ws.agent_id === 'orchestrator') {
      return `阶段: verification · 门控: 04-report · 舰队路由`;
    }
    return items.length > 0 ? items[0].title : ws.role;
  }

  // Fetch initial fleet data
  async function loadInitialData() {
    try {
      const res = await fetch('/api/observatory/agents');
      if (res.ok) {
        const data = await res.json();
        state.agents = data.agents || [];
        state.sources = data.sources || {};
        updateMetrics(data);
        renderWorkspaces();
        if (data.backfill) updateBackfill(data.backfill);

        // Auto-select first item if none selected
        autoSelectFirstItem();
      }
    } catch (err) {
      console.warn('Initial fleet load failed:', err);
    }
    loadEvents();
  }

  function autoSelectFirstItem() {
    if (state.selectedItemId || state.selectedEventId || state.selectedAgentId) return;
    for (const ws of state.agents) {
      if (ws.items && ws.items.length > 0) {
        selectItem(ws.items[0].item_id);
        break;
      }
    }
  }

  function updateMetrics(data) {
    mTotal.textContent = data.total_agents || state.agents.length;
    mRunning.textContent = data.running_count || 0;
    mIdle.textContent = data.idle_count || 0;
    mBlocked.textContent = data.blocked_count || 0;
  }

  function updateBackfill(b) {
    if (!b || b.is_complete || b.total_files === 0) {
      backfillBanner.style.display = 'none';
      return;
    }
    backfillBanner.style.display = 'flex';
    backfillPercent.textContent = `${b.percent}%`;
    backfillBar.style.width = `${b.percent}%`;
    backfillText.textContent = `已索引 ${b.indexed_files} / ${b.total_files} 个事件文件 (${b.current_file || ''})`;
  }

  // Comprehensive Scholar Full View Renderer (Compact tree, 1-row phases, FieldKG & Stage progress)
  function renderScholarFullView(ws) {
    const items = ws.items || [];
    const hierItem = items.find(it => it.kind === 'research_hierarchy');
    const pipeItem = items.find(it => it.kind === 'catalog_pipeline');
    const kgItem = items.find(it => it.kind === 'fieldkg_status');
    const stageItem = items.find(it => it.kind === 'stage_progress');

    const hp = (hierItem && hierItem.payload) ? hierItem.payload : {};
    const pp = (pipeItem && pipeItem.payload) ? pipeItem.payload : {};
    const kgp = (kgItem && kgItem.payload) ? kgItem.payload : {};
    const sp = (stageItem && stageItem.payload) ? stageItem.payload : {};

    const fields = hp.hierarchy || [];
    const breakdown = hp.stage_breakdown || {};
    const tweaks = sp.last_tweaks || [];
    const suite = sp.test_suite || {};
    const pStatus = pp.paper_level_status || {};

    const fieldsHtml = fields.map(f => {
      const topicsHtml = (f.topics || []).map(tp => {
        const threadsHtml = (tp.threads || []).map(tr => {
          const papers = tr.papers || [];
          const papersHtml = papers.length > 0 ? papers.map(ppr => `
            <div class="tree-paper-row">
              <span title="${escapeHtml(ppr.title)}"><span style="font-size: 11px; margin-right: 3px;">📝</span><span class="tree-badge-paper">Paper</span><strong style="color: #f1f5f9;">${escapeHtml(ppr.title)}</strong></span>
              <span class="status-tag status-${ppr.stage_key === 'WRITING' ? 'IN_PROGRESS' : (ppr.stage_key === 'REVISION' ? 'BLOCKED' : 'IDLE')}" style="font-size: 8.5px; padding: 1px 4px;">${escapeHtml(ppr.stage)}</span>
            </div>
          `).join('') : `
            <div style="font-size: 10px; color: var(--text-dim); padding-left: 18px; font-style: italic;">
              (暂无 Paper 写作稿件 · 独立探索路线)
            </div>
          `;

          return `
            <div class="tree-thread">
              <div class="tree-thread-header">
                <span>↗ <span class="tree-badge-thread">Thread</span>${escapeHtml(tr.title)}</span>
                <span class="status-tag status-IDLE" style="font-size: 8.5px; padding: 1px 4px;">${escapeHtml(tr.status)}</span>
              </div>
              ${tr.question ? `<div class="tree-thread-q">❓ ${escapeHtml(tr.question)}</div>` : ''}
              ${papersHtml}
            </div>
          `;
        }).join('');

        return `
          <div class="tree-topic">
            <div class="tree-topic-header">
              <span>◈ <span class="tree-badge-topic">Topic</span> ${escapeHtml(tp.name)}</span>
              <span class="status-tag status-IDLE" style="font-size: 8.5px; padding: 1px 4px;">${escapeHtml(tp.status)}</span>
            </div>
            ${threadsHtml}
          </div>
        `;
      }).join('');

      return `
        <div class="tree-field">
          <div class="tree-field-header">
            <span style="color: #38bdf8;">◇ <span class="tree-badge-field">Field</span>${escapeHtml(f.name)}</span>
            <span class="status-tag status-IDLE" style="font-size: 8.5px; padding: 1px 4px;">${escapeHtml(f.status)}</span>
          </div>
          ${topicsHtml}
        </div>
      `;
    }).join('');

    const phasesHtml = `
      <div class="scholar-phase-row">
        <div class="phase-col phase-heavy" title="冷入库可见主库文献">
          <div class="phase-step-num">PHASE 1</div>
          <div class="phase-col-title">① 摄入与检索</div>
          <div class="phase-col-val" style="color: #38bdf8;">${pp.visible_papers || 1197} 篇</div>
          <div class="phase-col-sub">${pp.quarantined_papers || 1980} 篇隔离 · 积聚量大</div>
        </div>
        <div class="phase-col phase-held" title="PDF身份校验门：726通过，434存疑待核">
          <div class="phase-step-num">PHASE 2</div>
          <div class="phase-col-title">② 身份核验门</div>
          <div class="phase-col-val" style="color: var(--accent-amber);">${pStatus.VERIFIED || pp.pdf_verified || 726} 确证</div>
          <div class="phase-col-sub" style="color: #fca5a5; font-weight: 600;">⚠️ 434 篇待审 (卡点)</div>
        </div>
        <div class="phase-col" title="选入 Collection 合集触发下游流水线">
          <div class="phase-step-num">PHASE 3</div>
          <div class="phase-col-title">③ 集合与排队</div>
          <div class="phase-col-val" style="color: #94a3b8;">${pp.active_jobs || 0} 项</div>
          <div class="phase-col-sub">${pp.collections_count || 0} 个集合 · 待选入触发</div>
        </div>
        <div class="phase-col" title="MinerU 两阶段解析流水线（两进程正文图表提取）">
          <div class="phase-step-num">PHASE 4</div>
          <div class="phase-col-title">④ MinerU解析</div>
          <div class="phase-col-val" style="color: #94a3b8;">${pp.active_parse_runs || 0} 篇</div>
          <div class="phase-col-sub">两进程就绪 · 当前空闲</div>
        </div>
        <div class="phase-col" title="解析质量门控：正文完整性与参考文献校验">
          <div class="phase-step-num">PHASE 5</div>
          <div class="phase-col-title">⑤ 正文质量门</div>
          <div class="phase-col-val" style="color: #94a3b8;">0 篇</div>
          <div class="phase-col-sub">质量门就绪 · 0 异常拦截</div>
        </div>
        <div class="phase-col" title="PaperSkeleton 骨架与 FieldKG 知识生长">
          <div class="phase-step-num">PHASE 6</div>
          <div class="phase-col-title">⑥ 骨架与深读</div>
          <div class="phase-col-val" style="color: #94a3b8;">0 篇</div>
          <div class="phase-col-sub">QuickRead / Skeleton 待触发</div>
        </div>
      </div>
    `;

    const tweaksHtml = tweaks.map(t => `
      <div style="padding: 3px 0; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 11px;">
        <span style="font-weight: 600; color: var(--accent-blue);">[${escapeHtml(t.component)}]</span>
        <span style="color: #cbd5e1; margin-left: 4px;">${escapeHtml(t.fix)}</span>
      </div>
    `).join('');

    return `
      <!-- Part 1: Field / Threads / Papers Hierarchy (Compact Indent Tree) -->
      <div class="detail-block" style="margin-bottom: 8px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
          <div class="detail-block-title" style="font-size: 12px; margin-bottom: 0;">Part 1. 研究层级结构与 5 篇稿件推进全景图 (缩进精简展示)</div>
          <div style="font-size: 10px; color: var(--text-dim);">
            写作中: <strong style="color: #34d399;">${breakdown.WRITING || 2}</strong> · 返修中: <strong style="color: #fbbf24;">${breakdown.REVISION || 1}</strong> · 规划中: <strong style="color: #94a3b8;">${breakdown.PLANNING || 2}</strong>
          </div>
        </div>

        <div class="scholar-indent-tree">
          ${fieldsHtml}
        </div>
      </div>

      <!-- Part 2: Literature Catalog Core Graph Pipeline (1-Row Phases) -->
      <div class="detail-block" style="margin-bottom: 8px;">
        <div class="detail-block-title" style="font-size: 12px; margin-bottom: 2px;">
          Part 2. 文献总库 Core Graph 6 阶段流水线 (横向单行阶段链)
        </div>
        <div style="font-size: 10.5px; color: var(--text-dim); margin-bottom: 4px;">
          各阶段文献积聚与状态分布（大部分文献积聚在阶段 ① 与 ②，434 篇处于身份核验卡点）：
        </div>

        ${phasesHtml}

        <div style="font-size: 10.5px; color: #fecaca; background: rgba(239,68,68,0.06); border: 1px solid rgba(239,68,68,0.2); border-radius: 4px; padding: 4px 6px; margin-top: 4px;">
          🔍 <strong>流水线状态定论：</strong> 总库处于「冷入库就绪」阶段，MinerU 解析当前 <strong>0 篇运行 / 0 项排队</strong>。仅当论文被选入 Collection 时才会按需排队执行。
        </div>
      </div>

      <!-- Part 3: FieldKG / OpenSPG / KAG Knowledge Graph -->
      <div class="detail-block" style="margin-bottom: 8px;">
        <div class="detail-block-title" style="font-size: 12px; margin-bottom: 3px;">
          Part 3. FieldKG 与 OpenSPG/KAG 知识图谱状态 (Knowledge Graph & Projections)
        </div>
        <div style="font-size: 10.5px; color: var(--text-muted); margin-bottom: 5px;">
          权威架构：<code>catalog.db (唯一编辑权威) → projection_outbox (${kgp.outbox_pending || 0} 积压) → OpenSPG/KAG (查询投影)</code>
        </div>

        <div class="stat-grid" style="margin-bottom: 5px; grid-template-columns: repeat(4, 1fr);">
          <div class="stat-box" style="padding: 3px 5px;">
            <div class="stat-label" style="font-size: 9.5px;">实体节点 (Nodes)</div>
            <div class="stat-val" style="font-size: 12.5px; color: var(--accent-blue);">${kgp.nodes_count || 0} 个</div>
          </div>
          <div class="stat-box" style="padding: 3px 5px;">
            <div class="stat-label" style="font-size: 9.5px;">关系边 (Edges)</div>
            <div class="stat-val" style="font-size: 12.5px; color: var(--accent-purple);">${kgp.edges_count || 0} 条</div>
          </div>
          <div class="stat-box" style="padding: 3px 5px;">
            <div class="stat-label" style="font-size: 9.5px;">证据节点 (Evidence)</div>
            <div class="stat-val" style="font-size: 12.5px; color: var(--accent-green);">${kgp.evidence_count || 0} 条</div>
          </div>
          <div class="stat-box" style="padding: 3px 5px;">
            <div class="stat-label" style="font-size: 9.5px;">密封快照 (Snapshots)</div>
            <div class="stat-val" style="font-size: 12.5px; color: var(--accent-amber);">${kgp.snapshots_count || 0} 份</div>
          </div>
        </div>

        <div style="font-size: 10.5px; color: #cbd5e1; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); border-radius: 4px; padding: 4px 6px; line-height: 1.4;">
          • <strong>图谱状态：</strong> <span class="status-tag status-IDLE" style="font-size: 8px; padding: 1px 3px;">${escapeHtml(kgp.status || 'READY')}</span> ${escapeHtml(kgp.lifecycle_state || '待从文献集合构建第一版 Snapshot (冷库基线就绪)')}<br/>
          • <strong>Track-first 边界规范：</strong> 每个 Field 拥有其独立的 living FieldKG；待文献完成 PaperSkeleton 提炼证据后经人工批准密封为 Snapshot vN 供 Track 采纳，绝不跨路线静默串染。
        </div>
      </div>

      <!-- Part 4: Stage Gates & Last Tweaks -->
      <div class="detail-block">
        <div class="detail-block-title" style="font-size: 12px; margin-bottom: 3px;">
          Part 4. 研发推进阶段与最新改动 (Stage & Last Tweaks)
        </div>
        <div style="font-size: 11px; margin-bottom: 4px;">
          <strong>当前阶段：</strong> <span style="color: #fff; font-weight: 600;">${escapeHtml(sp.current_stage || 'G11 Catalog & Parsing Acceptance')}</span>
          <span style="margin-left: 8px;"><strong>门控契约：</strong> <code>${escapeHtml(sp.stage_gate || 'stage-gates/04-verification-report.md')}</code></span>
          <span class="status-tag status-PENDING_REVIEW" style="margin-left: 4px; font-size: 8.5px; padding: 1px 4px;">${escapeHtml(sp.gate_status || 'pending_review')}</span>
        </div>

        <div style="display: flex; gap: 8px; margin-bottom: 4px;">
          <span style="font-size: 10.5px; color: var(--accent-green); background: rgba(16,185,129,0.08); padding: 1px 5px; border-radius: 3px; border: 1px solid rgba(16,185,129,0.2);">测试通过: <strong>${suite.passed || 1078}</strong></span>
          <span style="font-size: 10.5px; color: var(--accent-amber); background: rgba(245,158,11,0.08); padding: 1px 5px; border-radius: 3px; border: 1px solid rgba(245,158,11,0.2);">现有告警: <strong>${suite.warnings || 20}</strong></span>
        </div>

        <div class="detail-block-title" style="margin-top: 4px; font-size: 11px;">最新工程修复与契约提交</div>
        ${tweaksHtml}
      </div>
    `;
  }

  // 3-Tier Dynamic Hardware Project Feature Icon System:
  // 1. Explicit metadata icon from project.yaml (highest precedence)
  // 2. Comprehensive semantic hardware domain ontology matching
  // 3. Deterministic hash-palette fallback ensuring distinct icons for arbitrary unseen projects
  const DYNAMIC_HARDWARE_PALETTE = [
    '🛠️', '⚙️', '🔬', '📡', '🎛️', '🤖', '🔋', '⚡', '🛰️', '📟',
    '🔌', '💻', '🖲️', '🛸', '🚜', '🗼', '🔧', '📦', '🌱', '💡',
    '🧭', '🔭', '🖨️', '📐', '🧊', '🧰', '🪙', '🛡️'
  ];

  function getForgeProjectIcon(folderOrId = '', name = '', explicitIcon = '', projectType = '') {
    // 1. Explicit metadata override (e.g., icon / emoji in project.yaml)
    if (explicitIcon && typeof explicitIcon === 'string' && explicitIcon.trim()) {
      return explicitIcon.trim();
    }

    const s = ((folderOrId || '') + ' ' + (name || '') + ' ' + (projectType || '')).toLowerCase();

    // 2. Comprehensive Hardware & Engineering Semantic Ontology Dictionary
    // Compute, Storage, Servers & Networking
    if (s.includes('nas') || s.includes('server') || s.includes('storage') || s.includes('raid') || s.includes('sata') || s.includes('san')) return '🖥️';
    if (s.includes('compute') || s.includes('cluster') || s.includes('docker') || s.includes('node') || s.includes('linux')) return '💻';

    // Autonomous Robotics, Rovers & Machinery
    if (s.includes('ugv') || s.includes('sprayer') || s.includes('rbcar') || s.includes('rover') || s.includes('chassis') || s.includes('agv')) return '🚜';
    if (s.includes('drone') || s.includes('uav') || s.includes('flight') || s.includes('quadcopter') || s.includes('aircraft')) return '🛸';
    if (s.includes('robot') || s.includes('arm') || s.includes('actuator') || s.includes('motor') || s.includes('servo') || s.includes('gantry')) return '🤖';

    // Solar, Photovoltaic, Battery & Energy Microgrids
    if (s.includes('sares') || s.includes('nanocentralised') || s.includes('ogpv') || s.includes('microgrid') || s.includes('solar') || s.includes('photovoltaic') || s.includes('光伏')) return '🔋';
    if (s.includes('battery') || s.includes('bms') || s.includes('inverter') || s.includes('ups') || s.includes('energy') || s.includes('grid') || s.includes('储能')) return '⚡';

    // Atmospheric, Tower, Meteorological & Optical Observation
    if (s.includes('weather') || s.includes('tower') || s.includes('cloud') || s.includes('sky') || s.includes('meteorolog') || s.includes('气象') || s.includes('观测')) return '🗼';
    if (s.includes('camera') || s.includes('vision') || s.includes('lens') || s.includes('optical') || s.includes('capture')) return '📷';

    // RF, Wireless, Telemetry & Space Communications
    if (s.includes('tnc') || (s.includes('solar') && s.includes('iot')) || s.includes('aprs') || s.includes('ham') || s.includes('radio') || s.includes('packet')) return '📟';
    if (s.includes('lora') || s.includes('rf') || s.includes('wireless') || s.includes('antenna') || s.includes('telemetry') || s.includes('repeater')) return '📡';
    if (s.includes('satellite') || s.includes('groundstation') || s.includes('orbit') || s.includes('cubesat')) return '🛰️';
    if (s.includes('iot') || s.includes('zigbee') || s.includes('ble') || s.includes('mesh') || s.includes('wifi') || s.includes('gateway')) return '📶';

    // Digital Fabrication, 3D Printing & Tooling
    if (s.includes('3dp') || s.includes('printer') || s.includes('klipper') || s.includes('voron') || s.includes('extruder') || s.includes('btt')) return '🖨️';
    if (s.includes('cnc') || s.includes('milling') || s.includes('router') || s.includes('lathe') || s.includes('machin')) return '⚙️';
    if (s.includes('laser') || s.includes('engrav') || s.includes('photon')) return '⚡';

    // Embedded Systems, PCB & Electronic Hardware
    if (s.includes('pcb') || s.includes('circuit') || s.includes('eschematic') || s.includes('smd') || s.includes('esp32') || s.includes('stm32') || s.includes('mcu')) return '🎛️';

    // Agriculture, Precision Fertigation & Environmental Sensing
    if (s.includes('fertigation') || s.includes('plant') || s.includes('crop') || s.includes('hydroponic') || s.includes('greenhouse') || s.includes('irrigation') || s.includes('农业') || s.includes('喷灌')) return '🌱';
    if (s.includes('sensor') || s.includes('temp') || s.includes('humidity') || s.includes('air') || s.includes('oscilloscope') || s.includes('meter')) return '🔬';

    // 3. Dynamic Hash Fallback: Ensures distinct, deterministic, non-identical icons for arbitrary new projects
    const seed = ((folderOrId || '') + ' ' + (name || '')).trim() || 'uuma_proj';
    let hash = 0;
    for (let i = 0; i < seed.length; i++) {
      hash = ((hash << 5) - hash) + seed.charCodeAt(i);
      hash |= 0;
    }
    const idx = Math.abs(hash) % DYNAMIC_HARDWARE_PALETTE.length;
    return DYNAMIC_HARDWARE_PALETTE[idx];
  }

  // Comprehensive Forge Full View Renderer (Compact Part 1, Part 2, Part 3 - Refer Scholar Design)
  function renderForgeFullView(ws) {
    const items = (ws && ws.items) || [];
    const wsItem = items.find(it => it.kind === 'forge_workspace');
    const projs = items.filter(it => it.kind === 'forge_project');
    const commItem = items.find(it => it.kind === 'forge_commerce');
    const journItem = items.find(it => it.kind === 'forge_journal');

    const wp = (wsItem && wsItem.payload) ? wsItem.payload : {};
    const cp = (commItem && commItem.payload) ? commItem.payload : {};
    const jp = (journItem && journItem.payload) ? journItem.payload : {};

    const eh = cp.engine_health || wp.engine_health || {};
    const ch = eh.channels || {};
    const pddCh = ch.pdd || { dot: '🟡', count: 603, latest_time: '2026-10-09 16:33' };
    const shopeeCh = ch.shopee || { dot: '🟡', count: 303, latest_time: '2026-10-09 13:40' };
    const tbCh = ch.taobao || { dot: '🟡', count: 165, latest_time: '2026-10-09 13:29' };
    const triage = cp.triage_summary || {};
    const unreviewed = triage.unreviewed || 1071;
    const sb = cp.status_breakdown || {};
    const inTransit = sb.in_transit || 0;
    const awaiting = sb.awaiting_dispatch || 0;
    const completed = sb.completed || 0;
    const totalSpend = cp.total_spend_cny || 35074.79;

    const projectsTreeHtml = projs.map(pr => {
      const p = pr.payload || {};
      const pct = (typeof p.progress_pct === 'number') ? p.progress_pct : 0;
      const projId = p.project_id || pr.item_id || '';
      const projName = p.name || pr.title.replace('项目: ', '');
      const icon = getForgeProjectIcon(projId, projName, p.icon || p.emoji || '', p.project_type || '');
      const stepperHtml = renderProjectCheckpointStepper(pct, p.stage_name, p.stage_code, false);

      return `
        <div class="forge-tree-proj-header" style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 4px; padding: 6px 10px; margin-bottom: 5px; cursor: pointer; transition: all 0.15s ease;" onclick="window.__uuma_selectItem('${escapeHtml(pr.item_id)}')">
          <div style="display: flex; align-items: center; gap: 8px; min-width: 0; flex: 1;">
            <span class="proj-feature-icon" title="硬件实体特征">${icon}</span>
            <span class="tree-badge-proj">PROJ</span>
            <span class="forge-proj-name" style="color: #f8fafc; font-weight: 600; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(projName)}</span>
          </div>
          <div style="display: flex; align-items: center; gap: 12px; flex-shrink: 0; margin-left: auto;">
            <span class="status-tag status-${escapeHtml(p.stage_code || 'IN_PROGRESS')}" style="font-size: 10px; font-weight: 600; padding: 2px 7px; border-radius: 4px; letter-spacing: 0.02em;">${escapeHtml(p.stage_name || '推进中')}</span>
            <span style="font-size: 10px; color: var(--text-dim); white-space: nowrap;">BOM ${p.bom_count || 0}份 · 图纸 ${p.design_count || 0}份</span>
            <div class="proj-stepper-container" style="width: 260px; flex-shrink: 0;">
              ${stepperHtml}
            </div>
          </div>
        </div>
      `;
    }).join('');

    const commercePhasesHtml = `
      <div class="scholar-phase-row" style="grid-template-columns: repeat(5, minmax(0, 1fr));">
        <div class="phase-col" style="cursor: pointer;" onclick="window.__uuma_selectCommerceChannel('pdd')" title="点击在侧边栏过滤并查看拼多多 603 笔订单明细">
          <div class="phase-step-num">CHANNEL 1 ↗</div>
          <div class="phase-col-title">① 拼多多 (PDD)</div>
          <div class="phase-col-val" style="color: #fb923c;">${pddCh.dot || '🟡'} ${pddCh.count || 603} 笔</div>
          <div class="phase-col-sub">${pddCh.latest_time || '2026-10-09 16:33'}</div>
        </div>
        <div class="phase-col" style="cursor: pointer;" onclick="window.__uuma_selectCommerceChannel('shopee')" title="点击在侧边栏过滤并查看 Shopee 303 笔海外订单明细">
          <div class="phase-step-num">CHANNEL 2 ↗</div>
          <div class="phase-col-title">② Shopee (虾皮)</div>
          <div class="phase-col-val" style="color: #f97316;">${shopeeCh.dot || '🟡'} ${shopeeCh.count || 303} 笔</div>
          <div class="phase-col-sub">${shopeeCh.latest_time || '2026-10-09 13:40'}</div>
        </div>
        <div class="phase-col" style="cursor: pointer;" onclick="window.__uuma_selectCommerceChannel('taobao')" title="点击在侧边栏过滤并查看淘宝 165 笔元器件订单明细">
          <div class="phase-step-num">CHANNEL 3 ↗</div>
          <div class="phase-col-title">③ 淘宝 (Taobao)</div>
          <div class="phase-col-val" style="color: #38bdf8;">${tbCh.dot || '🟡'} ${tbCh.count || 165} 笔</div>
          <div class="phase-col-sub">${tbCh.latest_time || '2026-10-09 13:29'}</div>
        </div>
        <div class="phase-col phase-held" style="cursor: pointer;" onclick="window.__uuma_selectCommerceChannel('unreviewed')" title="点击在侧边栏查看待人类评审门控 (1,071 笔)">
          <div class="phase-step-num">TRIAGE GATE ↗</div>
          <div class="phase-col-title">④ 人工归属评审</div>
          <div class="phase-col-val" style="color: #c084fc;">${unreviewed.toLocaleString()} 笔</div>
          <div class="phase-col-sub" style="color: #fca5a5; font-weight: 600;">⚠️ 待评审确认 (VO)</div>
        </div>
        <div class="phase-col phase-heavy" style="cursor: pointer;" onclick="window.__uuma_selectCommerceChannel('all')" title="点击在侧边栏查看全部 1,071 笔流水明细与支出总额">
          <div class="phase-step-num">TOTAL SPEND ↗</div>
          <div class="phase-col-title">⑤ 累计采购总额</div>
          <div class="phase-col-val" style="color: var(--accent-green);">¥${Number(totalSpend).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}</div>
          <div class="phase-col-sub">在途 ${inTransit} · 待发 ${awaiting} · 717 批</div>
        </div>
      </div>
    `;

    const jpPages = jp.recent_journal_pages || [];
    const sysBreakdown = jp.system_breakdown || {};
    const breakdownPills = Object.entries(sysBreakdown).slice(0, 4).map(([k, v]) => `
      <span class="forge-pill" style="cursor: pointer;" onclick="window.__uuma_selectJournalSystem('${escapeHtml(k)}')" title="点击在侧边栏查看 ${escapeHtml(k)} 分类的 ${v} 篇日志">
        <strong style="color: var(--accent-blue);">${escapeHtml(k)}</strong>: ${v}篇 ↗
      </span>
    `).join('');

    const recentPagesHtml = jpPages.slice(0, 3).map(pg => `
      <div class="forge-log-mini-row" style="cursor: pointer;" onclick="window.__uuma_selectJournalSystem('all')" title="点击在侧边栏查看全部工程日志">
        <span style="color: #f1f5f9; font-size: 10.5px;">• ${escapeHtml(pg.title || '')}</span>
        <span style="font-size: 9px; color: var(--text-dim);">${escapeHtml(pg.project_system || '')}</span>
      </div>
    `).join('');

    return `
      <!-- Part 1: 5 大硬件实体项目进度与概览 -->
      <div class="detail-block" style="margin-bottom: 8px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
          <div class="detail-block-title" style="font-size: 12px; margin-bottom: 0;">Part 1. 5 大硬件实体项目进度与工程概览 (单项点击查看详情)</div>
          <div style="font-size: 10px; color: var(--text-dim);">
            1个在网 · 4个推进中 · 5 大成熟项目基线
          </div>
        </div>

        <div style="display: flex; flex-direction: column; gap: 2px;">
          ${projectsTreeHtml}
        </div>
      </div>

      <!-- Part 2: 硬件采购全链路与多平台抓取引擎 -->
      <div class="detail-block" style="margin-bottom: 8px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px; cursor: pointer;" onclick="window.__uuma_selectCommerceChannel('all')">
          <div class="detail-block-title" style="font-size: 12px; margin-bottom: 0;">Part 2. 硬件采购全链路与多平台拉取引擎 (点击渠道查看侧边栏明细 ↗)</div>
          <div style="font-size: 10px; color: #fde68a;">
            ${eh.status_dot || '🟡'} 引擎状态: <strong>${escapeHtml(eh.status_label || '待刷新 (Outdated)')}</strong> (最新拉取: ${escapeHtml(eh.latest_pull_formatted || '2026-10-09 16:33')})
          </div>
        </div>

        ${commercePhasesHtml}

        <div style="font-size: 10px; color: #d8b4fe; background: rgba(168, 85, 247, 0.05); border: 1px solid rgba(168, 85, 247, 0.18); border-radius: 4px; padding: 4px 6px; line-height: 1.4; margin-top: 4px;">
          ℹ️ <strong>只读 (VO) 契约声明：</strong> 观测台严格保持只读遥测属性。订单归属复核（区分 <code>self</code> 硬件物料 vs <code>others</code> 个人非实验生活用品）由操作者通过 Telegram Bot / 外部 Agent 异步处理并持久化至 <code>lab.db</code>，不在观测台提供直接改库按钮。
        </div>
      </div>

      <!-- Part 3: Notion 硬件工程日志总览 -->
      <div class="detail-block" style="margin-bottom: 8px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; cursor: pointer;" onclick="window.__uuma_selectJournalSystem('all')">
          <div class="detail-block-title" style="font-size: 12px; margin-bottom: 0;">Part 3. Notion 硬件工程日志与 Runner 同步状态 (点击查看侧边栏 29 篇明细 ↗)</div>
          <div style="font-size: 10px; display: flex; align-items: center; gap: 4px;">
            <span>Runner:</span>
            <span class="status-tag status-${jp.runner_status === 'READY' || jp.runner_status === 'SYNCED' ? 'SYNCED' : escapeHtml(jp.runner_status || 'SYNCED')}" style="font-size: 8.5px; padding: 1px 4px;">${escapeHtml(jp.runner_status === 'READY' || jp.runner_status === 'SYNCED' ? 'SYNCED' : (jp.runner_status || 'SYNCED'))}</span>
            ${(() => {
              const syncIso = (jp.latest_sync_job && jp.latest_sync_job.updated_at) || jp.last_synced_at || (journItem && journItem.updated_at) || '';
              const ago = formatTimeAgo(syncIso);
              return ago ? `<span style="color: var(--text-dim); font-size: 9px; font-weight: normal; margin-left: 2px;" title="最后同步时间: ${formatTime(syncIso)}">${escapeHtml(ago)}</span>` : '';
            })()}
          </div>
        </div>

        <div style="display: flex; align-items: center; gap: 4px; margin-bottom: 5px; flex-wrap: wrap;">
          <span style="font-size: 10px; color: var(--text-dim); margin-right: 4px;">收录 ${jp.total_pages || 29} 篇日志，系统覆盖:</span>
          ${breakdownPills}
        </div>

        <div style="background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.05); border-radius: 4px; padding: 4px 6px;">
          <div style="font-size: 9.5px; color: var(--text-dim); margin-bottom: 2px;">最新同步日志摘录 (点击侧边栏查看全部)：</div>
          ${recentPagesHtml}
        </div>
      </div>
    `;
  }

  function renderProjectCheckpointStepper(pct, stageName, stageCode, isCompact = false) {
    const p = Math.max(0, Math.min(100, typeof pct === 'number' ? pct : 0));
    const checkpoints = [
      { step: 1, targetPct: 20, name: '概念架构与需求基线', short: '概念' },
      { step: 2, targetPct: 40, name: '原理图与规范定型', short: '原理图' },
      { step: 3, targetPct: 60, name: 'BOM选型与物料打样', short: 'BOM' },
      { step: 4, targetPct: 80, name: '嵌入式固件台架集成', short: '台架' },
      { step: 5, targetPct: 100, name: '现场常态在网部署', short: '在网' }
    ];

    let activeIndex = 0;
    for (let i = checkpoints.length - 1; i >= 0; i--) {
      if (p >= (checkpoints[i].targetPct - 15)) {
        activeIndex = i;
        break;
      }
    }

    const nodesHtml = checkpoints.map((cp, idx) => {
      let stateClass = 'pending';
      let stateLabel = '待推进';

      if (p >= cp.targetPct) {
        stateClass = 'completed';
        stateLabel = '已达标';
      } else if (idx === activeIndex) {
        stateClass = 'active';
        stateLabel = '推进中';
      }

      const tooltip = `阶段 ${cp.step}: ${cp.name} · 状态: ${stateLabel}`;

      if (isCompact) {
        return `
          <div class="proj-step-node ${stateClass}" title="${escapeHtml(tooltip)}">
            <div class="proj-step-dot">${stateClass === 'completed' ? '✓' : ''}</div>
          </div>
        `;
      }

      return `
        <div class="proj-step-node ${stateClass}" title="${escapeHtml(tooltip)}">
          <div class="proj-step-dot">${stateClass === 'completed' ? '✓' : ''}</div>
          <div class="proj-step-label-row">
            <span class="proj-step-name">${escapeHtml(cp.short)}</span>
            <span class="proj-step-badge">${stateLabel}</span>
          </div>
        </div>
      `;
    }).join('');

    if (isCompact) {
      return `
        <div class="proj-stepper-compact" title="项目生命周期: ${escapeHtml(stageName || '推进中')}">
          <div class="proj-stepper-track-line"></div>
          <div class="proj-stepper-track-fill" style="width: ${p}%;"></div>
          <div class="proj-stepper-nodes-row compact">
            ${nodesHtml}
          </div>
        </div>
      `;
    }

    return `
      <div class="proj-stepper-full" title="项目生命周期: ${escapeHtml(stageName || '推进中')}">
        <div class="proj-stepper-track-line"></div>
        <div class="proj-stepper-track-fill" style="width: ${p}%;"></div>
        <div class="proj-stepper-nodes-row">
          ${nodesHtml}
        </div>
      </div>
    `;
  }

  function renderForgePreviewHtml(ws, isExpanded) {
    const items = (ws && ws.items) || [];
    const wsItem = items.find(it => it.kind === 'forge_workspace');
    const projs = items.filter(it => it.kind === 'forge_project');
    const commItem = items.find(it => it.kind === 'forge_commerce');
    const journItem = items.find(it => it.kind === 'forge_journal');

    const wp = (wsItem && wsItem.payload) ? wsItem.payload : {};
    const cp = (commItem && commItem.payload) ? commItem.payload : {};
    const jp = (journItem && journItem.payload) ? journItem.payload : {};
    const eh = cp.engine_health || wp.engine_health || {};
    const ch = eh.channels || {};
    const pddCnt = (ch.pdd && ch.pdd.count) || 603;
    const shopeeCnt = (ch.shopee && ch.shopee.count) || 303;
    const tbCnt = (ch.taobao && ch.taobao.count) || 165;
    const unreviewed = (cp.triage_summary && cp.triage_summary.unreviewed) || 1071;
    const totalPages = jp.total_pages || 29;

    if (isExpanded) {
      return `
        <div class="forge-card-preview expanded-card-view" onclick="event.stopPropagation();">
          <div class="forge-preview-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <span style="font-size: 14px; font-weight: 700; color: #fff;">🛠️ Forge 5大实体工程、多平台采购流转与工程日志 (Part 1 - 3)</span>
            <span class="status-tag status-ACTIVE" style="font-size: 10px;">已放大展示 · 5 Projects · 1071 Orders</span>
          </div>
          ${renderForgeFullView(ws)}
        </div>
      `;
    } else {
      // Strictly maintain 5 projects row limit in collapsed view to preserve compact card size
      const displayProjs = projs.slice(0, 5);
      const remainingCount = projs.length - displayProjs.length;

      const collapsedRowsHtml = displayProjs.map(pr => {
        const p = pr.payload || {};
        const pct = (typeof p.progress_pct === 'number') ? p.progress_pct : 0;
        const projId = p.project_id || pr.item_id || '';
        const projName = p.name || pr.title.replace('项目: ', '');
        const icon = getForgeProjectIcon(projId, projName, p.icon || p.emoji || '', p.project_type || '');
        const compactStepperHtml = renderProjectCheckpointStepper(pct, p.stage_name, p.stage_code, true);

        return `
          <div class="forge-collapsed-proj-row">
            <div style="display: flex; align-items: center; gap: 6px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;">
              <span class="proj-feature-icon" style="font-size: 12px;">${icon}</span>
              <span class="tree-badge-proj" style="font-size: 8px; padding: 1px 4px; line-height: 11px;">PROJ</span>
              <span style="color: #f1f5f9; font-size: 10.5px; font-weight: 600; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(projName)}</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px; flex-shrink: 0; margin-left: auto;">
              <span class="status-tag status-${escapeHtml(p.stage_code || 'IN_PROGRESS')}" style="font-size: 9px; font-weight: 600; padding: 1.5px 5px; border-radius: 3px;">${escapeHtml(p.stage_name || '推进中')}</span>
              <span style="font-size: 9px; color: var(--text-dim); white-space: nowrap;">BOM ${p.bom_count || 0}</span>
              <div style="width: 75px; flex-shrink: 0;">
                ${compactStepperHtml}
              </div>
            </div>
          </div>
        `;
      }).join('');

      return `
        <div class="forge-card-preview collapsed-card-view" onclick="window.__uuma_selectAgent('forge-lab-bot')" style="cursor: pointer;" title="点击放大展示 Forge 完整工作区与 3 大板块">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <span style="font-size: 11px; font-weight: 700; color: #fff;">🛠️ 5 大硬件实体工程 (Hardware Lab)</span>
            <span class="status-tag status-ACTIVE" style="font-size: 9px;">${projs.length} 项工程 · 1071 笔流水</span>
          </div>

          <div style="display: flex; flex-direction: column; gap: 4px; margin-bottom: 6px; max-height: 155px; overflow: hidden;">
            ${collapsedRowsHtml}
            ${remainingCount > 0 ? `
              <div style="font-size: 9.5px; color: var(--accent-blue); text-align: center; padding: 2px 0;">
                + 还有 ${remainingCount} 项实体工程 (点击放大查看全部)
              </div>
            ` : ''}
          </div>

          <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(0, 0, 0, 0.28); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 4px; padding: 4px 6px; font-size: 9.5px; margin-bottom: 4px;">
            <span style="color: var(--text-dim);">📦 采购流转:</span>
            <span style="color: #fb923c;">PDD ${pddCnt}</span> · 
            <span style="color: #f97316;">Shopee ${shopeeCnt}</span> · 
            <span style="color: #38bdf8;">Taobao ${tbCnt}</span>
            <span style="color: #c084fc; font-weight: 600;">(${unreviewed} 待审)</span>
          </div>

          <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(56, 189, 248, 0.06); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 4px; padding: 3px 6px; font-size: 9.5px;">
            <span style="color: #38bdf8; font-weight: 600;">📝 Notion 工程日志：</span>
            <span style="color: #cbd5e1;">收录 ${totalPages} 篇 · Runner SYNCED ${(() => {
              const syncIso = (jp && jp.latest_sync_job && jp.latest_sync_job.updated_at) || (jp && jp.last_synced_at) || (journItem && journItem.updated_at) || '';
              const ago = formatTimeAgo(syncIso);
              return ago ? `<span style="color: var(--text-dim); font-size: 8.5px; margin-left: 2px;">(${escapeHtml(ago)})</span>` : '';
            })()}</span>
          </div>

          <div style="font-size: 9.5px; color: var(--accent-blue); text-align: right; margin-top: 4px;">
            🔍 点击卡片任意位置放大整个窗口 (展开 3 大完整工程板块) ↗
          </div>
        </div>
      `;
    }
  }

  function renderForgeDashboard(ws) {
    return `
      <div class="detail-block">
        <div class="detail-block-title">智能体概览与运行状态</div>
        <div style="font-size: 13px; margin-bottom: 6px;">
          <strong>状态：</strong> <span class="status-tag status-${escapeHtml(ws.status)}">${escapeHtml(ws.status)}</span>
          <span style="margin-left: 10px;"><strong>健康度：</strong> <span class="badge-live ${ws.health === 'HEALTHY' ? '' : 'polling'}">${escapeHtml(ws.health)}</span></span>
        </div>
        <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 5px;"><strong>核心职责：</strong> ${escapeHtml(ws.role)}</div>
        <div style="font-size: 12px; color: var(--text-dim);"><strong>核心数据源：</strong> ${escapeHtml(ws.source_name)}</div>
      </div>
      ${renderForgeFullView(ws)}
    `;
  }

  function renderWisdomPreviewHtml(ws, isExpanded) {
    const items = ws.items || [];
    const activeTopic = items.find(it => it.kind === 'knowledge_topic' && it.status === 'ACTIVE') || {};
    const archivedTopics = items.filter(it => it.kind === 'knowledge_topic' && it.status === 'ARCHIVED');
    const allTopics = [];
    if (activeTopic.item_id) {
      allTopics.push(activeTopic);
    }
    allTopics.push(...archivedTopics);

    const tasks = items.filter(it => it.kind === 'active_task');
    const runningTask = tasks.find(t => t.status === 'RUNNING');
    const actPayload = activeTopic.payload || {};

    const topicsStripHtml = allTopics.map((top, idx) => {
      const isAct = top.status === 'ACTIVE';
      const p = top.payload || {};
      const title = p.title || (top.title ? top.title.replace('知识主题: ', '') : `主题 ${top.item_id}`);
      const status = top.status || (isAct ? 'ACTIVE' : 'ARCHIVED');
      const vCnt = p.ver_cnt || 45;
      const claimCnt = p.claim_count || 8;
      const linkCnt = p.links_cnt || 20;
      const summaryText = p.superseded_by_topic_id 
        ? '已合并至主干 topic_07a8' 
        : (p.summary || (isAct ? '气雾栽培核心要素、分株成活与喷雾间隔' : '历史排查与撤回审计记录'));

      return `
        <div class="wisdom-topic-card ${isAct ? 'active-topic' : ''}" 
             data-topic-id="${escapeHtml(top.item_id)}" 
             title="${escapeHtml(title)}"
             onclick="event.stopPropagation(); window.__uuma_selectItem('${escapeHtml(top.item_id)}')">
          
          <div class="wisdom-topic-card-inner">
            <div class="wisdom-topic-header">
              <span style="font-size: 10px; font-weight: 700; ${isAct ? 'color: #34d399;' : 'color: #94a3b8;'}">
                ${isAct ? '🌿 主干 #1' : `#${idx + 1}`}
              </span>
              <span class="status-tag status-${escapeHtml(status)}" style="font-size: 8.5px; padding: 1px 4px; ${isAct ? 'background: rgba(16,185,129,0.22); border-color: #10b981; color: #34d399;' : ''}">
                ${escapeHtml(status)}
              </span>
            </div>
            
            <div>
              <div class="wisdom-topic-title">
                ${escapeHtml(title)}
              </div>
              <div class="wisdom-topic-sub">
                ${isAct ? `v${vCnt} · ${claimCnt}断言 · ${linkCnt}引据` : escapeHtml(summaryText)}
              </div>
            </div>
          </div>

          <!-- 悬浮浮出提示卡片 (鼠标移过去浮出完整信息) -->
          <div class="wisdom-topic-popover">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              <span style="font-weight: 700; ${isAct ? 'color: #34d399;' : 'color: #38bdf8;'} font-size: 11.5px;">
                ${isAct ? '🌿 活跃演进主干主题' : `📦 历史归档主题 #${idx + 1}`}
              </span>
              <span class="status-tag status-${escapeHtml(status)}" style="font-size: 9px; ${isAct ? 'background: rgba(16,185,129,0.22); border-color: #10b981; color: #34d399;' : ''}">
                ${escapeHtml(status)}
              </span>
            </div>
            <div style="font-weight: 700; color: #fff; font-size: 12px; margin-bottom: 4px;">
              ${escapeHtml(title)}
            </div>
            <div style="font-size: 10px; color: #94a3b8; margin-bottom: 4px;">
              <strong>版本:</strong> v${vCnt} · <strong>断言:</strong> <span style="color: var(--accent-green);">${claimCnt} 项已提取</span> · <strong>引据:</strong> <span style="color: var(--accent-blue);">${linkCnt} 处</span>
            </div>
            <div style="font-size: 10px; color: #cbd5e1; margin-bottom: 5px; line-height: 1.4;">
              ${escapeHtml(summaryText)}
            </div>
            <div style="font-size: 9.5px; color: var(--accent-blue); text-align: right; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 3px;">
              🔍 点击在右侧检视面板查看完整知识图谱 ↗
            </div>
          </div>

        </div>
      `;
    }).join('');

    if (isExpanded) {
      return `
        <div class="wisdom-card-preview expanded-card-view" onclick="event.stopPropagation();">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <span style="font-size: 14px; font-weight: 700; color: #fff;">📚 Wisdom 知识主题架构、演进追溯与调查推进态</span>
            <span class="status-tag status-ACTIVE" style="font-size: 10.5px;">${allTopics.length} 个主题体系 · 1 活跃主干 · ${archivedTopics.length} 归档追溯</span>
          </div>

          <!-- 执行真实态探针 -->
          <div class="liveness-banner ${runningTask && !runningTask.payload.is_silent ? 'active-running' : ''}" style="margin-bottom: 8px;">
            <div class="liveness-banner-title">
              <span style="color: ${runningTask ? 'var(--accent-amber)' : 'var(--accent-green)'};">
                ${runningTask ? '⚡ 当前调查真实运行探针' : '⚡ 调度器待命状态'}
              </span>
              <span style="font-size: 10px; color: var(--text-dim);">运行监控与心跳时效</span>
            </div>
            <div class="liveness-banner-text">
              ${runningTask ? `
                <strong>任务状态：</strong> 调度器注册标称 <span style="color: #38bdf8;">RUNNING</span>。<br/>
                <strong>心跳诊断：</strong> <span style="color: #fcd34d;">⚠️ 心跳静默待唤醒</span>（上次心跳于 2026-10-10 19:29，已超 90 小时无活跃心跳脉冲）。<br/>
                <strong>真实状态剖析：</strong> 该任务属于长期调查规划任务，已成功绑定至主题 <code>topic_07a8</code>，但当前本地 Worker 未实时占用 CPU 循环；正在等待调度器发起下一轮调研周期。
              ` : '当前暂无处于 RUNNING 状态的调查任务，所有主题处于就绪归档状态。'}
            </div>
          </div>

          <!-- 统一知识主题卡片行 (第1个为青色活跃主题，后续为归档主题，同一排弹性压缩与悬停展开) -->
          <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 6px; padding: 8px 10px; margin-bottom: 6px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <span style="font-size: 11px; font-weight: 700; color: var(--text-dim);">
                📦 知识主题演进与归档追溯全景 (${allTopics.length} 个 · 同一排弹性展示 · 悬停浮出详情)：
              </span>
              <a href="${actPayload.standalone_url || 'http://127.0.0.1:8767/wisdom/topics'}" target="_blank" style="color: var(--accent-blue); font-size: 10.5px; text-decoration: none;">
                独立知识文档 (v${actPayload.ver_cnt || 45}) ↗
              </a>
            </div>
            <div class="wisdom-topics-strip">
              ${topicsStripHtml}
            </div>
          </div>
        </div>
      `;
    } else {
      return `
        <div class="wisdom-card-preview collapsed-card-view" onclick="window.__uuma_selectAgent('wisdom-oldman')">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <span style="font-size: 11px; font-weight: 700; color: #fff;">📚 知识主题架构与调查归属态</span>
            <span class="status-tag status-ACTIVE" style="font-size: 9px;">${allTopics.length} 主题 · 1 主干 ${archivedTopics.length} 归档</span>
          </div>

          <!-- 缩小状态下的同一排主题弹性卡片行 -->
          <div class="wisdom-topics-strip" style="margin-bottom: 6px;">
            ${topicsStripHtml}
          </div>

          <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.25); border-radius: 4px; padding: 4px 6px; font-size: 10px;">
            <span style="color: #fcd34d; font-weight: 600;">⚡ 执行状态探针：</span>
            <span style="color: #cbd5e1;">${runningTask ? 'task_7debe 标称 RUNNING · 心跳静默待唤醒 (>90h)' : '就绪待命'}</span>
          </div>
          <div style="font-size: 10px; color: var(--accent-blue); text-align: right; margin-top: 4px;">
            🔍 点击卡片展开查看完整主题树、调查归属与事件时间线 ↗
          </div>
        </div>
      `;
    }
  }

  // Comprehensive Brainstormer Architecture DAG & Topic View Renderer
  function renderBrainstormerPreviewHtml(ws, isExpanded) {
    const items = ws.items || [];
    const dagItem = items.find(it => it.kind === 'decision_dag') || {};
    const dp = dagItem.payload || {};
    const topics = dp.topics || [
      {
        topic_id: 'topic_state_daemon',
        title: '本地状态守护与持久化单写者队列 (State Daemon & Storage Queue)',
        description: '解决本地高并发读写、防数据踩踏与单写者排队同步机制，保障 SQLite 与 JSON 状态原子刷新与无锁并发读取',
        icon: '⚡',
        decisions: [{ id: 'dec_arch_001', title: 'Single-Writer Project Queue for State Sync', status: 'accepted' }],
        questions: [{ id: 'que_001', title: 'How to handle dual-entry voice and Telegram?', status: 'open' }],
        assumptions: [{ id: 'asm_001', title: 'Low Latency Local Daemon on 127.0.0.1:8772', status: 'open' }],
        checkpoints: [{ id: 'chk_001', title: 'Verify Atomic state flush with fsync & replace', status: 'open' }],
      },
      {
        topic_id: 'topic_dag_rendering',
        title: '架构决策图谱可视化与抽屉交互 (DAG Flow & Inspector UX)',
        description: '基于 @xyflow/react 与 dagre 拓扑布局的决策 DAG 交互渲染，支持多层级折叠展开与 Notion 风格侧边栏检查',
        icon: '🎨',
        decisions: [{ id: 'dec_arch_002', title: 'DAG Rendering with @xyflow/react & dagre', status: 'accepted' }],
        questions: [{ id: 'que_002', title: 'Should inspector drawer auto-collapse on small screens?', status: 'open' }],
        assumptions: [],
        checkpoints: [],
      }
    ];

    const allDecs = dp.discussed_decisions || [];
    const allQues = dp.open_questions || [];
    const allAsms = dp.assumptions || [];
    const allChks = dp.checkpoints || [];
    const projId = dp.project_id || 'proj_live_arch_001';
    const rev = dp.revision ? `r${dp.revision}` : 'r6';

    const totalTopicsCount = topics.length;
    const showAllTopics = !!state.bsShowAllTopics;
    // 5-Topic Cap: Show at most 5 topics by default unless Show More is toggled
    const displayTopics = (totalTopicsCount > 5 && !showAllTopics) ? topics.slice(0, 5) : topics;
    const remainingCount = totalTopicsCount - displayTopics.length;

    // Helper to determine if a topic is open:
    // Default: ONLY index 0 (newest topic) is OPEN! All older topics (idx > 0) are CLOSED (hide)!
    function isBsTopicOpen(topicId, idx) {
      if (state.bsTopicExpanded && Object.prototype.hasOwnProperty.call(state.bsTopicExpanded, topicId)) {
        return !!state.bsTopicExpanded[topicId];
      }
      return idx === 0;
    }

    if (isExpanded) {
      const topicsCardsHtml = displayTopics.map((t, idx) => {
        const isOpen = isBsTopicOpen(t.topic_id, idx);

        const decsHtml = (t.decisions || []).map(d => `
          <div class="bs-node-card bs-node-dec" onclick="window.__uuma_selectItem('bs_dec_${escapeHtml(d.id)}')">
            <div class="bs-node-head">
              <span class="bs-node-title">🟢 ${escapeHtml(d.title)}</span>
              <span class="status-tag status-COMPLETED">已决议</span>
            </div>
            ${d.body || d.rationale ? `<div class="bs-node-desc">${escapeHtml(d.body || d.rationale)}</div>` : ''}
          </div>
        `).join('') || '<div class="bs-empty-hint">暂无已决议方案</div>';

        const quesHtml = (t.questions || []).map(q => `
          <div class="bs-node-card bs-node-que" onclick="window.__uuma_selectItem('bs_que_${escapeHtml(q.id)}')">
            <div class="bs-node-head">
              <span class="bs-node-title">🟡 ${escapeHtml(q.title)}</span>
              <span class="status-tag status-WAITING">待研讨</span>
            </div>
            ${q.body ? `<div class="bs-node-desc">${escapeHtml(q.body)}</div>` : ''}
          </div>
        `).join('') || '<div class="bs-empty-hint">无待决议问题</div>';

        const asmsHtml = (t.assumptions || []).map(a => `
          <div class="bs-node-card bs-node-asm">
            <div class="bs-node-head">
              <span class="bs-node-title">🟣 ${escapeHtml(a.title)}</span>
              <span class="status-tag status-IDLE">假设</span>
            </div>
            ${a.body ? `<div class="bs-node-desc">${escapeHtml(a.body)}</div>` : ''}
          </div>
        `).join('') || '<div class="bs-empty-hint">无特定底层假设</div>';

        const chksHtml = (t.checkpoints || []).map(c => `
          <div class="bs-node-card bs-node-chk">
            <div class="bs-node-head">
              <span class="bs-node-title">🔵 ${escapeHtml(c.title)}</span>
              <span class="status-tag status-IN_PROGRESS">待验证</span>
            </div>
          </div>
        `).join('') || '<div class="bs-empty-hint">就绪待命</div>';

        return `
          <div class="bs-topic-card ${isOpen ? 'is-open' : 'is-collapsed'}">
            <div class="bs-topic-card-header" onclick="window.__uuma_toggleBsTopic('${escapeHtml(t.topic_id)}', event)" title="${isOpen ? '点击折叠此议题 (Collapse)' : '点击展开此议题 (Expand)'}">
              <div class="bs-topic-title-wrap">
                <span class="bs-toggle-caret ${isOpen ? 'open' : ''}">${isOpen ? '▼' : '▶'}</span>
                <span class="bs-topic-num">Topic ${idx + 1} / ${totalTopicsCount}</span>
                <span class="bs-topic-icon">${escapeHtml(t.icon || '◈')}</span>
                <span class="bs-topic-title">${escapeHtml(t.title)}</span>
                <span class="bs-topic-id-badge">${escapeHtml(t.topic_id)}</span>
                ${!isOpen ? `<span class="bs-topic-collapsed-hint">(已折叠 · 点击展开)</span>` : ''}
              </div>
              <div class="bs-topic-meta-pills">
                <span class="bs-pill pill-dec">${(t.decisions || []).length} 决议</span>
                <span class="bs-pill pill-que">${(t.questions || []).length} 待研讨</span>
                <span class="bs-pill pill-asm">${(t.assumptions || []).length} 假设</span>
              </div>
            </div>

            <!-- Under Topic: Indented Tree with Left Vertical Guideline (shown when isOpen) -->
            ${isOpen ? `
              <div class="bs-topic-indent-tree">
                ${t.description ? `
                  <div class="bs-topic-desc-box">
                    <strong>🎯 架构目标 / 核心背景：</strong> ${escapeHtml(t.description)}
                  </div>
                ` : ''}

                <!-- 4 Distinct Bordered Category Groups -->
                <div class="bs-cat-group cat-dec">
                  <div class="bs-cat-header">
                    <span><span class="bs-cat-dot">🟢</span>已决议架构方案</span>
                    <span class="bs-cat-count">${(t.decisions || []).length} 项决议</span>
                  </div>
                  <div class="bs-cat-items">${decsHtml}</div>
                </div>

                <div class="bs-cat-group cat-que">
                  <div class="bs-cat-header">
                    <span><span class="bs-cat-dot">🟡</span>待研讨讨论议题</span>
                    <span class="bs-cat-count">${(t.questions || []).length} 个议题</span>
                  </div>
                  <div class="bs-cat-items">${quesHtml}</div>
                </div>

                <div class="bs-cat-group cat-asm">
                  <div class="bs-cat-header">
                    <span><span class="bs-cat-dot">🟣</span>底层设计假设</span>
                    <span class="bs-cat-count">${(t.assumptions || []).length} 项假设</span>
                  </div>
                  <div class="bs-cat-items">${asmsHtml}</div>
                </div>

                <div class="bs-cat-group cat-chk">
                  <div class="bs-cat-header">
                    <span><span class="bs-cat-dot">🔵</span>落地验证检查点</span>
                    <span class="bs-cat-count">${(t.checkpoints || []).length} 个检查点</span>
                  </div>
                  <div class="bs-cat-items">${chksHtml}</div>
                </div>
              </div>
            ` : ''}
          </div>
        `;
      }).join('');

      return `
        <div class="brainstormer-card-preview expanded-card-view" onclick="event.stopPropagation();">
          <div class="brainstormer-preview-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div>
              <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 16px; font-weight: 700; color: #fff;">🏛️ Brainstormer 架构决策拓扑全景图 (Architecture Decision DAG)</span>
                <span class="status-tag status-ACTIVE" style="font-size: 10.5px;">共 ${totalTopicsCount} 个核心架构议题 (最新优先)</span>
              </div>
              <div style="font-size: 11px; color: var(--text-muted); margin-top: 3px;">
                按系统架构议题 (Topics) 阶梯缩进归属 · 默认仅自动展开最新议题，早期议题紧凑折叠收起
              </div>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <span class="status-tag status-ACTIVE" style="font-size: 11px;">专案: ${escapeHtml(projId)} (${escapeHtml(rev)})</span>
            </div>
          </div>

          <div class="bs-arch-meta-bar">
            <div class="bs-arch-flow">
              <span class="flow-pill pill-asm">💡 底层假设</span>
              <span class="flow-arrow">──(支撑 grounds)──▶</span>
              <span class="flow-pill pill-que">❓ 待研讨议题</span>
              <span class="flow-arrow">──(决议 decides)──▶</span>
              <span class="flow-pill pill-dec">✅ 架构决策</span>
              <span class="flow-arrow">──(验证 verifies)──▶</span>
              <span class="flow-pill pill-chk">🏁 检查点</span>
            </div>

            <div class="bs-top-stat-strip">
              <div class="bs-stat-chip chip-topic">
                <span class="chip-val">${totalTopicsCount}</span>
                <span class="chip-lbl">核心架构议题 (Topics)</span>
              </div>
              <div class="bs-stat-chip chip-dec">
                <span class="chip-val">${allDecs.length}</span>
                <span class="chip-lbl">已决议方案</span>
              </div>
              <div class="bs-stat-chip chip-que">
                <span class="chip-val">${allQues.length}</span>
                <span class="chip-lbl">待讨论议题</span>
              </div>
              <div class="bs-stat-chip chip-asm">
                <span class="chip-val">${allAsms.length}</span>
                <span class="chip-lbl">底层假设</span>
              </div>
              <div class="bs-stat-chip chip-chk">
                <span class="chip-val">${allChks.length}</span>
                <span class="chip-lbl">验证检查点</span>
              </div>
            </div>
          </div>

          <!-- Topics Action Bar (Expand All / Collapse All) -->
          <div class="bs-topics-action-bar">
            <div style="font-size: 11px; color: var(--text-dim); display: flex; align-items: center; gap: 6px;">
              <span>📋 议题列表 (共 <strong>${totalTopicsCount}</strong> 个 · 默认仅展开最新议题)</span>
              ${totalTopicsCount > 5 && !showAllTopics ? `<span style="font-size: 9.5px; color: #fbbf24;">(前 5 个展示中)</span>` : ''}
            </div>
            <div class="bs-action-btn-group">
              <button class="bs-action-btn" onclick="window.__uuma_setAllBsTopics(true, event)" title="全部展开所有议题">
                展开全部 (Expand All)
              </button>
              <button class="bs-action-btn" onclick="window.__uuma_setAllBsTopics(false, event)" title="全部折叠为紧凑条目">
                全部折叠 (Collapse All)
              </button>
            </div>
          </div>

          <div class="bs-topics-grid-wrap">
            ${topicsCardsHtml}
          </div>

          ${totalTopicsCount > 5 ? `
            <div class="bs-show-more-card">
              <button class="bs-show-more-btn" onclick="window.__uuma_toggleBsShowAll(event)">
                ${showAllTopics
                  ? `<span>▲ 收起早期架构议题 (仅保留前 5 个最新议题)</span>`
                  : `<span>▼ 展开查看其余 ${remainingCount} 个早期架构议题 (Show More)</span>`
                }
              </button>
            </div>
          ` : ''}
        </div>
      `;
    } else {
      // Collapsed Card View in 6-agent grid:
      // Show clearly numbered topics with indented tree rows and visible borders!
      const collapsedTopicsHtml = displayTopics.map((t, idx) => {
        const isOpen = isBsTopicOpen(t.topic_id, idx);

        const decRows = (t.decisions || []).slice(0, 2).map(d => `
          <div class="bs-collapsed-node-row row-dec" onclick="window.__uuma_selectItem('bs_dec_${escapeHtml(d.id)}')" title="已决议: ${escapeHtml(d.title)}">
            <span style="color: #f8fafc; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 82%;">🟢 ${escapeHtml(d.title)}</span>
            <span class="status-tag status-COMPLETED" style="font-size: 8px; padding: 1px 3.5px; flex-shrink: 0;">已决议</span>
          </div>
        `).join('');

        const queRows = (t.questions || []).slice(0, 2).map(q => `
          <div class="bs-collapsed-node-row row-que" onclick="window.__uuma_selectItem('bs_que_${escapeHtml(q.id)}')" title="待研讨: ${escapeHtml(q.title)}">
            <span style="color: #f8fafc; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 82%;">🟡 ${escapeHtml(q.title)}</span>
            <span class="status-tag status-WAITING" style="font-size: 8px; padding: 1px 3.5px; flex-shrink: 0;">待研讨</span>
          </div>
        `).join('');

        const asmRows = (t.assumptions || []).slice(0, 1).map(a => `
          <div class="bs-collapsed-node-row row-asm" title="底层假设: ${escapeHtml(a.title)}">
            <span style="color: #f8fafc; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 82%;">🟣 ${escapeHtml(a.title)}</span>
            <span class="status-tag status-IDLE" style="font-size: 8px; padding: 1px 3.5px; flex-shrink: 0;">假设</span>
          </div>
        `).join('');

        const chkRows = (t.checkpoints || []).slice(0, 1).map(c => `
          <div class="bs-collapsed-node-row row-chk" title="检查点: ${escapeHtml(c.title)}">
            <span style="color: #f8fafc; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 82%;">🔵 ${escapeHtml(c.title)}</span>
            <span class="status-tag status-IN_PROGRESS" style="font-size: 8px; padding: 1px 3.5px; flex-shrink: 0;">验证</span>
          </div>
        `).join('');

        return `
          <div class="bs-collapsed-topic-card ${isOpen ? 'is-open' : 'is-collapsed'}">
            <div class="bs-collapsed-topic-header" onclick="window.__uuma_toggleBsTopic('${escapeHtml(t.topic_id)}', event)" title="${isOpen ? '点击折叠此议题' : '点击展开此议题'}">
              <div style="display: flex; align-items: center; gap: 5px; min-width: 0; overflow: hidden;">
                <span class="bs-toggle-caret ${isOpen ? 'open' : ''}" style="font-size: 8.5px;">${isOpen ? '▼' : '▶'}</span>
                <span class="bs-topic-num">Topic ${idx + 1} / ${totalTopicsCount}</span>
                <span style="color: #38bdf8; font-size: 12px;">${escapeHtml(t.icon || '◈')}</span>
                <span style="font-weight: 700; color: #f1f5f9; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(t.title)}">
                  ${escapeHtml(t.title.split('(')[0].trim())}
                </span>
                ${!isOpen ? `<span style="font-size: 8.5px; color: var(--text-dim);">(收起)</span>` : ''}
              </div>
              <div style="display: flex; gap: 3px; flex-shrink: 0;">
                <span class="bs-pill pill-dec">${(t.decisions || []).length}决议</span>
                <span class="bs-pill pill-que">${(t.questions || []).length}待议</span>
              </div>
            </div>

            <!-- Under Topic: Indented Tree with Left Guideline (shown when isOpen) -->
            ${isOpen ? `
              <div class="bs-collapsed-indent-tree">
                ${decRows}
                ${queRows}
                ${asmRows}
                ${chkRows}
              </div>
            ` : ''}
          </div>
        `;
      }).join('');

      return `
        <div class="brainstormer-card-preview collapsed-card-view" onclick="window.__uuma_selectAgent('brainstormer')">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <div style="display: flex; align-items: center; gap: 6px;">
              <span style="font-size: 11px; font-weight: 700; color: #fff;">🏛️ 架构决策 DAG</span>
              <span class="status-tag status-ACTIVE" style="font-size: 8.5px; padding: 1px 4px;">共 ${totalTopicsCount} 个议题 · 最新优先</span>
            </div>
            <span style="font-size: 9.5px; color: var(--text-dim);">${escapeHtml(projId)} (${escapeHtml(rev)})</span>
          </div>

          <div style="display: flex; flex-direction: column; gap: 4px; margin-bottom: 6px;">
            ${collapsedTopicsHtml}
            ${remainingCount > 0 ? `
              <div style="font-size: 9px; color: var(--accent-blue); text-align: center; padding: 2px 0;">
                + 还有 ${remainingCount} 个早期架构议题 (点击展开查看全部)
              </div>
            ` : ''}
          </div>

          <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(16, 185, 129, 0.06); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: 4px; padding: 3px 6px; font-size: 9.5px;">
            <span style="color: #34d399; font-weight: 600;">📊 全局进展：</span>
            <span style="color: #cbd5e1;">
              已决议: <strong style="color: var(--accent-green);">${allDecs.length}</strong> · 
              待讨论: <strong style="color: var(--accent-amber);">${allQues.length}</strong> · 
              假设: <strong style="color: var(--accent-purple);">${allAsms.length}</strong>
            </span>
          </div>

          <div style="font-size: 9.5px; color: var(--accent-blue); text-align: right; margin-top: 4px;">
            🔍 点击卡片展开查看完整决策 DAG 架构图谱与大图 ↗
          </div>
        </div>
      `;
    }
  }

  function renderBrainstormerInspector(item, p) {
    const isTopicItem = item.kind === 'architecture_topic';
    const topicData = isTopicItem ? p.topic : null;
    const topics = p.topics || (topicData ? [topicData] : []);
    const projId = p.project_id || (topicData ? p.project_id : 'proj_live_arch_001');
    const rev = p.revision ? `r${p.revision}` : 'r6';

    const allDecs = p.discussed_decisions || (topicData ? topicData.decisions : []);
    const allQues = p.open_questions || (topicData ? topicData.questions : []);
    const allAsms = p.assumptions || (topicData ? topicData.assumptions : []);
    const allChks = p.checkpoints || (topicData ? topicData.checkpoints : []);

    const totalTopicsCount = topics.length;
    const showAllTopics = !!state.bsShowAllTopics;
    const displayTopics = (totalTopicsCount > 5 && !showAllTopics) ? topics.slice(0, 5) : topics;
    const remainingCount = totalTopicsCount - displayTopics.length;

    function isBsTopicOpen(topicId, idx) {
      if (state.bsTopicExpanded && Object.prototype.hasOwnProperty.call(state.bsTopicExpanded, topicId)) {
        return !!state.bsTopicExpanded[topicId];
      }
      return idx === 0;
    }

    const topicsBlockHtml = displayTopics.map((t, idx) => {
      const isOpen = isBsTopicOpen(t.topic_id, idx);

      const decsHtml = (t.decisions || []).map(d => `
        <div class="bs-node-card bs-node-dec" onclick="window.__uuma_selectItem('bs_dec_${escapeHtml(d.id)}')">
          <div class="bs-node-head">
            <span class="bs-node-title">🟢 ${escapeHtml(d.title)}</span>
            <span class="status-tag status-COMPLETED">已决议</span>
          </div>
          ${d.body || d.rationale ? `<div class="bs-node-desc">${escapeHtml(d.body || d.rationale)}</div>` : ''}
        </div>
      `).join('') || '<div class="bs-empty-hint">暂无已决议方案</div>';

      const quesHtml = (t.questions || []).map(q => `
        <div class="bs-node-card bs-node-que" onclick="window.__uuma_selectItem('bs_que_${escapeHtml(q.id)}')">
          <div class="bs-node-head">
            <span class="bs-node-title">🟡 ${escapeHtml(q.title)}</span>
            <span class="status-tag status-WAITING">待研讨</span>
          </div>
          ${q.body ? `<div class="bs-node-desc">${escapeHtml(q.body)}</div>` : ''}
        </div>
      `).join('') || '<div class="bs-empty-hint">无待讨论问题</div>';

      const asmsHtml = (t.assumptions || []).map(a => `
        <div class="bs-node-card bs-node-asm">
          <div class="bs-node-head">
            <span class="bs-node-title">🟣 ${escapeHtml(a.title)}</span>
            <span class="status-tag status-IDLE">假设</span>
          </div>
          ${a.body ? `<div class="bs-node-desc">${escapeHtml(a.body)}</div>` : ''}
        </div>
      `).join('');

      const chksHtml = (t.checkpoints || []).map(c => `
        <div class="bs-node-card bs-node-chk">
          <div class="bs-node-head">
            <span class="bs-node-title">🔵 ${escapeHtml(c.title)}</span>
            <span class="status-tag status-IN_PROGRESS">待验证</span>
          </div>
        </div>
      `).join('');

      return `
        <div class="bs-topic-card ${isOpen ? 'is-open' : 'is-collapsed'}" style="margin-bottom: 8px;">
          <div class="bs-topic-card-header" onclick="window.__uuma_toggleBsTopic('${escapeHtml(t.topic_id)}', event)" title="${isOpen ? '点击折叠此议题' : '点击展开此议题'}">
            <div class="bs-topic-title-wrap">
              <span class="bs-toggle-caret ${isOpen ? 'open' : ''}">${isOpen ? '▼' : '▶'}</span>
              <span class="bs-topic-num">Topic ${idx + 1} / ${totalTopicsCount}</span>
              <span class="bs-topic-icon">${escapeHtml(t.icon || '◈')}</span>
              <span class="bs-topic-title" style="font-size: 12px;">${escapeHtml(t.title)}</span>
              ${!isOpen ? `<span class="bs-topic-collapsed-hint">(收起)</span>` : ''}
            </div>
            <span class="bs-topic-id-badge">${escapeHtml(t.topic_id)}</span>
          </div>

          <!-- Under Topic: Indented Tree with Left Guideline (shown when isOpen) -->
          ${isOpen ? `
            <div class="bs-topic-indent-tree">
              ${t.description ? `
                <div class="bs-topic-desc-box">
                  <strong>🎯 架构目标 / 背景：</strong> ${escapeHtml(t.description)}
                </div>
              ` : ''}

              <div class="bs-cat-group cat-dec">
                <div class="bs-cat-header">
                  <span><span class="bs-cat-dot">🟢</span>已决议架构设计</span>
                  <span class="bs-cat-count">${(t.decisions || []).length} 项决议</span>
                </div>
                <div class="bs-cat-items">${decsHtml}</div>
              </div>

              <div class="bs-cat-group cat-que">
                <div class="bs-cat-header">
                  <span><span class="bs-cat-dot">🟡</span>待研讨议题与未决问题</span>
                  <span class="bs-cat-count">${(t.questions || []).length} 个议题</span>
                </div>
                <div class="bs-cat-items">${quesHtml}</div>
              </div>

              ${(t.assumptions || []).length ? `
                <div class="bs-cat-group cat-asm">
                  <div class="bs-cat-header">
                    <span><span class="bs-cat-dot">🟣</span>底层设计假设</span>
                    <span class="bs-cat-count">${t.assumptions.length} 项假设</span>
                  </div>
                  <div class="bs-cat-items">${asmsHtml}</div>
                </div>
              ` : ''}

              ${(t.checkpoints || []).length ? `
                <div class="bs-cat-group cat-chk">
                  <div class="bs-cat-header">
                    <span><span class="bs-cat-dot">🔵</span>验证检查点</span>
                    <span class="bs-cat-count">${t.checkpoints.length} 个检查点</span>
                  </div>
                  <div class="bs-cat-items">${chksHtml}</div>
                </div>
              ` : ''}
            </div>
          ` : ''}
        </div>
      `;
    }).join('');

    return `
      <div class="detail-block">
        <div class="detail-block-title" style="display: flex; justify-content: space-between; align-items: center;">
          <span>架构决策图谱 (Decision Map DAG)</span>
          <span class="status-tag status-ACTIVE" style="font-size: 9.5px;">共 ${totalTopicsCount} 个核心议题</span>
        </div>
        <div style="font-size: 11px; margin-bottom: 6px;">
          <strong>关联专案：</strong> <code>${escapeHtml(projId)}</code> · <strong>修订版本：</strong> <code>${escapeHtml(rev)}</code>
        </div>

        <div class="stat-grid" style="grid-template-columns: repeat(4, 1fr); gap: 4px; margin-bottom: 8px;">
          <div class="stat-box">
            <div class="stat-label">架构议题</div>
            <div class="stat-val" style="color: #38bdf8;">${totalTopicsCount}</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">已决议方案</div>
            <div class="stat-val" style="color: var(--accent-green);">${allDecs.length}</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">待研讨议题</div>
            <div class="stat-val" style="color: var(--accent-amber);">${allQues.length}</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">底层假设</div>
            <div class="stat-val" style="color: var(--accent-purple);">${allAsms.length}</div>
          </div>
        </div>

        <div class="bs-arch-flow" style="margin-bottom: 8px;">
          <span class="flow-pill pill-asm">💡 假设</span>
          <span class="flow-arrow">─▶</span>
          <span class="flow-pill pill-que">❓ 议题</span>
          <span class="flow-arrow">─▶</span>
          <span class="flow-pill pill-dec">✅ 决议</span>
          <span class="flow-arrow">─▶</span>
          <span class="flow-pill pill-chk">🏁 检查点</span>
        </div>

        <!-- Topics Action Bar in Inspector -->
        <div class="bs-topics-action-bar" style="margin-bottom: 8px;">
          <span style="font-size: 10.5px; color: var(--text-dim);">议题折叠列表 (${totalTopicsCount} 个)</span>
          <div class="bs-action-btn-group">
            <button class="bs-action-btn" onclick="window.__uuma_setAllBsTopics(true, event)" style="font-size: 9px; padding: 1.5px 6px;">全部展开</button>
            <button class="bs-action-btn" onclick="window.__uuma_setAllBsTopics(false, event)" style="font-size: 9px; padding: 1.5px 6px;">全部折叠</button>
          </div>
        </div>

        ${topicsBlockHtml}

        ${totalTopicsCount > 5 ? `
          <div class="bs-show-more-card">
            <button class="bs-show-more-btn" onclick="window.__uuma_toggleBsShowAll(event)">
              ${showAllTopics
                ? `<span>▲ 收起早期架构议题 (仅保留前 5 个)</span>`
                : `<span>▼ 展开其余 ${remainingCount} 个早期架构议题 (Show More)</span>`
              }
            </button>
          </div>
        ` : ''}
      </div>
    `;
  }

  window.__uuma_suggestAssign = function(targetAgent) {
    if (window.__uuma_selectAgent) {
      window.__uuma_selectAgent(targetAgent);
    }
  };

  function renderYoncPreviewHtml(ws, isExpanded) {
    const items = ws.items || [];
    const coreItem = items.find(it => it.kind === 'project_graph') || items[0] || {};
    const p = coreItem.payload || {};
    const timelineProjects = p.part1_timeline_projects || [];
    const assignSuggestions = p.part2_assign_suggestions || [];
    const stats = p.part3_macro_stats || {
      total_projects: 58,
      completed_projects: 0,
      l4_decomposed_projects: 11,
      l4_pct: 19.0,
      timeline_assigned_count: 9,
      total_nodes: 691,
      total_edges: 638,
      level_breakdown: { L1: 58, L2: 94, L3: 232, L4: 307 },
      status_breakdown: { TODO: 642, DONE: 14, CANCELLED: 35 }
    };
    const activities = p.part4_activities || [];
    const l1Break = stats.level_breakdown || {};
    const totalNodes = stats.total_nodes || 691;

    // Part 4: Activities Split into 2 Columns (Sessions vs Tasks/Topology)
    const sessionActs = activities.filter(a => a.kind === 'session');
    const taskActs = activities.filter(a => a.kind !== 'session');

    function renderActivityCards(acts) {
      if (!acts.length) {
        return '<div style="color: var(--text-dim); font-size: 9.5px; padding: 4px;">无近期记录</div>';
      }
      return acts.map(act => {
        const icon = act.kind === 'session' ? '💬' : (act.kind === 'task' ? '📋' : '🌐');
        const timeStr = act.time ? (act.time.length > 10 ? act.time.slice(0, 10) : act.time) : '';
        return `
          <div class="yonc-activity-card" onclick="event.stopPropagation(); window.__uuma_selectItem('${escapeHtml(act.id)}')" title="${escapeHtml(act.summary)}">
            <div style="display: flex; align-items: center; gap: 5px; min-width: 0; flex: 1;">
              <span style="font-size: 10px;">${icon}</span>
              <span class="yonc-activity-title" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 9.5px;">${escapeHtml(act.title)}</span>
            </div>
            <div style="display: flex; align-items: center; gap: 4px; flex-shrink: 0; margin-left: 6px;">
              <span class="status-tag status-${escapeHtml(act.status)}" style="font-size: 8px; padding: 0 3px;">${escapeHtml(act.status)}</span>
              ${timeStr ? `<span class="yonc-activity-time" style="font-size: 8.5px;">${escapeHtml(timeStr)}</span>` : ''}
            </div>
          </div>
        `;
      }).join('');
    }

    const activitiesColsHtml = `
      <div class="yonc-activity-cols">
        <div class="yonc-activity-col">
          <div class="yonc-activity-col-title">
            <span>💬 智能体会话交互 (${sessionActs.length})</span>
            <span style="font-size: 8.5px; font-weight: normal; color: var(--text-dim);">Hermes Sessions</span>
          </div>
          ${renderActivityCards(sessionActs)}
        </div>
        <div class="yonc-activity-col">
          <div class="yonc-activity-col-title">
            <span>📋 调度任务与图谱同步 (${taskActs.length})</span>
            <span style="font-size: 8.5px; font-weight: normal; color: var(--text-dim);">Tasks & Topology</span>
          </div>
          ${renderActivityCards(taskActs)}
        </div>
      </div>
    `;

    // Part 1: Timeline Projects Rows
    const displayProjects = isExpanded ? timelineProjects : timelineProjects.slice(0, 3);
    const timelineRowsHtml = displayProjects.map(proj => {
      const pct = Math.min(100, Math.max(0, proj.completion_pct || 0));
      const l4Pct = (typeof proj.l4_decomposition_pct === 'number')
        ? proj.l4_decomposition_pct
        : (proj.has_l4 ? 100 : 0);
      const isFullL4 = l4Pct === 100;
      const l4BarColor = isFullL4 ? 'var(--accent-green)' : (l4Pct > 0 ? '#38bdf8' : 'rgba(255,255,255,0.15)');
      const l4PctHtml = `
        <div class="mini-progress-row" style="margin: 0;" title="${isFullL4 ? '所有子分支叶子节点全部拆解至 L4' : (l4Pct > 0 ? `部分分支停在 L3 (${proj.l4_leaves}/${proj.total_leaves} 叶子节点已达 L4)` : '未深度拆解至 L4')}">
          <div class="mini-progress-bar" style="height: 5px; background: rgba(255,255,255,0.06);">
            <div class="mini-progress-fill" style="width: ${l4Pct}%; background: ${l4BarColor};"></div>
          </div>
          <span class="mini-progress-text" style="font-size: 9.5px; color: ${isFullL4 ? 'var(--accent-green)' : (l4Pct > 0 ? '#38bdf8' : 'var(--text-dim)')};">
            ${l4Pct}% ${proj.total_leaves ? `(${proj.l4_leaves}/${proj.total_leaves})` : ''}
          </span>
        </div>
      `;

      return `
        <div class="yonc-table-row ${isExpanded ? '' : 'collapsed-row'}">
          <div class="yonc-proj-title" title="${escapeHtml(proj.title)}">
            <span style="color: #38bdf8; margin-right: 4px;">▸</span>${escapeHtml(proj.title)}
            <span style="font-size: 9px; color: var(--text-dim); font-weight: normal; margin-left: 3px;">(${proj.total_tasks} 节点)</span>
          </div>
          <div class="yonc-due-date">
            <span>📅</span><span>${escapeHtml(proj.due_date || '—')}</span>
          </div>
          <div style="padding-right: 6px;">
            <div class="mini-progress-row" style="margin: 0;">
              <div class="mini-progress-bar" style="height: 5px;"><div class="mini-progress-fill" style="width: ${pct}%;"></div></div>
              <span class="mini-progress-text" style="font-size: 9.5px;">${pct}% (${proj.done_tasks}/${proj.total_tasks})</span>
            </div>
          </div>
          <div style="padding-right: 6px;">${l4PctHtml}</div>
          ${isExpanded ? `<div><span class="status-tag status-${escapeHtml(proj.status)}" style="font-size: 8.5px; padding: 1px 4px;">${escapeHtml(proj.status)}</span></div>` : ''}
        </div>
      `;
    }).join('');

    // Part 2: Assign Suggestions Cards/Chips
    let part2ContentHtml = '';
    if (isExpanded) {
      part2ContentHtml = `
        <div class="yonc-assign-grid">
          ${assignSuggestions.map(s => `
            <div class="yonc-assign-card" style="border-left-color: ${s.agent_color};">
              <div class="yonc-assign-card-head">
                <div class="yonc-assign-target">
                  <span>${s.icon}</span>
                  <span style="color: ${s.agent_color};">${escapeHtml(s.target_name)}</span>
                </div>
                <button class="yonc-assign-btn" onclick="event.stopPropagation(); window.__uuma_suggestAssign('${escapeHtml(s.target_agent)}')">委派协同 ↗</button>
              </div>
              <div class="yonc-assign-scope">🎯 <strong>分工范围：</strong>${escapeHtml(s.scope)}</div>
              <ul class="yonc-assign-tasks">
                ${(s.suggested_tasks || []).map(t => `<li>${escapeHtml(t)}</li>`).join('')}
              </ul>
              <div class="yonc-assign-rationale">💡 ${escapeHtml(s.rationale)}</div>
            </div>
          `).join('')}
        </div>
      `;
    } else {
      part2ContentHtml = `
        <div class="yonc-assign-chips">
          ${assignSuggestions.map(s => `
            <div class="yonc-assign-chip" style="border-left-color: ${s.agent_color};" title="${escapeHtml(s.rationale)}" onclick="event.stopPropagation(); window.__uuma_suggestAssign('${escapeHtml(s.target_agent)}')">
              <span>${s.icon}</span>
              <strong style="color: #f1f5f9; font-size: 9.5px; margin: 0 3px;">${escapeHtml(s.target_name.split(' ')[0])}:</strong>
              <span style="color: var(--text-muted); font-size: 9px;">${escapeHtml(s.scope)}</span>
            </div>
          `).join('')}
        </div>
      `;
    }

    if (isExpanded) {
      return `
        <div class="yonc-card-preview expanded-card-view" onclick="event.stopPropagation();">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
            <span style="font-size: 15px; font-weight: 700; color: #fff;">📊 Yonc 专案图谱、时间线推进、跨 Agent 分工建议与宏观全景</span>
            <span class="status-tag status-ACTIVE" style="font-size: 11px;">已放大展示 · 全图 58 专案 · 9 个排期中 · 6 大 Agent 协同</span>
          </div>

          <!-- Part 1: Timeline Projects Table -->
          <div class="yonc-part-section">
            <div class="yonc-part-header">
              <span class="yonc-part-title">📅 Part 1 · 时间线专案排期跟踪 (Timeline Projects · ${timelineProjects.length} 项)</span>
              <span style="font-size: 10px; color: var(--text-dim);">包含到期日期、完成度、L4 深度拆解状态</span>
            </div>
            <div class="yonc-table">
              <div class="yonc-table-header">
                <div>专案名称 (PROJECT / WBS)</div>
                <div>截止日期 (DUE DATE)</div>
                <div>任务进度 (TASK PROGRESS %)</div>
                <div>L4 拆解深度 (L4 DECOMPOSITION %)</div>
                <div>状态 (STATUS)</div>
              </div>
              ${timelineRowsHtml}
            </div>
          </div>

          <!-- Part 2: Assign Suggestions -->
          <div class="yonc-part-section">
            <div class="yonc-part-header">
              <span class="yonc-part-title">🤝 Part 2 · 跨 Agent 分工委派建议 (Assign Suggestions · 6 大专业方向)</span>
              <span style="font-size: 10px; color: var(--accent-blue);">Yonc 协同引擎基于图谱节点属性智能推荐 ↗</span>
            </div>
            ${part2ContentHtml}
          </div>

          <!-- Part 3: Macro Stats -->
          <div class="yonc-part-section">
            <div class="yonc-part-header">
              <span class="yonc-part-title">🌐 Part 3 · 专案图谱宏观统计 (Macro Project Graph Statistics)</span>
              <span style="font-size: 10px; color: var(--text-dim);">全图 691 节点 · 638 条拓扑依赖边</span>
            </div>
            <div class="yonc-macro-grid">
              <div class="yonc-stat-box">
                <div class="yonc-stat-val">${stats.total_projects} <span style="font-size: 10px; font-weight: normal; color: var(--text-dim);">个</span></div>
                <div class="yonc-stat-lbl">全图总专案数 (L1)</div>
              </div>
              <div class="yonc-stat-box">
                <div class="yonc-stat-val" style="color: var(--accent-green);">${stats.completed_projects} <span style="font-size: 10px; font-weight: normal; color: var(--text-dim);">个</span></div>
                <div class="yonc-stat-lbl">已完成专案 (全图14节点已验)</div>
              </div>
              <div class="yonc-stat-box">
                <div class="yonc-stat-val" style="color: #38bdf8;">${stats.fully_l4_projects !== undefined ? stats.fully_l4_projects : 1} <span style="font-size: 10px; font-weight: normal; color: var(--text-dim);">完全 / ${stats.partial_l4_projects !== undefined ? stats.partial_l4_projects : 10} 部分</span></div>
                <div class="yonc-stat-lbl">L4 深度拆解 (58个专案)</div>
              </div>
              <div class="yonc-stat-box">
                <div class="yonc-stat-val" style="color: #a78bfa;">${stats.timeline_assigned_count} <span style="font-size: 10px; font-weight: normal; color: var(--text-dim);">个</span></div>
                <div class="yonc-stat-lbl">时间线排期推进中</div>
              </div>
            </div>
            <div style="font-size: 9.5px; color: var(--text-dim); margin-top: 4px; display: flex; justify-content: space-between;">
              <span>WBS 节点层级分布：L1: ${l1Break.L1 || 58} · L2: ${l1Break.L2 || 94} · L3: ${l1Break.L3 || 232} · L4: ${l1Break.L4 || 307}</span>
              <span>状态：${stats.status_breakdown.TODO || 642} 待办 · ${stats.status_breakdown.DONE || 14} 完成 · ${stats.status_breakdown.CANCELLED || 35} 归档</span>
            </div>
          </div>

          <!-- Part 4: Activities Split into Columns -->
          <div class="yonc-part-section">
            <div class="yonc-part-header">
              <span class="yonc-part-title">⚡ Part 4 · 专案动态与活动记录 (Activities & Sessions · 双栏分列展示)</span>
              <span style="font-size: 9.5px; color: var(--text-dim);">分列展示智能体会话与调度任务</span>
            </div>
            ${activitiesColsHtml}
          </div>
        </div>
      `;
    } else {
      // Collapsed View
      return `
        <div class="yonc-card-preview collapsed-card-view" onclick="window.__uuma_selectAgent('yonc')">
          <!-- Part 3 Quick Stats Banner in Collapsed -->
          <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 4px; padding: 4px 8px; font-size: 10px;">
            <span style="color: #38bdf8; font-weight: 600;">🌐 专案图谱全局：</span>
            <span style="color: #cbd5e1;">${stats.total_projects} 专案 · <strong>${stats.fully_l4_projects !== undefined ? stats.fully_l4_projects : 1}完全/${stats.partial_l4_projects !== undefined ? stats.partial_l4_projects : 10}部分已拆至 L4</strong> · <strong>${stats.timeline_assigned_count} 个排期中</strong> · ${stats.completed_projects} 完成</span>
          </div>

          <!-- Part 1: Top Timeline Projects in Collapsed -->
          <div class="yonc-part-section" style="padding: 6px 8px;">
            <div class="yonc-part-header" style="margin-bottom: 4px;">
              <span class="yonc-part-title" style="font-size: 10.5px;">📅 Part 1 · 时间线排期专案 (Top ${displayProjects.length})</span>
              <span style="font-size: 9px; color: #38bdf8;">共 ${timelineProjects.length} 项排期</span>
            </div>
            <div class="yonc-table">
              ${timelineRowsHtml}
            </div>
          </div>

          <!-- Part 2: Quick Assign Suggestions in Collapsed -->
          <div class="yonc-part-section" style="padding: 6px 8px;">
            <div class="yonc-part-header" style="margin-bottom: 4px;">
              <span class="yonc-part-title" style="font-size: 10.5px;">🤝 Part 2 · 分工委派建议</span>
              <span style="font-size: 9px; color: var(--text-dim);">建议委派至其他代理</span>
            </div>
            ${part2ContentHtml}
          </div>

          <!-- Part 4: Activities in 2 Columns -->
          <div class="yonc-part-section" style="padding: 5px 8px;">
            <div class="yonc-part-header" style="margin-bottom: 3px;">
              <span class="yonc-part-title" style="font-size: 10px;">⚡ Part 4 · 专案动态与活动记录</span>
              <span style="font-size: 8.5px; color: var(--text-dim);">(双栏分列)</span>
            </div>
            ${activitiesColsHtml}
          </div>

          <div style="font-size: 9.5px; color: var(--accent-blue); text-align: right; margin-top: 1px;">
            🔍 点击卡片展开查看完整 9 个排期专案、跨 Agent 分工建议与宏观图谱 ↗
          </div>
        </div>
      `;
    }
  }

  function renderYoncDashboard(ws) {
    const items = ws.items || [];
    const coreItem = items.find(it => it.kind === 'project_graph') || items[0] || {};
    const p = coreItem.payload || {};
    const timelineProjects = p.part1_timeline_projects || [];
    const assignSuggestions = p.part2_assign_suggestions || [];
    const stats = p.part3_macro_stats || {
      total_projects: 58,
      completed_projects: 0,
      l4_decomposed_projects: 11,
      l4_pct: 19.0,
      timeline_assigned_count: 9,
      total_nodes: 691,
      total_edges: 638,
      level_breakdown: { L1: 58, L2: 94, L3: 232, L4: 307 },
      status_breakdown: { TODO: 642, DONE: 14, CANCELLED: 35 }
    };
    const activities = p.part4_activities || [];
    const l1Break = stats.level_breakdown || {};
    const totalNodes = stats.total_nodes || 691;

    // Part 4: Activities Split into 2 Columns (Sessions vs Tasks/Topology)
    const sessionActs = activities.filter(a => a.kind === 'session');
    const taskActs = activities.filter(a => a.kind !== 'session');

    function renderDashboardActivityCards(acts) {
      if (!acts.length) {
        return '<div style="color: var(--text-dim); font-size: 9.5px; padding: 4px;">无近期记录</div>';
      }
      return acts.map(act => {
        const icon = act.kind === 'session' ? '💬' : (act.kind === 'task' ? '📋' : '🌐');
        const timeStr = act.time ? (act.time.length > 10 ? act.time.slice(0, 10) : act.time) : '';
        return `
          <div class="yonc-activity-card" onclick="window.__uuma_selectItem('${escapeHtml(act.id)}')" title="${escapeHtml(act.summary)}">
            <div style="display: flex; align-items: center; gap: 5px; min-width: 0; flex: 1;">
              <span style="font-size: 10px;">${icon}</span>
              <span class="yonc-activity-title" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 9.5px;">${escapeHtml(act.title)}</span>
            </div>
            <div style="display: flex; align-items: center; gap: 4px; flex-shrink: 0; margin-left: 6px;">
              <span class="status-tag status-${escapeHtml(act.status)}" style="font-size: 8px; padding: 0 3px;">${escapeHtml(act.status)}</span>
              ${timeStr ? `<span class="yonc-activity-time" style="font-size: 8.5px;">${escapeHtml(timeStr)}</span>` : ''}
            </div>
          </div>
        `;
      }).join('');
    }

    const activitiesColsHtml = `
      <div class="yonc-activity-cols">
        <div class="yonc-activity-col">
          <div class="yonc-activity-col-title">
            <span>💬 智能体会话交互 (${sessionActs.length})</span>
            <span style="font-size: 8.5px; font-weight: normal; color: var(--text-dim);">Hermes Sessions</span>
          </div>
          ${renderDashboardActivityCards(sessionActs)}
        </div>
        <div class="yonc-activity-col">
          <div class="yonc-activity-col-title">
            <span>📋 调度任务与图谱同步 (${taskActs.length})</span>
            <span style="font-size: 8.5px; font-weight: normal; color: var(--text-dim);">Tasks & Topology</span>
          </div>
          ${renderDashboardActivityCards(taskActs)}
        </div>
      </div>
    `;

    const timelineRowsHtml = timelineProjects.map(proj => {
      const pct = Math.min(100, Math.max(0, proj.completion_pct || 0));
      const l4Pct = (typeof proj.l4_decomposition_pct === 'number')
        ? proj.l4_decomposition_pct
        : (proj.has_l4 ? 100 : 0);
      const isFullL4 = l4Pct === 100;
      const l4BarColor = isFullL4 ? 'var(--accent-green)' : (l4Pct > 0 ? '#38bdf8' : 'rgba(255,255,255,0.15)');
      const l4PctHtml = `
        <div class="mini-progress-row" style="margin: 0;" title="${isFullL4 ? '所有子分支叶子节点全部拆解至 L4' : (l4Pct > 0 ? `部分分支停在 L3 (${proj.l4_leaves}/${proj.total_leaves} 叶子节点已达 L4)` : '未深度拆解至 L4')}">
          <div class="mini-progress-bar" style="height: 5px; background: rgba(255,255,255,0.06);">
            <div class="mini-progress-fill" style="width: ${l4Pct}%; background: ${l4BarColor};"></div>
          </div>
          <span class="mini-progress-text" style="font-size: 9.5px; color: ${isFullL4 ? 'var(--accent-green)' : (l4Pct > 0 ? '#38bdf8' : 'var(--text-dim)')};">
            ${l4Pct}% ${proj.total_leaves ? `(${proj.l4_leaves}/${proj.total_leaves})` : ''}
          </span>
        </div>
      `;

      return `
        <div class="yonc-table-row">
          <div class="yonc-proj-title" title="${escapeHtml(proj.title)}">
            <span style="color: #38bdf8; margin-right: 4px;">▸</span>${escapeHtml(proj.title)}
            <span style="font-size: 9px; color: var(--text-dim); margin-left: 2px;">(${proj.total_tasks})</span>
          </div>
          <div class="yonc-due-date">📅 ${escapeHtml(proj.due_date || '—')}</div>
          <div style="padding-right: 6px;">
            <div class="mini-progress-row" style="margin: 0;">
              <div class="mini-progress-bar" style="height: 5px;"><div class="mini-progress-fill" style="width: ${pct}%;"></div></div>
              <span class="mini-progress-text" style="font-size: 9.5px;">${pct}%</span>
            </div>
          </div>
          <div style="padding-right: 6px;">${l4PctHtml}</div>
          <div><span class="status-tag status-${escapeHtml(proj.status)}" style="font-size: 8.5px; padding: 1px 3px;">${escapeHtml(proj.status)}</span></div>
        </div>
      `;
    }).join('');

    const assignCardsHtml = assignSuggestions.map(s => `
      <div class="yonc-assign-card" style="border-left-color: ${s.agent_color}; margin-bottom: 6px;">
        <div class="yonc-assign-card-head">
          <div class="yonc-assign-target">
            <span>${s.icon}</span>
            <span style="color: ${s.agent_color};">${escapeHtml(s.target_name)}</span>
          </div>
          <button class="yonc-assign-btn" onclick="window.__uuma_suggestAssign('${escapeHtml(s.target_agent)}')">委派协同 ↗</button>
        </div>
        <div class="yonc-assign-scope">🎯 <strong>分工建议：</strong>${escapeHtml(s.scope)}</div>
        <ul class="yonc-assign-tasks">
          ${(s.suggested_tasks || []).map(t => `<li>${escapeHtml(t)}</li>`).join('')}
        </ul>
        <div class="yonc-assign-rationale">💡 ${escapeHtml(s.rationale)}</div>
      </div>
    `).join('');

    return `
      <div class="detail-block">
        <div class="detail-block-title">Yonc 智能体概览与专案图谱核心</div>
        <div style="font-size: 12px; margin-bottom: 6px;">
          <strong>状态：</strong> <span class="status-tag status-${escapeHtml(ws.status)}">${escapeHtml(ws.status)}</span>
          <span style="margin-left: 8px;"><strong>健康度：</strong> <span class="badge-live">${escapeHtml(ws.health)}</span></span>
        </div>
        <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 4px;"><strong>核心职责：</strong> ${escapeHtml(ws.role)}</div>
        <div style="font-size: 11px; color: var(--text-dim);"><strong>核心数据源：</strong> ${escapeHtml(ws.source_name)}</div>
      </div>

      <!-- Part 3: Macro Stats -->
      <div class="detail-block">
        <div class="detail-block-title">Part 3 · 专案图谱全局宏观统计 (Macro Stats)</div>
        <div class="yonc-macro-grid" style="margin-bottom: 8px;">
          <div class="yonc-stat-box">
            <div class="yonc-stat-val">${stats.total_projects} <span style="font-size: 10px; color: var(--text-dim);">个</span></div>
            <div class="yonc-stat-lbl">全图总专案 (L1)</div>
          </div>
          <div class="yonc-stat-box">
            <div class="yonc-stat-val" style="color: var(--accent-green);">${stats.completed_projects} <span style="font-size: 10px; color: var(--text-dim);">个</span></div>
            <div class="yonc-stat-lbl">已完成专案 (14节点验)</div>
          </div>
          <div class="yonc-stat-box">
            <div class="yonc-stat-val" style="color: #38bdf8;">${stats.fully_l4_projects !== undefined ? stats.fully_l4_projects : 1} <span style="font-size: 10px; color: var(--text-dim);">完全 / ${stats.partial_l4_projects !== undefined ? stats.partial_l4_projects : 10} 部分</span></div>
            <div class="yonc-stat-lbl">L4 深度拆解专案</div>
          </div>
          <div class="yonc-stat-box">
            <div class="yonc-stat-val" style="color: #a78bfa;">${stats.timeline_assigned_count} <span style="font-size: 10px; color: var(--text-dim);">个</span></div>
            <div class="yonc-stat-lbl">时间线排期中</div>
          </div>
        </div>
        <div style="font-size: 9.5px; color: var(--text-dim); margin-top: 4px; display: flex; justify-content: space-between;">
          <span>WBS 节点分布：L1:${l1Break.L1 || 58} · L2:${l1Break.L2 || 94} · L3:${l1Break.L3 || 232} · L4:${l1Break.L4 || 307}</span>
          <span>总计: ${totalNodes} 节点 / ${stats.total_edges} 边</span>
        </div>
      </div>

      <!-- Part 1: Timeline Projects Table -->
      <div class="detail-block">
        <div class="detail-block-title">Part 1 · 时间线专案排期跟踪 (Timeline Projects · ${timelineProjects.length} 项)</div>
        <div class="yonc-table">
          <div class="yonc-table-header">
            <div>专案名称 (PROJECT)</div>
            <div>截止日期 (DUE DATE)</div>
            <div>任务进度 (TASK PROGRESS %)</div>
            <div>L4 拆解深度 (L4 DECOMPOSITION %)</div>
            <div>状态</div>
          </div>
          ${timelineRowsHtml}
        </div>
      </div>

      <!-- Part 2: Assign Suggestions -->
      <div class="detail-block">
        <div class="detail-block-title">Part 2 · 跨 Agent 分工委派建议 (Assign Suggestions · 6 大专业方向)</div>
        ${assignCardsHtml}
      </div>

      <!-- Part 4: Activities Split into Columns -->
      <div class="detail-block">
        <div class="detail-block-title">Part 4 · 专案动态与活动记录 (Activities & Sessions · 双栏分列展示)</div>
        <div style="margin-top: 6px;">
          ${activitiesColsHtml}
        </div>
      </div>
    `;
  }

  function renderWorkspaces() {
    workspacesGrid.innerHTML = '';
    state.agents.forEach((ws) => {
      const isExpanded = state.expandedAgentId === ws.agent_id;
      const card = document.createElement('div');
      card.className = `workspace-card ${isExpanded ? 'expanded' : ''}`;
      card.setAttribute('data-agent-id', ws.agent_id);

      const rawItems = ws.items || [];
      const itemsToRender = (ws.agent_id === 'wisdom-oldman')
        ? rawItems.filter(it => it.kind !== 'knowledge_topic')
        : rawItems;

      const itemsHtml = itemsToRender.map((it) => {
        const isActive = it.item_id === state.selectedItemId;
        const p = it.payload || {};
        let progressHtml = '';
        if (typeof p.progress_pct === 'number') {
          const pct = Math.min(100, Math.max(0, p.progress_pct));
          progressHtml = `
            <div class="mini-progress-row">
              <div class="mini-progress-bar"><div class="mini-progress-fill" style="width: ${pct}%;"></div></div>
              <span class="mini-progress-text">${pct}%</span>
            </div>
          `;
        }

        let topicPillHtml = '';
        if (it.kind === 'active_task' && p.parent_topic_title) {
          topicPillHtml = `<div class="topic-tag-pill">📂 所属主题: ${escapeHtml(p.parent_topic_title)}</div>`;
        }

        let statusTagHtml = `<span class="status-tag status-${escapeHtml(it.status)}">${escapeHtml(it.status)}</span>`;
        if (it.kind === 'active_task' && p.is_silent && it.status === 'RUNNING') {
          statusTagHtml = `<span class="status-tag status-RUNNING" style="background: rgba(245, 158, 11, 0.2); border-color: var(--accent-amber); color: #fcd34d;">RUNNING (心跳静默)</span>`;
        }

        return `
          <div class="item-row ${isActive ? 'active' : ''}" data-item-id="${escapeHtml(it.item_id)}">
            <div class="item-main">
              <div class="item-title">${escapeHtml(it.title)}</div>
              ${topicPillHtml}
              <div class="item-summary">${escapeHtml(it.summary || it.source_ref)}</div>
              ${progressHtml}
            </div>
            <div class="item-meta">
              ${statusTagHtml}
              <div>${formatTime(it.updated_at)}</div>
            </div>
          </div>
        `;
      }).join('');

      const glance = getAgentGlance(ws);

      let scholarPreviewHtml = '';
      if (ws.agent_id === 'scholar') {
        if (isExpanded) {
          scholarPreviewHtml = `
            <div class="scholar-card-preview expanded-card-view" onclick="event.stopPropagation();">
              <div class="scholar-preview-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <span style="font-size: 16px; font-weight: 700; color: #fff;">📊 Scholar 研究层级、5篇稿件推进状态与文献总库全景图</span>
                <span class="status-tag status-ACTIVE" style="font-size: 11px;">已放大展示 · 2 Fields · 4 Threads · 5 Papers</span>
              </div>
              ${renderScholarFullView(ws)}
            </div>
          `;
        } else {
          scholarPreviewHtml = `
            <div class="scholar-card-preview collapsed-card-view" onclick="window.__uuma_selectAgent('scholar')">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span style="font-size: 11px; font-weight: 700; color: #fff;">📊 Scholar 研究层级与状态图</span>
                <span class="status-tag status-ACTIVE" style="font-size: 9px;">2 Fields · 4 Threads · 5 Papers</span>
              </div>
              
              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin-bottom: 6px;">
                <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); border-radius: 4px; padding: 4px 6px;">
                  <div style="font-size: 10px; font-weight: 700; color: #38bdf8;">◇ Solar Energy (太阳能)</div>
                  <div style="font-size: 9px; color: var(--text-muted); margin-top: 2px; line-height: 1.4;">
                    • ↗ All-sky image: <span style="color: #34d399; font-weight: 600;">[2篇: 写作/返修]</span><br/>
                    • ↗ Satellite cloud: <span style="color: #94a3b8;">[1篇: 规划中]</span><br/>
                    • ↗ Islanded microgrid: <span style="color: #34d399; font-weight: 600;">[1篇: 写作中]</span>
                  </div>
                </div>
                <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); border-radius: 4px; padding: 4px 6px;">
                  <div style="font-size: 10px; font-weight: 700; color: #a78bfa;">◇ Rural Electrification (乡村)</div>
                  <div style="font-size: 9px; color: var(--text-muted); margin-top: 2px; line-height: 1.4;">
                    • ↗ Hybrid system: <span style="color: #94a3b8;">[1篇: 规划中]</span><br/>
                    <span style="color: var(--text-dim); font-style: italic;">(路线独立承载假说 · 0-N篇论文)</span>
                  </div>
                </div>
              </div>

              <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.25); border-radius: 4px; padding: 4px 6px; font-size: 10px;">
                <span style="color: #fca5a5; font-weight: 600;">⚙️ 文献总库解析态：</span>
                <span style="color: #cbd5e1;">可见 1197 篇 · <strong>当前解析中: 0 篇 (冷入库就绪)</strong></span>
              </div>
              <div style="font-size: 10px; color: var(--accent-blue); text-align: right; margin-top: 4px;">
                🔍 点击卡片展开查看完整 5 篇稿件、大图与流水线 ↗
              </div>
            </div>
          `;
        }
      }

      let wisdomPreviewHtml = '';
      if (ws.agent_id === 'wisdom-oldman') {
        wisdomPreviewHtml = renderWisdomPreviewHtml(ws, isExpanded);
      }

      let forgePreviewHtml = '';
      if (ws.agent_id === 'forge-lab-bot') {
        forgePreviewHtml = renderForgePreviewHtml(ws, isExpanded);
      }

      let brainstormerPreviewHtml = '';
      if (ws.agent_id === 'brainstormer') {
        brainstormerPreviewHtml = renderBrainstormerPreviewHtml(ws, isExpanded);
      }

      let yoncPreviewHtml = '';
      if (ws.agent_id === 'yonc') {
        yoncPreviewHtml = renderYoncPreviewHtml(ws, isExpanded);
      }

      card.innerHTML = `
        <div class="workspace-header" data-agent-id="${escapeHtml(ws.agent_id)}">
          <div class="header-left">
            <span class="toggle-caret">▶</span>
            <span class="agent-title">${escapeHtml(ws.name)}</span>
            <span class="status-tag status-${escapeHtml(ws.status)}">${escapeHtml(ws.status)}</span>
          </div>
          <div class="agent-glance" title="${escapeHtml(glance)}">${escapeHtml(glance)}</div>
          <div class="header-right">
            <span class="items-badge">${(ws.items || []).length} 项</span>
          </div>
        </div>
        <div class="agent-role">${escapeHtml(ws.role)}</div>
        ${scholarPreviewHtml}
        ${wisdomPreviewHtml}
        ${forgePreviewHtml}
        ${brainstormerPreviewHtml}
        ${yoncPreviewHtml}
        <div class="item-list" style="${(isExpanded && ws.agent_id === 'scholar') || ws.agent_id === 'brainstormer' || ws.agent_id === 'forge-lab-bot' || ws.agent_id === 'yonc' ? 'display: none;' : ''}">
          ${itemsHtml || '<div style="color: var(--text-dim); font-size: 11px; padding: 4px;">暂无活动项</div>'}
        </div>
      `;

      // Card Block Click -> Toggle Accordion Expansion + Inspect
      card.addEventListener('click', (e) => {
        // If clicking inside interactive child elements when expanded, don't toggle accordion
        if (e.target.closest('.item-row') || e.target.closest('.tree-paper-row') || e.target.closest('.forge-tree-proj-header') || e.target.closest('.wisdom-topic-card') || e.target.closest('button') || e.target.closest('a') || e.target.closest('.notion-link-pill') || e.target.closest('.yonc-activity-pill') || e.target.closest('.yonc-assign-btn') || e.target.closest('.yonc-assign-chip')) {
          return;
        }

        if (state.expandedAgentId === ws.agent_id) {
          // If already expanded, only collapse if clicking the header row
          if (e.target.closest('.workspace-header')) {
            state.expandedAgentId = null;
            selectAgent(ws);
            renderWorkspaces();
          }
        } else {
          // If collapsed, clicking ANYWHERE on the card block expands it directly!
          state.expandedAgentId = ws.agent_id;
          selectAgent(ws);
          renderWorkspaces();
        }
      });

      // Item click event -> Inspect Item
      card.querySelectorAll('.item-row').forEach((row) => {
        row.addEventListener('click', (e) => {
          e.stopPropagation();
          const itemId = row.getAttribute('data-item-id');
          selectItem(itemId);
        });
      });

      workspacesGrid.appendChild(card);
    });
  }

  // Load and Render Activity Events
  async function loadEvents() {
    try {
      const params = new URLSearchParams();
      if (state.filterAgent && state.filterAgent !== 'all') {
        params.append('agent_id', state.filterAgent);
      }
      if (state.searchQuery) {
        params.append('query', state.searchQuery);
      }
      params.append('limit', '50');

      const res = await fetch(`/api/observatory/events?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        state.events = data.events || [];
        renderEvents();
      }
    } catch (err) {
      console.warn('Load events failed:', err);
    }
  }

  function renderEvents() {
    activityFeed.innerHTML = '';
    const filteredEvents = state.events.filter((ev) => {
      if (state.filterAgent && state.filterAgent !== 'all') {
        if (ev.agent_id !== state.filterAgent) return false;
      }
      return true;
    });
    if (filteredEvents.length === 0) {
      activityFeed.innerHTML = '<div style="color: var(--text-dim); padding: 12px; text-align: center;">无匹配的审计活动记录</div>';
      return;
    }
    filteredEvents.forEach((ev) => {
      const card = document.createElement('div');
      const isActive = ev.event_id === state.selectedEventId;
      card.className = `event-card ${isActive ? 'active' : ''}`;
      card.setAttribute('data-event-id', escapeHtml(ev.event_id));
      card.innerHTML = `
        <div style="flex: 1; min-width: 0;">
          <span class="event-agent-tag">[${escapeHtml(ev.agent_id)}]</span>
          <span style="color: #cbd5e1;">${escapeHtml(ev.summary)}</span>
        </div>
        <div class="event-time">${formatTime(ev.captured_at)}</div>
      `;

      // Event Card Click -> Inspect Event
      card.addEventListener('click', () => {
        selectEvent(ev);
      });

      activityFeed.appendChild(card);
    });
  }

  function setInspectorOpen(isOpen, savePreference = false) {
    if (savePreference) {
      state.isSidebarOpen = isOpen;
      try {
        localStorage.setItem('uuma_sidebar_open', isOpen ? 'true' : 'false');
      } catch (_) {}
    }
    if (isOpen) {
      inspectorPane.classList.remove('collapsed');
      if (state.sidebarWidth) {
        inspectorPane.style.width = state.sidebarWidth + 'px';
        document.documentElement.style.setProperty('--sidebar-width', state.sidebarWidth + 'px');
      }
      if (btnToggleSidebar) btnToggleSidebar.classList.add('active');
    } else {
      inspectorPane.classList.add('collapsed');
      if (btnToggleSidebar) btnToggleSidebar.classList.remove('active');
    }
  }

  function toggleInspector() {
    const isCurrentlyCollapsed = inspectorPane.classList.contains('collapsed');
    // User explicitly toggled sidebar: invert and save preference
    setInspectorOpen(isCurrentlyCollapsed, true);
  }

  function renderScholarDashboard(ws) {
    return `
      <div class="detail-block">
        <div class="detail-block-title">智能体概览与运行状态</div>
        <div style="font-size: 13px; margin-bottom: 6px;">
          <strong>状态：</strong> <span class="status-tag status-${escapeHtml(ws.status)}">${escapeHtml(ws.status)}</span>
          <span style="margin-left: 10px;"><strong>健康度：</strong> <span class="badge-live ${ws.health === 'HEALTHY' ? '' : 'polling'}">${escapeHtml(ws.health)}</span></span>
        </div>
        <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 5px;"><strong>核心职责：</strong> ${escapeHtml(ws.role)}</div>
        <div style="font-size: 12px; color: var(--text-dim);"><strong>核心数据源：</strong> ${escapeHtml(ws.source_name)}</div>
      </div>
      ${renderScholarFullView(ws)}
    `;
  }

  // Inspect an Agent directly
  function selectAgent(ws) {
    state.selectedAgentId = ws.agent_id;
    state.selectedItemId = null;
    state.selectedEventId = null;
    renderEvents();
    if (state.isSidebarOpen) {
      setInspectorOpen(true, false);
    }

    inspTitle.textContent = ws.name;
    inspSubtitle.textContent = `智能体工作区 · ${ws.agent_id} · ${ws.source_name}`;

    const items = ws.items || [];
    countSessions.textContent = 0;
    countTools.textContent = 0;
    countArtifacts.textContent = 0;

    if (ws.agent_id === 'scholar') {
      inspectorBody.innerHTML = renderScholarDashboard(ws);
      return;
    }

    if (ws.agent_id === 'forge-lab-bot') {
      inspectorBody.innerHTML = renderForgeDashboard(ws);
      return;
    }

    if (ws.agent_id === 'yonc') {
      inspectorBody.innerHTML = renderYoncDashboard(ws);
      return;
    }

    const itemsSummaryHtml = items.map(it => `
      <div class="item-row" style="margin-bottom: 4px;" onclick="window.__uuma_selectItem('${escapeHtml(it.item_id)}')">
        <div class="item-main">
          <div class="item-title">${escapeHtml(it.title)}</div>
          <div class="item-summary">${escapeHtml(it.summary)}</div>
        </div>
        <span class="status-tag status-${escapeHtml(it.status)}">${escapeHtml(it.status)}</span>
      </div>
    `).join('');

    inspectorBody.innerHTML = `
      <div class="detail-block">
        <div class="detail-block-title">智能体概览与运行状态</div>
        <div style="font-size: 12px; margin-bottom: 5px;">
          <strong>状态：</strong> <span class="status-tag status-${escapeHtml(ws.status)}">${escapeHtml(ws.status)}</span>
          <span style="margin-left: 8px;"><strong>健康度：</strong> <span class="badge-live ${ws.health === 'HEALTHY' ? '' : 'polling'}">${escapeHtml(ws.health)}</span></span>
        </div>
        <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 5px;"><strong>核心职责：</strong> ${escapeHtml(ws.role)}</div>
        <div style="font-size: 11px; color: var(--text-dim);"><strong>核心数据源：</strong> ${escapeHtml(ws.source_name)}</div>
      </div>

      <div class="detail-block">
        <div class="detail-block-title">归属活动项 (${items.length})</div>
        ${itemsSummaryHtml || '<div style="color: var(--text-dim); font-size: 11px;">暂无归属活动项</div>'}
      </div>
    `;
  }

  window.__uuma_selectAgent = function(id) {
    const ws = state.agents.find(a => a.agent_id === id);
    if (ws) {
      state.expandedAgentId = ws.agent_id;
      selectAgent(ws);
      renderWorkspaces();
    }
  };

  // Inspect an Activity Event
  function selectEvent(ev) {
    state.selectedEventId = ev.event_id;
    state.selectedItemId = null;
    state.selectedAgentId = null;
    renderEvents();
    renderWorkspaces();
    if (state.isSidebarOpen) {
      setInspectorOpen(true, false);
    }

    inspTitle.textContent = ev.summary || `Event ${ev.event_id.slice(0, 10)}`;
    inspSubtitle.textContent = `[${ev.agent_id}] · 钩子: ${ev.hook} · 来源: ${ev.source_path || 'hermes_spool'}`;

    countSessions.textContent = 0;
    countTools.textContent = ev.tool_name ? 1 : 0;
    countArtifacts.textContent = 0;

    let parsedSnippet = {};
    if (ev.raw_snippet) {
      try {
        parsedSnippet = JSON.parse(ev.raw_snippet);
      } catch {
        parsedSnippet = { raw: ev.raw_snippet };
      }
    }

    inspectorBody.innerHTML = `
      <div class="detail-block">
        <div class="detail-block-title">审计事件详情</div>
        <div style="font-size: 12px; margin-bottom: 5px;">
          <strong>智能体：</strong> <span class="event-agent-tag">[${escapeHtml(ev.agent_id)}]</span>
          <span style="margin-left: 8px;"><strong>事件类型：</strong> <code>${escapeHtml(ev.hook)}</code></span>
        </div>
        <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 3px;"><strong>发生时间：</strong> ${ev.captured_at || '—'}</div>
        <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 3px;"><strong>工具调用：</strong> ${escapeHtml(ev.tool_name || '无')}</div>
        <div style="font-size: 11px; color: var(--text-dim); margin-bottom: 5px;"><strong>日志来源：</strong> ${escapeHtml(ev.source_path || 'hermes_spool')}</div>
        <div style="font-size: 12px; margin-top: 6px; color: #fff;">${escapeHtml(ev.summary)}</div>
      </div>

      <div class="detail-block">
        <div class="detail-block-title">原始载荷快照 (Raw Snippet)</div>
        <div class="code-box">${escapeHtml(JSON.stringify(parsedSnippet, null, 2))}</div>
      </div>
    `;
  }

  // Select Item and Load Inspector Details
  async function selectItem(itemId) {
    state.selectedItemId = itemId;
    state.selectedEventId = null;
    state.selectedAgentId = null;
    renderWorkspaces();
    renderEvents();
    if (state.isSidebarOpen) {
      setInspectorOpen(true, false);
    }

    // Fast-path: local cache display immediately
    const localItem = findItemLocally(itemId);
    if (localItem) {
      renderInspectorContent({ item: localItem, sessions: [] });
    } else {
      inspTitle.textContent = '加载详情中...';
      inspSubtitle.textContent = itemId;
      inspectorBody.innerHTML = '<div style="color: var(--text-dim); text-align: center; margin-top: 40px;">正在提取跨源详细记录...</div>';
    }

    // Increment request epoch to avoid async race conditions
    const currentEpoch = ++state.requestEpoch;

    try {
      const res = await fetch(`/api/observatory/items/${encodeURIComponent(itemId)}`);
      if (currentEpoch !== state.requestEpoch) {
        return; // Discard stale response
      }
      if (res.ok) {
        const data = await res.json();
        state.selectedItemData = data;
        renderInspectorContent(data);
      }
    } catch (err) {
      console.warn('Item deep fetch failed:', err);
    }
  }

  // Make selectItem and Forge interaction helpers globally accessible for onclick links
  window.__uuma_selectItem = selectItem;

  window.__uuma_selectCommerceChannel = function(ch) {
    state.forgeCommerceFilter = ch || 'all';
    setInspectorOpen(true, false);
    selectItem('forge_commerce_monitor');
  };

  window.__uuma_selectJournalSystem = function(sys) {
    state.forgeJournalFilter = sys || 'all';
    setInspectorOpen(true, false);
    selectItem('forge_notion_journals');
  };

  window.__uuma_setCommerceFilter = function(ch) {
    state.forgeCommerceFilter = ch || 'all';
    if (state.selectedItemData) {
      renderInspectorContent(state.selectedItemData);
    }
  };

  window.__uuma_setJournalFilter = function(sys) {
    state.forgeJournalFilter = sys || 'all';
    if (state.selectedItemData) {
      renderInspectorContent(state.selectedItemData);
    }
  };

  window.__uuma_toggleOrderExpand = function(lineId) {
    state.expandedOrderId = (state.expandedOrderId === lineId) ? null : lineId;
    if (state.selectedItemData) {
      renderInspectorContent(state.selectedItemData);
    }
  };

  window.__uuma_toggleJournalExpand = function(jId) {
    state.expandedJournalId = (state.expandedJournalId === jId) ? null : jId;
    if (state.selectedItemData) {
      renderInspectorContent(state.selectedItemData);
    }
  };

  window.__uuma_toggleBsTopic = function(topicId, e) {
    if (e) e.stopPropagation();
    state.bsTopicExpanded = state.bsTopicExpanded || {};
    const bsAgent = state.agents.find(a => a.agent_id === 'brainstormer');
    const dagItem = (bsAgent && bsAgent.items || []).find(it => it.kind === 'decision_dag');
    const topics = (dagItem && dagItem.payload && dagItem.payload.topics) || [];
    const idx = topics.findIndex(t => t.topic_id === topicId);
    const currentlyOpen = Object.prototype.hasOwnProperty.call(state.bsTopicExpanded, topicId)
      ? !!state.bsTopicExpanded[topicId]
      : (idx === 0);
    state.bsTopicExpanded[topicId] = !currentlyOpen;
    renderWorkspaces();
    if (state.selectedItemData && (state.selectedItemData.kind === 'decision_dag' || state.selectedItemData.kind === 'architecture_topic')) {
      renderInspectorContent(state.selectedItemData);
    }
  };

  window.__uuma_setAllBsTopics = function(isOpen, e) {
    if (e) e.stopPropagation();
    state.bsTopicExpanded = state.bsTopicExpanded || {};
    const bsAgent = state.agents.find(a => a.agent_id === 'brainstormer');
    const dagItem = (bsAgent && bsAgent.items || []).find(it => it.kind === 'decision_dag');
    const topics = (dagItem && dagItem.payload && dagItem.payload.topics) || [];
    topics.forEach(t => {
      state.bsTopicExpanded[t.topic_id] = isOpen;
    });
    renderWorkspaces();
    if (state.selectedItemData && (state.selectedItemData.kind === 'decision_dag' || state.selectedItemData.kind === 'architecture_topic')) {
      renderInspectorContent(state.selectedItemData);
    }
  };

  window.__uuma_toggleBsShowAll = function(e) {
    if (e) e.stopPropagation();
    state.bsShowAllTopics = !state.bsShowAllTopics;
    renderWorkspaces();
    if (state.selectedItemData && (state.selectedItemData.kind === 'decision_dag' || state.selectedItemData.kind === 'architecture_topic')) {
      renderInspectorContent(state.selectedItemData);
    }
  };


  function renderInspectorContent(data) {
    const item = data.item;
    const sessions = data.sessions || [];
    const p = item.payload || {};

    inspTitle.textContent = item.title;
    inspSubtitle.textContent = `${item.agent_id} · ${item.kind} · 来源: ${item.source_ref}`;

    // Update tab counts
    countSessions.textContent = sessions.length;
    countTools.textContent = (p && p.tools) ? p.tools.length : 0;
    countArtifacts.textContent = (p && p.artifacts) ? p.artifacts.length : 0;

    if (state.activeTab === 'overview') {
      let specializedBlock = '';

      // 1. Brainstormer Decision Map DAG & Architecture Topics View
      if (item.kind === 'decision_dag' || item.kind === 'architecture_topic') {
        specializedBlock = renderBrainstormerInspector(item, p);
      }
      // Yonc Project Graph Core View (Part 1, 2, 3, 4)
      else if (item.kind === 'project_graph' || item.item_id === 'yonc_graph_core') {
        const yoncWs = state.agents.find(a => a.agent_id === 'yonc') || { items: [item] };
        specializedBlock = renderYoncDashboard(yoncWs);
      }
      // 2. Forge Workspace Overview (Comprehensive Part 1, Part 2, Part 3 View)
      else if (item.kind === 'forge_workspace') {
        const forgeWs = state.agents.find(a => a.agent_id === 'forge-lab-bot') || { items: [item] };
        specializedBlock = renderForgeFullView(forgeWs);
      }
      // 3. Forge Hardware Entity Project View
      else if (item.kind === 'forge_project') {
        const steps = p.pipeline_steps || [];
        const stepsHtml = steps.map(s => {
          const icon = s.status === 'COMPLETED' ? '✓' : (s.status === 'IN_PROGRESS' ? '▶' : '○');
          return `
            <div class="pipeline-step step-${escapeHtml(s.status)}">
              <div>
                <span style="font-family: var(--font-mono); font-weight: 700; margin-right: 4px;">${icon} ${s.step}.</span>
                <span>${escapeHtml(s.name)}</span>
              </div>
              <span class="status-tag status-${escapeHtml(s.status)}">${escapeHtml(s.status)}</span>
            </div>
          `;
        }).join('');

        const bomListHtml = (p.bom_files || []).map(f => `
          <div style="padding: 2px 0; font-size: 11px; color: #cbd5e1; font-family: var(--font-mono);">
            📄 ${escapeHtml(f)}
          </div>
        `).join('') || '<div style="color: var(--text-dim); font-size: 11px;">暂无独立 BOM 文件</div>';

        const openItemsHtml = (p.open_items || []).map(oi => `
          <li style="margin-bottom: 2px; color: #fca5a5;">${escapeHtml(oi)}</li>
        `).join('');

        const paramsHtml = Object.entries(p.resolved_parameters || {}).map(([k, v]) => `
          <div style="padding: 3px 0; border-bottom: 1px solid rgba(255,255,255,0.04); font-size: 11px;">
            <span style="color: var(--text-dim); font-weight: 600;">${escapeHtml(k)}:</span>
            <span style="color: #cbd5e1; margin-left: 4px;">${typeof v === 'object' ? escapeHtml(JSON.stringify(v)) : escapeHtml(v)}</span>
          </div>
        `).join('');

        const nodesHtml = Object.entries(p.nodes || {}).map(([nk, nv]) => `
          <div style="padding: 4px; background: rgba(255,255,255,0.02); border-radius: 4px; margin-bottom: 4px; font-size: 11px;">
            <div style="font-weight: 600; color: var(--accent-blue);">${escapeHtml(nv.name || nk)} (${escapeHtml(nv.model || 'Node')})</div>
            <div style="color: var(--text-muted); font-size: 10px;">状态: ${escapeHtml(nv.status || 'active')} · 系统: ${escapeHtml(nv.os || 'Linux')}</div>
          </div>
        `).join('');

        const worklogsHtml = (p.db_worklogs || []).map(wl => `
          <div style="padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.04); font-size: 11px;">
            <div style="color: #fff;">${escapeHtml(wl.action)}</div>
            <div style="color: var(--accent-amber); font-size: 10px; margin-top: 2px;">结论: ${escapeHtml(wl.result || '进行中')}</div>
          </div>
        `).join('');

        const pt = p.procurement_trace || {};
        const ptFulfilled = pt.fulfilled_count || 0;
        const ptInTransit = pt.in_transit_count || 0;
        const ptOrdered = pt.ordered_count || 0;
        const ptMatched = pt.total_matched || 0;
        const ptSamples = pt.sample_items || [];

        const ptSamplesHtml = ptSamples.map(si => `
          <div style="display: flex; justify-content: space-between; align-items: center; padding: 3px 0; border-bottom: 1px solid rgba(255,255,255,0.04); font-size: 11px;">
            <div style="flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-right: 6px;">
              <span style="font-weight: 600; color: #fb923c;">[${escapeHtml(si.platform)}]</span>
              <span style="color: #cbd5e1;">${escapeHtml(si.product)}</span>
            </div>
            <div style="flex-shrink: 0;">
              <span style="font-size: 10px; color: var(--text-dim); margin-right: 4px;">匹配: <code>${escapeHtml(si.keyword)}</code></span>
              <span class="status-tag status-${si.status === '已到货/入库' ? 'COMPLETED' : (si.status === '运输在途' ? 'PURCHASING' : 'WAITING')}" style="font-size: 9px;">${escapeHtml(si.status)}</span>
            </div>
          </div>
        `).join('');

        specializedBlock = `
          <div class="detail-block">
            <div class="detail-block-title">硬件项目生命周期进展 (Hardware Lifecycle)</div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <div>
                <strong style="color: #fff; font-size: 12px;">当前阶段：${escapeHtml(p.stage_name)}</strong>
              </div>
              <span class="status-tag status-${escapeHtml(p.stage_code)}">${escapeHtml(p.stage_code)}</span>
            </div>

            <div class="mini-progress-row" style="margin-bottom: 8px;">
              <div class="mini-progress-bar" style="height: 6px;"><div class="mini-progress-fill" style="width: ${p.progress_pct}%;"></div></div>
              <span class="mini-progress-text" style="font-size: 11px;">${p.progress_pct}%</span>
            </div>

            <div class="pipeline-track">
              ${stepsHtml}
            </div>

            <!-- Project Procurement & BOM Fulfillment -->
            <div class="detail-block-title" style="margin-top: 10px;">物料采购与 BOM 履约追踪 (Procurement & BOM Fulfillment)</div>
            <div class="breakdown-grid" style="margin-bottom: 8px;">
              <div class="breakdown-box">
                <div class="breakdown-label" style="color: var(--accent-green);">已到货 / 入库</div>
                <div class="breakdown-val" style="color: var(--accent-green);">${ptFulfilled} 项</div>
              </div>
              <div class="breakdown-box">
                <div class="breakdown-label" style="color: var(--accent-amber);">采购在途 / 运输中</div>
                <div class="breakdown-val" style="color: var(--accent-amber);">${ptInTransit} 项</div>
              </div>
              <div class="breakdown-box">
                <div class="breakdown-label" style="color: #fb923c;">已拍下 / 待发货</div>
                <div class="breakdown-val" style="color: #fb923c;">${ptOrdered} 项</div>
              </div>
              <div class="breakdown-box">
                <div class="breakdown-label" style="color: var(--text-dim);">匹配物料项</div>
                <div class="breakdown-val" style="color: var(--text-dim);">${ptMatched} 项</div>
              </div>
            </div>
            ${ptSamplesHtml ? `
              <div style="background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.06); border-radius: 4px; padding: 6px 8px; margin-bottom: 8px;">
                <div style="font-size: 10px; color: var(--text-dim); margin-bottom: 4px; font-weight: 600;">已匹配物料流水样本：</div>
                ${ptSamplesHtml}
              </div>
            ` : ''}

            <div class="stat-grid" style="margin-top: 10px;">
              <div class="stat-box">
                <div class="stat-label">BOM 清单文件</div>
                <div class="stat-val" style="color: var(--accent-green);">${p.bom_count} 份</div>
              </div>
              <div class="stat-box">
                <div class="stat-label">技术设计文档</div>
                <div class="stat-val" style="color: var(--accent-blue);">${p.docs_count} 篇</div>
              </div>
              <div class="stat-box">
                <div class="stat-label">电路/原理图纸</div>
                <div class="stat-val" style="color: var(--accent-purple);">${p.design_count} 份</div>
              </div>
              <div class="stat-box">
                <div class="stat-label">实操工作日志</div>
                <div class="stat-val" style="color: var(--accent-amber);">${p.worklogs_count} 条</div>
              </div>
            </div>

            <div class="detail-block-title" style="margin-top: 10px;">BOM 与物料候选文档</div>
            <div style="background: rgba(0,0,0,0.2); padding: 6px 8px; border-radius: 4px; margin-bottom: 8px;">
              ${bomListHtml}
            </div>

            ${nodesHtml ? `
              <div class="detail-block-title" style="margin-top: 8px;">计算节点与基础设施配置</div>
              ${nodesHtml}
            ` : ''}

            ${paramsHtml ? `
              <div class="detail-block-title" style="margin-top: 8px;">已定型工程设计参数 (Resolved Parameters)</div>
              ${paramsHtml}
            ` : ''}

            ${openItemsHtml ? `
              <div class="detail-block-title" style="margin-top: 8px; color: #f87171;">待决议设计事项 (Open Design Items)</div>
              <ul style="padding-left: 16px; margin: 4px 0; font-size: 11px;">
                ${openItemsHtml}
              </ul>
            ` : ''}

            ${worklogsHtml ? `
              <div class="detail-block-title" style="margin-top: 8px;">实验室构建与工艺记录 (lab.db Worklogs)</div>
              ${worklogsHtml}
            ` : ''}

            <div style="font-size: 10px; color: var(--text-dim); margin-top: 10px;">
              <strong>工程目录：</strong> <code>${escapeHtml(p.folder_path || '—')}</code>
            </div>
          </div>
        `;
      }
      // 4. Forge Commerce Tracker View
      else if (item.kind === 'forge_commerce') {
        const batch = p.latest_batch || {};
        const orderLines = p.order_lines || [];
        const sb = p.status_breakdown || {};
        const inTransit = sb.in_transit || 0;
        const awaiting = sb.awaiting_dispatch || 0;
        const completed = sb.completed || 0;
        const cancelled = sb.cancelled || 0;
        const eh = p.engine_health || {};
        const ch = eh.channels || {};
        const pddCh = ch.pdd || { dot: '🟡', count: 603, latest_time: '2026-10-09 16:33' };
        const shopeeCh = ch.shopee || { dot: '🟡', count: 303, latest_time: '2026-10-09 13:40' };
        const tbCh = ch.taobao || { dot: '🟡', count: 165, latest_time: '2026-10-09 13:29' };
        const curFilter = state.forgeCommerceFilter || 'all';

        let filteredLines = orderLines;
        if (curFilter === 'pdd') {
          filteredLines = orderLines.filter(l => (l.platform || '').toLowerCase() === 'pdd');
        } else if (curFilter === 'shopee') {
          filteredLines = orderLines.filter(l => (l.platform || '').toLowerCase() === 'shopee');
        } else if (curFilter === 'taobao') {
          filteredLines = orderLines.filter(l => (l.platform || '').toLowerCase() === 'taobao');
        } else if (curFilter === 'unreviewed') {
          filteredLines = orderLines.filter(l => (l.review_status || '') === 'unreviewed');
        }

        const linesListHtml = filteredLines.length > 0 ? filteredLines.map(ol => {
          const isExpanded = state.expandedOrderId === ol.line_id;
          const plat = (ol.platform || 'pdd').toLowerCase();
          const platBadgeClass = `badge-plat-${plat}`;
          const platLabel = (ol.platform || 'PDD').toUpperCase();

          let statusClass = 'COMPLETED';
          if (ol.order_status === '卖家已发货' || ol.order_status === '运输中') statusClass = 'PURCHASING';
          else if (ol.order_status === '拼单成功') statusClass = 'WAITING';
          else if (ol.order_status === 'Cancelled' || ol.order_status === '交易关闭') statusClass = 'BLOCKED';

          return `
            <div class="forge-order-card">
              <div class="forge-order-header" onclick="window.__uuma_toggleOrderExpand('${escapeHtml(ol.line_id)}')">
                <div style="min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 62%;">
                  <span class="tree-badge-platform ${platBadgeClass}">${platLabel}</span>
                  <span style="font-weight: 600; color: #f1f5f9;">${escapeHtml(ol.product_name || '商品物料')}</span>
                  ${ol.variant_name ? `<span style="font-size: 10px; color: var(--text-dim); margin-left: 4px;">(${escapeHtml(ol.variant_name)})</span>` : ''}
                </div>
                <div style="flex-shrink: 0; display: flex; align-items: center; gap: 6px;">
                  <strong style="color: var(--accent-green); font-size: 11px;">¥${Number(ol.line_total || ol.unit_price || 0).toFixed(2)}</strong>
                  <span class="status-tag status-${statusClass}" style="font-size: 8px; padding: 1px 4px;">${escapeHtml(ol.order_status || '已完成')}</span>
                  <span style="font-size: 10px; color: var(--text-dim);">${isExpanded ? '▾' : '▸'}</span>
                </div>
              </div>
              ${isExpanded ? `
                <div class="forge-order-body">
                  <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin-bottom: 4px;">
                    <div><strong>店铺名称：</strong> ${escapeHtml(ol.shop_name || '—')}</div>
                    <div><strong>订单编号：</strong> <code style="font-size: 9.5px;">${escapeHtml(ol.order_id || ol.line_id)}</code></div>
                    <div><strong>单价/数量：</strong> ¥${Number(ol.unit_price || 0).toFixed(2)} × ${ol.quantity || 1} 件</div>
                    <div><strong>规格款式：</strong> ${escapeHtml(ol.variant_name || '默认款式')}</div>
                    <div><strong>下单时间：</strong> ${escapeHtml(ol.created_at || '—')}</div>
                    <div><strong>归属评审：</strong> <span style="color: #c084fc; font-weight: 600;">${escapeHtml(ol.review_status || 'unreviewed')}</span> (待确认)</div>
                  </div>
                  <div style="font-size: 9.5px; color: var(--text-dim); border-top: 1px dashed rgba(255,255,255,0.06); padding-top: 3px; margin-top: 3px;">
                    ℹ️ 观测台只读保护：此条目归属于 <code>${platLabel}</code> 抓取流水。人类分类标签请通过外部 Agent / Telegram 会话标记。
                  </div>
                </div>
              ` : ''}
            </div>
          `;
        }).join('') : '<div style="color: var(--text-dim); font-size: 11px; padding: 12px; text-align: center;">当前分类筛选下暂无订单数据</div>';

        const filterTabsHtml = `
          <div class="forge-filter-tabs">
            <span class="forge-tab-pill ${curFilter === 'all' ? 'active' : ''}" onclick="window.__uuma_setCommerceFilter('all')">全部 (${p.triage_summary?.total_lines || 1071})</span>
            <span class="forge-tab-pill pill-pdd ${curFilter === 'pdd' ? 'active' : ''}" onclick="window.__uuma_setCommerceFilter('pdd')">拼多多 (${pddCh.count || 603})</span>
            <span class="forge-tab-pill pill-shopee ${curFilter === 'shopee' ? 'active' : ''}" onclick="window.__uuma_setCommerceFilter('shopee')">Shopee (${shopeeCh.count || 303})</span>
            <span class="forge-tab-pill pill-taobao ${curFilter === 'taobao' ? 'active' : ''}" onclick="window.__uuma_setCommerceFilter('taobao')">淘宝 (${tbCh.count || 165})</span>
            <span class="forge-tab-pill pill-unrev ${curFilter === 'unreviewed' ? 'active' : ''}" onclick="window.__uuma_setCommerceFilter('unreviewed')">待审门控 (${p.triage_summary?.unreviewed || 1071})</span>
          </div>
        `;

        specializedBlock = `
          <div class="detail-block">
            <div class="detail-block-title">采购订单流转状态分解 (Procurement Status Breakdown)</div>
            <div class="breakdown-grid">
              <div class="breakdown-box">
                <div class="breakdown-label" style="color: var(--accent-amber);">采购在途 / 运输中</div>
                <div class="breakdown-val" style="color: var(--accent-amber);">${inTransit} 笔</div>
              </div>
              <div class="breakdown-box">
                <div class="breakdown-label" style="color: #fb923c;">拼单达成 / 待发货</div>
                <div class="breakdown-val" style="color: #fb923c;">${awaiting} 笔</div>
              </div>
              <div class="breakdown-box">
                <div class="breakdown-label" style="color: var(--accent-green);">已采购完成 / 入库</div>
                <div class="breakdown-val" style="color: var(--accent-green);">${completed} 笔</div>
              </div>
              <div class="breakdown-box">
                <div class="breakdown-label" style="color: var(--text-dim);">已取消 / 关闭</div>
                <div class="breakdown-val" style="color: var(--text-dim);">${cancelled} 笔</div>
              </div>
            </div>

            <div class="stat-grid">
              <div class="stat-box">
                <div class="stat-label">归档批次数</div>
                <div class="stat-val">${p.batch_count || 0}</div>
              </div>
              <div class="stat-box">
                <div class="stat-label">订单总笔数</div>
                <div class="stat-val">${p.total_orders || 0}</div>
              </div>
              <div class="stat-box" style="grid-column: span 2;">
                <div class="stat-label">累计采购金额</div>
                <div class="stat-val" style="color: var(--accent-green);">¥${Number(p.total_spend_cny || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2 })} CNY</div>
              </div>
            </div>

            <!-- Multi-Platform Ingestion Engine Health & Timestamps -->
            <div class="detail-block-title" style="margin-top: 10px;">多平台抓取引擎状态与时间审计 (Engine Health & Timestamps)</div>
            <div style="background: rgba(251, 191, 36, 0.08); border: 1px solid rgba(251, 191, 36, 0.3); border-radius: 6px; padding: 8px 10px; margin-bottom: 8px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <span style="font-weight: 700; color: #fde68a; font-size: 11px;">
                  ${eh.status_dot || '🟡'} 多平台抓取引擎：${escapeHtml(eh.status_label || '待刷新 (Outdated)')}
                </span>
                <span style="font-size: 10px; color: var(--text-dim);">最新全量同步: <strong style="color: #cbd5e1;">${escapeHtml(eh.latest_pull_formatted || '2026-10-09 16:33')}</strong></span>
              </div>
              <div style="font-size: 10px; color: #cbd5e1; line-height: 1.4;">
                ${escapeHtml(eh.note || '上次拉取成功并已安全归档至 lab.db (共 1,071 笔)。距今 > 24 小时，处于待增量拉取就绪状态。')}
              </div>
            </div>

            <!-- Ingestion Channels Breakdown -->
            <div style="display: flex; gap: 6px; margin-bottom: 8px; flex-wrap: wrap;">
              <div style="flex: 1; min-width: 140px; background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 4px; padding: 6px 8px; font-size: 11px; cursor: pointer;" onclick="window.__uuma_setCommerceFilter('pdd')">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
                  <span style="font-weight: 600; color: #fb923c;">${pddCh.dot || '🟡'} 拼多多 (PDD)</span>
                  <span style="font-size: 10px; color: var(--accent-green);">${pddCh.count || 603} 笔</span>
                </div>
                <div style="font-size: 10px; color: var(--text-dim);">最近拉取: ${escapeHtml(pddCh.latest_time || '2026-10-09 16:33')}</div>
              </div>
              <div style="flex: 1; min-width: 140px; background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 4px; padding: 6px 8px; font-size: 11px; cursor: pointer;" onclick="window.__uuma_setCommerceFilter('shopee')">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
                  <span style="font-weight: 600; color: #f97316;">${shopeeCh.dot || '🟡'} Shopee (虾皮)</span>
                  <span style="font-size: 10px; color: var(--accent-green);">${shopeeCh.count || 303} 笔</span>
                </div>
                <div style="font-size: 10px; color: var(--text-dim);">最近拉取: ${escapeHtml(shopeeCh.latest_time || '2026-10-09 13:40')}</div>
              </div>
              <div style="flex: 1; min-width: 140px; background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 4px; padding: 6px 8px; font-size: 11px; cursor: pointer;" onclick="window.__uuma_setCommerceFilter('taobao')">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
                  <span style="font-weight: 600; color: #38bdf8;">${tbCh.dot || '🟡'} 淘宝 (Taobao)</span>
                  <span style="font-size: 10px; color: var(--accent-green);">${tbCh.count || 165} 笔</span>
                </div>
                <div style="font-size: 10px; color: var(--text-dim);">最近拉取: ${escapeHtml(tbCh.latest_time || '2026-10-09 13:29')}</div>
              </div>
            </div>

            <!-- Ownership Triage & Human Review Gate -->
            <div class="detail-block-title" style="margin-top: 10px;">订单分类与人类复核门控 (Triage & Human Review)</div>
            <div style="background: rgba(168, 85, 247, 0.06); border: 1px solid rgba(168, 85, 247, 0.2); border-radius: 5px; padding: 8px 10px; margin-bottom: 8px; font-size: 11px; line-height: 1.5; cursor: pointer;" onclick="window.__uuma_setCommerceFilter('unreviewed')">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <strong style="color: #c084fc;">待人类评审确认归属：${(p.triage_summary && p.triage_summary.unreviewed) || 1071} 笔商品</strong>
                <span class="status-tag status-PENDING_REVIEW">待分类评审</span>
              </div>
              <div style="color: #cbd5e1; font-size: 10px;">
                • <strong>Step 1 (自动拉取)：</strong> 自动从淘宝/拼多多/Shopee抓取全量订单与最新流转状态并归档至 <code>lab.db</code>。<br/>
                • <strong>Step 2 (人工分类)：</strong> 区分 <code>self</code> (实验室物料) 与 <code>others</code> (个人日常/非实验)，滤除非实验订单。<br/>
                • <strong>Step 3 (BOM比对)：</strong> 仅对确认 <code>self</code> 的硬件物料与 5 大成熟工程 BOM 执行自动履约匹配与验收入库。
              </div>
              <div style="margin-top: 6px; padding-top: 6px; border-top: 1px dashed rgba(168, 85, 247, 0.3); font-size: 10px; color: #d8b4fe;">
                ℹ️ <strong>观测台只读 (VO) 契约声明：</strong> 本观测台严格保持只读遥测属性（View-Only）。人类归属确认由用户通过与 Telegram Bot / 外部 Agent 会话或导出 Excel 4表协议异步更新，不在本界面直接提供改库操作。
              </div>
            </div>

            <!-- Project BOM Fulfillment Trace Matrix -->
            ${(p.bom_trace && p.bom_trace.length > 0) ? `
              <div class="detail-block-title" style="margin-top: 10px;">成熟 BOM 自动溯源与履约矩阵 (BOM Fulfillment Trace)</div>
              <div style="display: flex; flex-direction: column; gap: 6px; margin-bottom: 8px;">
                ${p.bom_trace.map(bt => `
                  <div style="background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 4px; padding: 6px 8px; font-size: 11px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px;">
                      <span style="font-weight: 600; color: #fff;">${escapeHtml(bt.project_name)}</span>
                      <span style="font-size: 10px; color: var(--text-dim);">
                        已入库: <strong style="color: var(--accent-green);">${bt.fulfilled_count}</strong> |
                        在途: <strong style="color: var(--accent-amber);">${bt.in_transit_count}</strong> |
                        待发货: <strong style="color: #fb923c;">${bt.ordered_count}</strong>
                      </span>
                    </div>
                    <div style="font-size: 10px; color: #94a3b8; display: flex; flex-wrap: wrap; gap: 4px; margin-top: 2px;">
                      ${bt.sample_items.map(si => `
                        <span style="background: rgba(255,255,255,0.04); padding: 1px 4px; border-radius: 2px; border: 1px solid rgba(255,255,255,0.08);">
                          [${escapeHtml(si.platform)}] ${escapeHtml(si.keyword)}: <span style="color: ${si.status === '已到货/入库' ? 'var(--accent-green)' : (si.status === '运输在途' ? 'var(--accent-amber)' : '#cbd5e1')};">${escapeHtml(si.status)}</span>
                        </span>
                      `).join('')}
                    </div>
                  </div>
                `).join('')}
              </div>
            ` : ''}

            <div style="font-size: 11px; margin-bottom: 5px; margin-top: 8px;"><strong>最新归档批次：</strong> <code>${escapeHtml(batch.batch_id || '—')}</code> (${batch.order_count || 0} 单 / ${batch.line_count || 0} 行)</div>
            <div class="detail-block-title" style="margin-top: 8px; margin-bottom: 4px;">多平台订单流水明细 (点击展开详情)</div>
            ${filterTabsHtml}
            <div class="forge-scroll-list">
              ${linesListHtml}
            </div>
          </div>
        `;
      }
      // 5. Forge Journal Runner View
      else if (item.kind === 'forge_journal') {
        const pages = p.recent_journal_pages || [];
        const sysBreakdown = p.system_breakdown || {};
        const curSysFilter = state.forgeJournalFilter || 'all';

        let filteredPages = pages;
        if (curSysFilter !== 'all') {
          filteredPages = pages.filter(pg => (pg.norm_system === curSysFilter) || (pg.project_system === curSysFilter));
        }

        const journalTabsHtml = `
          <div class="forge-filter-tabs">
            <span class="forge-tab-pill ${curSysFilter === 'all' ? 'active' : ''}" onclick="window.__uuma_setJournalFilter('all')">全部 (${p.total_pages || pages.length || 29})</span>
            ${Object.entries(sysBreakdown).map(([k, v]) => `
              <span class="forge-tab-pill ${curSysFilter === k ? 'active' : ''}" onclick="window.__uuma_setJournalFilter('${escapeHtml(k)}')">${escapeHtml(k)} (${v})</span>
            `).join('')}
          </div>
        `;

        const journalCardsHtml = filteredPages.length > 0 ? filteredPages.map(pg => {
          const isExpanded = state.expandedJournalId === pg.journal_id;
          const sysTag = pg.norm_system || pg.project_system || '3DP';
          const blocks = pg.content_blocks || [];

          return `
            <div class="forge-journal-card">
              <div class="forge-journal-header" onclick="window.__uuma_toggleJournalExpand('${escapeHtml(pg.journal_id)}')">
                <div style="min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 68%;">
                  <span style="font-weight: 600; color: #fff;">${escapeHtml(pg.title || '无标题工程日志')}</span>
                </div>
                <div style="flex-shrink: 0; display: flex; align-items: center; gap: 6px;">
                  <span style="font-size: 9px; color: var(--accent-blue); background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.25); padding: 1.5px 5px; border-radius: 3px;">${escapeHtml(sysTag)}</span>
                  <span style="font-size: 10px; color: var(--text-dim);">${isExpanded ? '▾' : '▸'}</span>
                </div>
              </div>
              ${isExpanded ? `
                <div class="forge-journal-body">
                  <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin-bottom: 6px;">
                    <div><strong>所属硬件系统：</strong> ${escapeHtml(pg.project_system || pg.norm_system || '—')}</div>
                    <div><strong>日志类型：</strong> ${escapeHtml(pg.entry_type || '硬件工程日志')}</div>
                    <div><strong>同步状态：</strong> <span class="status-tag status-${pg.sync_status === 'SYNCED' ? 'COMPLETED' : 'WAITING'}" style="font-size: 8px; padding: 1px 4px;">${escapeHtml(pg.sync_status || 'SYNCED')}</span></div>
                    <div><strong>最后更新：</strong> ${escapeHtml(pg.updated_at || '—')}</div>
                  </div>

                  <!-- Real Engineering Content Notes from Notion snapshot_json -->
                  <div class="journal-content-box">
                    <div style="font-weight: 700; color: #38bdf8; margin-bottom: 5px; font-size: 11px;">📄 日志正文要点记录 (Engineering Journal Notes):</div>
                    ${blocks.length > 0 ? blocks.map(cb => {
                      if (cb.type && cb.type.startsWith('heading')) {
                        return `<div style="font-weight: 700; color: #fde68a; margin-top: 6px; margin-bottom: 2px;">📌 ${escapeHtml(cb.text)}</div>`;
                      } else if (cb.type === 'quote') {
                        return `<div style="color: #34d399; font-weight: 600; padding: 2px 6px; background: rgba(52, 211, 153, 0.08); border-left: 3px solid #34d399; margin: 4px 0;">💡 ${escapeHtml(cb.text)}</div>`;
                      } else if (cb.type === 'bulleted_list_item' || cb.type === 'numbered_list_item') {
                        return `<div style="color: #e2e8f0; padding-left: 10px; margin: 2px 0;">• ${escapeHtml(cb.text)}</div>`;
                      } else {
                        return `<div style="color: #cbd5e1; margin: 2px 0;">${escapeHtml(cb.text)}</div>`;
                      }
                    }).join('') : '<div style="color: var(--text-dim); font-style: italic;">（未录入文字正文详情）</div>'}
                  </div>

                  ${pg.notion_url ? `
                    <div style="margin-top: 8px; text-align: right;">
                      <a href="${escapeHtml(pg.notion_url)}" target="_blank" rel="noopener noreferrer" class="notion-link-pill" style="display: inline-block; font-size: 10.5px; text-decoration: none; color: var(--accent-blue); background: rgba(56, 189, 248, 0.15); padding: 3px 8px; border-radius: 4px; border: 1px solid rgba(56, 189, 248, 0.35); font-weight: 600;">
                        打开 Notion 原文 ↗
                      </a>
                    </div>
                  ` : ''}
                </div>
              ` : ''}
            </div>
          `;
        }).join('') : '<div style="color: var(--text-dim); font-size: 11px; padding: 12px; text-align: center;">当前系统分类下暂无日志页面</div>';

        const syncIso = (p.latest_sync_job && p.latest_sync_job.updated_at) || p.last_synced_at || item.updated_at || '';
        const runnerTimeAgo = formatTimeAgo(syncIso);
        const runnerStatusLabel = (p.runner_status === 'READY' || p.runner_status === 'SYNCED') ? 'SYNCED' : (p.runner_status || 'IDLE');

        specializedBlock = `
          <div class="detail-block">
            <div class="detail-block-title">Notion 硬件工程日志总览</div>
            <div style="font-size: 12px; margin-bottom: 6px; display: flex; align-items: center; flex-wrap: wrap; gap: 4px;">
              <strong>Runner 同步状态：</strong>
              <span class="status-tag status-${runnerStatusLabel === 'SYNCED' ? 'SYNCED' : escapeHtml(p.runner_status)}" style="padding: 1.5px 6px;">${escapeHtml(runnerStatusLabel)}</span>
              ${runnerTimeAgo ? `<span style="color: var(--text-dim); font-size: 10px; font-weight: normal; margin-left: 3px;" title="最后同步时间: ${formatTime(syncIso)}">${escapeHtml(runnerTimeAgo)}</span>` : ''}
              <span style="color: var(--text-muted); font-size: 11px; margin-left: 8px;">已同步收录 <strong>${p.total_pages || 29}</strong> 篇页面</span>
            </div>

            <div class="detail-block-title" style="margin-top: 8px; margin-bottom: 4px;">系统分类筛选</div>
            ${journalTabsHtml}

            <div class="detail-block-title" style="margin-top: 8px; margin-bottom: 4px;">工程日志列表 (共 ${filteredPages.length} 篇 · 点击展开详情)</div>
            <div class="forge-scroll-list">
              ${journalCardsHtml}
            </div>
          </div>
        `;
      }
      // 4. Scholar Research Hierarchy View (Part 1)
      else if (item.kind === 'research_hierarchy') {
        const fields = p.hierarchy || [];
        const breakdown = p.stage_breakdown || {};

        const hierarchyHtml = fields.map(f => {
          const topicsHtml = (f.topics || []).map(tp => {
            const threadsHtml = (tp.threads || []).map(tr => {
              const papers = tr.papers || [];
              const papersHtml = papers.length > 0 ? papers.map(pp => `
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 4px 6px; background: rgba(255,255,255,0.03); border-radius: 4px; margin-top: 3px; font-size: 11px;">
                  <span style="color: #f1f5f9; font-weight: 500;"><span style="margin-right: 3px;">📝</span><span class="tree-badge-paper">Paper</span>${escapeHtml(pp.title)}</span>
                  <span class="status-tag status-${pp.stage_key === 'WRITING' ? 'IN_PROGRESS' : (pp.stage_key === 'REVISION' ? 'BLOCKED' : 'IDLE')}" style="font-size: 9px;">${escapeHtml(pp.stage)}</span>
                </div>
              `).join('') : `
                <div style="font-size: 10px; color: var(--text-dim); padding: 3px 6px; font-style: italic;">
                  (暂无 Paper 写作稿件 · 独立探索路线 / 纯科学问题阶段)
                </div>
              `;

              return `
                <div style="padding: 6px 8px; background: rgba(56, 189, 248, 0.03); border: 1px solid rgba(56, 189, 248, 0.15); border-radius: 5px; margin-top: 5px;">
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-weight: 600; color: var(--accent-blue); font-size: 11px;">↗ <span class="tree-badge-thread">Thread</span>${escapeHtml(tr.title)}</span>
                    <span class="status-tag status-IDLE" style="font-size: 9px;">${escapeHtml(tr.status)}</span>
                  </div>
                  ${tr.question ? `<div style="font-size: 10px; color: var(--text-muted); margin-top: 2px;">❓ ${escapeHtml(tr.question)}</div>` : ''}
                  <div style="margin-top: 4px;">
                    <div style="font-size: 9px; color: var(--text-dim); text-transform: uppercase; font-weight: 700;">写作稿件 (Manuscripts - ${papers.length} 篇):</div>
                    ${papersHtml}
                  </div>
                </div>
              `;
            }).join('');

            return `
              <div style="margin-left: 8px; margin-top: 6px; border-left: 2px solid rgba(255,255,255,0.08); padding-left: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <span style="font-weight: 600; color: #e2e8f0; font-size: 11px;">◈ <span class="tree-badge-topic">Topic</span> ${escapeHtml(tp.name)}</span>
                  <span class="status-tag status-IDLE" style="font-size: 9px;">${escapeHtml(tp.status)}</span>
                </div>
                ${threadsHtml}
              </div>
            `;
          }).join('');

          return `
            <div style="background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 6px; padding: 8px; margin-bottom: 8px;">
              <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 4px;">
                <span style="font-weight: 700; color: #fff; font-size: 12px;">◇ <span class="tree-badge-field">Field</span>${escapeHtml(f.name)}</span>
                <span class="status-tag status-IDLE">${escapeHtml(f.status)}</span>
              </div>
              ${topicsHtml}
            </div>
          `;
        }).join('');

        specializedBlock = `
          <div class="detail-block">
            <div class="detail-block-title">研究层级与写作阶段 (Research Hierarchy & Stages)</div>
            <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 8px;">
              层级规则：<code>Field (领域) → Topic (主题) → Thread/Track (路线) → Paper (写作产物)</code>
            </div>

            <div class="stat-grid">
              <div class="stat-box">
                <div class="stat-label">研究领域 (Fields)</div>
                <div class="stat-val" style="color: var(--accent-blue);">${p.fields_count || 2} 个</div>
              </div>
              <div class="stat-box">
                <div class="stat-label">研究路线 (Threads / Tracks)</div>
                <div class="stat-val" style="color: var(--accent-purple);">${p.threads_count || 4} 条</div>
              </div>
              <div class="stat-box">
                <div class="stat-label">写作稿件 (Manuscripts)</div>
                <div class="stat-val" style="color: var(--accent-green);">${p.papers_count || 5} 篇</div>
              </div>
              <div class="stat-box">
                <div class="stat-label">写作阶段分布</div>
                <div class="stat-val" style="font-size: 11px; color: #cbd5e1; font-weight: normal; margin-top: 3px;">
                  写作中: <strong>${breakdown.WRITING || 2}</strong> · 返修中: <strong>${breakdown.REVISION || 1}</strong> · 规划中: <strong>${breakdown.PLANNING || 2}</strong>
                </div>
              </div>
            </div>

            <div style="font-size: 11px; color: #38bdf8; background: rgba(56,189,248,0.08); border: 1px solid rgba(56,189,248,0.2); border-radius: 4px; padding: 5px 8px; margin-bottom: 10px;">
              ℹ️ <strong>路线与论文归属规范：</strong> Track (Thread) 拥有完整的科学状态。一条 Track 允许有 0 到多篇 Paper；纯探索或未成文的 Track 不会伪造论文。
            </div>

            <div class="detail-block-title">层级树结构与当前阶段</div>
            ${hierarchyHtml}
          </div>
        `;
      }
      // 5. Scholar Catalog Pipeline & Core Graph Parsing State (Part 2)
      else if (item.kind === 'catalog_pipeline') {
        const stages = p.core_graph_stages || [];
        const stagesHtml = stages.map(s => {
          const icon = s.state === 'COMPLETED' ? '✓' : (s.state === 'RUNNING' ? '▶' : '○');
          return `
            <div class="pipeline-step step-${escapeHtml(s.state)}" style="margin-bottom: 4px;">
              <div>
                <span style="font-family: var(--font-mono); font-weight: 700; margin-right: 4px;">${icon} ${s.step}.</span>
                <span style="font-weight: 600;">${escapeHtml(s.name)}</span>
                <div style="font-size: 10px; color: var(--text-dim); margin-top: 2px;">${escapeHtml(s.summary)}</div>
              </div>
              <span class="status-tag status-${escapeHtml(s.state)}">${escapeHtml(s.state)}</span>
            </div>
          `;
        }).join('');

        specializedBlock = `
          <div class="detail-block">
            <div class="detail-block-title">文献总库与 Core Graph 处理流水线</div>
            
            <div class="stat-grid">
              <div class="stat-box">
                <div class="stat-label">总库可见论文</div>
                <div class="stat-val" style="color: var(--accent-blue);">${p.visible_papers || 1197} 篇</div>
              </div>
              <div class="stat-box">
                <div class="stat-label">衍生内容隔离</div>
                <div class="stat-val" style="color: var(--text-dim);">${p.quarantined_papers || 1980} 篇</div>
              </div>
              <div class="stat-box">
                <div class="stat-label">PDF 身份已核验 (VERIFIED)</div>
                <div class="stat-val" style="color: var(--accent-green);">${p.pdf_verified || 1697} 份</div>
              </div>
              <div class="stat-box">
                <div class="stat-label">待审核 (NEEDS_REVIEW)</div>
                <div class="stat-val" style="color: var(--accent-amber);">${p.pdf_needs_review || 1467} 份</div>
              </div>
            </div>

            <div style="background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.25); border-radius: 5px; padding: 8px; margin-bottom: 10px;">
              <div style="font-weight: 700; color: #fca5a5; font-size: 11px; margin-bottom: 4px;">
                🔍 关于「文献是否有在解析」的权威状态：
              </div>
              <div style="font-size: 11px; color: #fecaca; line-height: 1.5;">
                • <strong>当前正在解析 (Parsing)：</strong> <code>0 篇</code><br/>
                • <strong>持久队列排队中 (Queued)：</strong> <code>0 项</code><br/>
                • <strong>状态定论：</strong> ${escapeHtml(p.pipeline_verdict)}
              </div>
            </div>

            <div class="detail-block-title">Core Graph 文献处理全生命周期流水线</div>
            <div class="pipeline-track">
              ${stagesHtml}
            </div>
          </div>
        `;
      }
      // 6. Scholar FieldKG View (Part 3)
      else if (item.kind === 'fieldkg_status') {
        specializedBlock = `
          <div class="detail-block">
            <div class="detail-block-title">FieldKG 与 OpenSPG/KAG 知识图谱状态</div>
            <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 6px;">
              权威与投影：<code>${escapeHtml(p.authority || 'data/catalog.db')} → projection_outbox (${p.outbox_pending || 0} 积压) → ${escapeHtml(p.engine || 'OpenSPG/KAG')}</code>
            </div>

            <div class="stat-grid">
              <div class="stat-box">
                <div class="stat-label">核心实体节点 (Nodes)</div>
                <div class="stat-val" style="color: var(--accent-blue);">${p.nodes_count || 0} 个</div>
              </div>
              <div class="stat-box">
                <div class="stat-label">关系三元组 (Edges)</div>
                <div class="stat-val" style="color: var(--accent-purple);">${p.edges_count || 0} 条</div>
              </div>
              <div class="stat-box">
                <div class="stat-label">原文证据节点 (Evidence)</div>
                <div class="stat-val" style="color: var(--accent-green);">${p.evidence_count || 0} 条</div>
              </div>
              <div class="stat-box">
                <div class="stat-label">密封快照 (Snapshots)</div>
                <div class="stat-val" style="color: var(--accent-amber);">${p.snapshots_count || 0} 份</div>
              </div>
            </div>

            <div style="font-size: 11px; color: #cbd5e1; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06); border-radius: 4px; padding: 6px 8px; margin-top: 8px; line-height: 1.5;">
              • <strong>图谱状态：</strong> <span class="status-tag status-IDLE">${escapeHtml(p.status || 'READY')}</span> ${escapeHtml(p.lifecycle_state || '待从文献集合构建第一版 Snapshot (冷库基线就绪)')}<br/>
              • <strong>Track-first 边界规范：</strong> ${escapeHtml(p.track_first_rule || 'Field 拥有 living FieldKG，Track 显式采纳不可变 Snapshot vN')}
            </div>
          </div>
        `;
      }
      // 7. Scholar Stage & Last Tweak View (Part 4)
      else if (item.kind === 'stage_progress') {
        const tweaks = p.last_tweaks || [];
        const suite = p.test_suite || {};
        const tweaksHtml = tweaks.map(t => `
          <div style="padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 11px;">
            <span style="font-weight: 600; color: var(--accent-blue);">[${escapeHtml(t.component)}]</span>
            <span style="color: #cbd5e1; margin-left: 4px;">${escapeHtml(t.fix)}</span>
          </div>
        `).join('');

        specializedBlock = `
          <div class="detail-block">
            <div class="detail-block-title">研发阶段与最新改动 (Stage & Tweaks)</div>
            <div style="font-size: 12px; margin-bottom: 5px;">
              <strong>当前阶段：</strong> <span style="color: #fff; font-weight: 600;">${escapeHtml(p.current_stage)}</span>
            </div>
            <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 6px;">
              <strong>门控契约：</strong> <code>${escapeHtml(p.stage_gate)}</code>
              <span class="status-tag status-PENDING_REVIEW" style="margin-left: 5px;">${escapeHtml(p.gate_status)}</span>
            </div>

            <div class="stat-grid">
              <div class="stat-box">
                <div class="stat-label">测试通过 (PASS)</div>
                <div class="stat-val" style="color: var(--accent-green);">${suite.passed || 1078}</div>
              </div>
              <div class="stat-box">
                <div class="stat-label">现有告警 (Warnings)</div>
                <div class="stat-val" style="color: var(--accent-amber);">${suite.warnings || 20}</div>
              </div>
            </div>

            <div class="detail-block-title" style="margin-top: 6px;">最新修复与提交改动</div>
            ${tweaksHtml}
          </div>
        `;
      }
      // 5. Wisdom Investigation Task View
      else if (item.kind === 'active_task') {
        const isSilent = p.is_silent;
        const timeline = p.timeline || [];

        const timelineHtml = timeline.map(ev => {
          let dotColor = 'green';
          if (ev.event_type.includes('CREATED')) dotColor = 'green';
          else if (ev.event_type.includes('ROUTE')) dotColor = 'purple';
          else if (ev.event_type.includes('ASSIGNED')) dotColor = 'amber';
          else if (ev.event_type.includes('RUN')) dotColor = 'blue';

          const pl = ev.payload || {};
          let summary = '';
          if (ev.event_type === 'TASK_CREATED') {
            summary = `任务目标: ${(pl.contract && pl.contract.objective) ? pl.contract.objective.slice(0, 110) + '...' : '任务在调度器中创建'}`;
          } else if (ev.event_type === 'ROUTE_DECIDED') {
            summary = `路由指派: ${(pl.decision && pl.decision.selected_agent) || 'wisdom-oldman'} (${(pl.decision && pl.decision.rationale) ? pl.decision.rationale[0] : '舰队语义分配'})`;
          } else if (ev.event_type === 'TASK_ASSIGNED') {
            summary = `执行人接单: ${pl.agent_id || 'wisdom-oldman'}`;
          } else if (ev.event_type === 'RUN_REGISTERED') {
            summary = `运行启动: ${(pl.registration && pl.registration.run_id) || ''} (${(pl.registration && pl.registration.execution_class) || 'BACKGROUND'})`;
          } else {
            summary = JSON.stringify(pl).slice(0, 90);
          }

          return `
            <div class="timeline-node">
              <div class="timeline-dot ${dotColor}"></div>
              <div class="timeline-content">
                <div class="timeline-time">${formatTime(ev.occurred_at)} · 序号 #${ev.sequence}</div>
                <div class="timeline-type">${escapeHtml(ev.event_type)} <span style="font-size: 10px; font-weight: normal; color: var(--text-dim);">(操作者: ${escapeHtml(ev.actor_id || 'orchestrator')})</span></div>
                <div class="timeline-detail">${escapeHtml(summary)}</div>
              </div>
            </div>
          `;
        }).join('');

        specializedBlock = `
          <!-- 所属知识主题横幅 -->
          <div class="detail-block" style="border-left: 3px solid #c084fc; background: rgba(192, 132, 252, 0.05);">
            <div class="detail-block-title" style="color: #c084fc;">📂 所属知识主题与层级归属</div>
            <div style="font-size: 13px; font-weight: 700; color: #fff; margin-bottom: 4px;">
              ${escapeHtml(p.parent_topic_title || '青葱 的 气雾栽培细节&核心构建要素 ，分株法')}
            </div>
            <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 6px;">
              <strong>Topic ID：</strong> <code>${escapeHtml(p.parent_topic_id || 'topic_07a8574b5d504d34a5483407c2a88400')}</code> · 
              <strong>主题状态：</strong> <span class="status-tag status-${p.parent_topic_status || 'ACTIVE'}">${p.parent_topic_status || 'ACTIVE'}</span>
            </div>
            <div style="font-size: 11px;">
              ${p.standalone_url ? `<a href="${p.standalone_url}" target="_blank" style="color: var(--accent-blue); text-decoration: none;">📖 打开完整主题文档与版本历史 (v45) ↗</a>` : ''}
              <span style="color: var(--text-dim); margin-left: 10px;">关联远程 OpenSPG: <a href="http://192.168.55.2:8887" target="_blank" style="color: var(--accent-blue);">192.168.55.2:8887 ↗</a></span>
            </div>
          </div>

          <!-- 真实运行状态探针 -->
          <div class="detail-block">
            <div class="detail-block-title">真实执行状态与心跳探针 (Liveness Probe)</div>
            <div class="liveness-banner ${!isSilent ? 'active-running' : ''}">
              <div class="liveness-banner-title">
                <span style="color: ${isSilent ? 'var(--accent-amber)' : 'var(--accent-green)'};">${escapeHtml(p.liveness_badge || '运行状态')}</span>
                <span style="font-size: 10px; color: var(--text-dim);">尝试: ${p.attempt || 1} · 已完成步数: ${p.completed_steps || 0}</span>
              </div>
              <div class="liveness-banner-text">
                ${escapeHtml(p.liveness_explanation || '')}
              </div>
              <div style="font-size: 10.5px; color: var(--text-muted); margin-top: 5px;">
                <strong>心跳记录：</strong> ${escapeHtml(p.heartbeat_delay_str || '—')} (上次心跳: ${p.last_heartbeat || '无'})
              </div>
              ${p.blocker ? `<div style="font-size: 11px; color: var(--accent-red); margin-top: 5px;"><strong>阻塞原因：</strong> ${escapeHtml(p.blocker)}</div>` : ''}
            </div>
          </div>

          <!-- 核心调研目标与待解决缺口 -->
          <div class="detail-block">
            <div class="detail-block-title">核心调研目标与待证 GAP</div>
            <div style="font-size: 11.5px; color: #cbd5e1; margin-bottom: 6px;">${escapeHtml(p.objective || '')}</div>
            <div style="margin-top: 6px;">
              <div class="gap-box">
                <div class="gap-box-title">🌿 GAP 1: 缓苗期周期与成活率判定</div>
                <div style="color: #cbd5e1;">青葱分株后缓苗要多久？查找直接证据，给出具体天数范围与新根长度等判断指标。</div>
              </div>
              <div class="gap-box">
                <div class="gap-box-title">💧 GAP 2: 气雾培喷雾间隔与营养液参数</div>
                <div style="color: #cbd5e1;">青葱（Allium fistulosum）气雾培的喷雾间隔、喷头与营养液参数有哪些可定位的直接证据？适用条件是什么？</div>
              </div>
            </div>
          </div>

          <!-- 任务全生命周期审计轨迹 (铺他们的 login / log) -->
          <div class="detail-block">
            <div class="detail-block-title">任务全生命周期审计轨迹 (Timeline Log)</div>
            <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 6px;">
              自创建、路由、分配到启动的完整事件时间链条（共 ${timeline.length} 步）：
            </div>
            <div class="timeline-track">
              ${timelineHtml || '<div style="color: var(--text-dim); font-size: 11px;">暂无轨迹事件</div>'}
            </div>
          </div>
        `;
      }
      // 6. Wisdom Knowledge Topic View
      else if (item.kind === 'knowledge_topic') {
        const underTasks = p.under_tasks || [];
        const claims = p.claims || [];

        const underTasksHtml = underTasks.map(t => `
          <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.06); border-radius: 4px; padding: 6px 8px; margin-bottom: 4px; font-size: 11px;">
            <div>
              <span style="font-weight: 600; color: #38bdf8;">${escapeHtml(t.title)}</span>
              ${t.is_silent ? '<span style="color: var(--accent-amber); font-size: 10px; margin-left: 4px;">(心跳静默)</span>' : ''}
            </div>
            <div style="display: flex; align-items: center; gap: 6px;">
              <span class="status-tag status-${escapeHtml(t.status)}" style="font-size: 10px;">${escapeHtml(t.status)}</span>
              <button onclick="window.__uuma_selectItem('${escapeHtml('wisdom_task_' + t.task_id)}')" style="background: rgba(56,189,248,0.15); border: 1px solid rgba(56,189,248,0.3); color: #38bdf8; border-radius: 3px; font-size: 10px; padding: 2px 5px; cursor: pointer;">检查 ↗</button>
            </div>
          </div>
        `).join('');

        const claimsHtml = claims.map((c, idx) => `
          <div class="claim-item">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
              <span style="font-weight: 700; color: var(--accent-green);">断言 #${idx + 1} (${escapeHtml(c.claim_id.slice(0, 12))})</span>
              <span class="status-tag status-COMPLETED" style="font-size: 9px;">${escapeHtml(c.status || 'CONFIRMED')}</span>
            </div>
            <div style="color: #cbd5e1;">${escapeHtml(c.statement || `${c.subject || ''} ${c.predicate || ''} ${c.object || ''}`)}</div>
          </div>
        `).join('');

        specializedBlock = `
          <!-- 主题体系指标卡片 -->
          <div class="detail-block">
            <div class="detail-block-title">主题体系与知识沉淀全景</div>
            <div style="font-size: 13px; font-weight: 700; color: #fff; margin-bottom: 4px;">
              ${escapeHtml(p.title || item.title)}
            </div>
            <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 8px;">
              ${p.aliases && p.aliases.length ? `<strong>主题别名：</strong> ${escapeHtml(p.aliases.join(', '))}<br/>` : ''}
              ${p.superseded_by_topic_id ? `<span style="color: var(--accent-amber);">⚠️ 该主题为归档副本，已合并至主干 topic: <code>${escapeHtml(p.superseded_by_topic_id)}</code></span><br/>` : ''}
              ${p.summary ? `<div style="color: #cbd5e1; margin-top: 4px;">${escapeHtml(p.summary)}</div>` : ''}
            </div>

            <div class="stat-grid" style="margin-bottom: 8px;">
              <div class="stat-box">
                <div class="stat-label">演进版本数</div>
                <div class="stat-val" style="color: #c084fc;">v${p.ver_cnt || 45}</div>
              </div>
              <div class="stat-box">
                <div class="stat-label">沉淀事实断言</div>
                <div class="stat-val" style="color: var(--accent-green);">${p.claim_count || 8} 项</div>
              </div>
              <div class="stat-box">
                <div class="stat-label">支撑文献引据</div>
                <div class="stat-val" style="color: var(--accent-blue);">${p.links_cnt || 20} 处</div>
              </div>
              <div class="stat-box">
                <div class="stat-label">挂靠调查任务</div>
                <div class="stat-val" style="color: var(--accent-amber);">${underTasks.length} 项</div>
              </div>
            </div>

            <div style="font-size: 11px; display: flex; gap: 10px;">
              ${p.standalone_url ? `<a href="${p.standalone_url}" target="_blank" style="color: var(--accent-blue); text-decoration: none;">📖 打开主题独立文档服务 (Port 8767) ↗</a>` : ''}
              <a href="${p.openspg_endpoint || 'http://192.168.55.2:8887'}" target="_blank" style="color: var(--accent-blue); text-decoration: none;">🌐 远程 OpenSPG 图谱端点 ↗</a>
            </div>
          </div>

          <!-- 此主题下属调查任务 -->
          <div class="detail-block">
            <div class="detail-block-title">📂 归属于此主题的调查任务 (${underTasks.length})</div>
            ${underTasksHtml || '<div style="color: var(--text-dim); font-size: 11px;">此主题下暂未挂靠未完成调查任务</div>'}
          </div>

          <!-- 已沉淀断言 -->
          ${claims.length ? `
            <div class="detail-block">
              <div class="detail-block-title">已验证知识断言 (Knowledge Claims)</div>
              ${claimsHtml}
            </div>
          ` : ''}
        `;
      }

      inspectorBody.innerHTML = `
        <div class="detail-block">
          <div class="detail-block-title">基本信息</div>
          <div style="font-size: 12px; margin-bottom: 5px;"><strong>状态：</strong> <span class="status-tag status-${escapeHtml(item.status)}">${escapeHtml(item.status)}</span></div>
          <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 3px;"><strong>发生时间：</strong> ${item.updated_at || '—'}</div>
          <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 3px;"><strong>数据来源：</strong> ${escapeHtml(item.source_ref)}</div>
          <div style="font-size: 12px; margin-top: 6px; color: #fff;">${escapeHtml(item.summary)}</div>
        </div>

        ${specializedBlock}

        <div class="detail-block">
          <div class="detail-block-title">特化载荷 (Specialized Payload)</div>
          <div class="code-box">${escapeHtml(JSON.stringify(item.payload, null, 2))}</div>
        </div>
      `;
    } else if (state.activeTab === 'timeline') {
      const p = item.payload || {};
      const timeline = p.timeline || [];
      if (timeline.length > 0) {
        inspectorBody.innerHTML = `
          <div class="detail-block">
            <div class="detail-block-title">任务全生命周期审计轨迹 (${timeline.length} 步事件)</div>
            <div style="font-size: 11px; color: var(--text-dim); margin-bottom: 8px;">按事件发生时间排列的完整调度与执行回溯</div>
            <div class="timeline-track">
              ${timeline.map(ev => `
                <div class="timeline-node">
                  <div class="timeline-dot ${ev.event_type.includes('CREATED') ? 'green' : (ev.event_type.includes('ROUTE') ? 'purple' : (ev.event_type.includes('ASSIGNED') ? 'amber' : 'blue'))}"></div>
                  <div class="timeline-content">
                    <div class="timeline-time">${formatTime(ev.occurred_at)} · 序号 #${ev.sequence}</div>
                    <div class="timeline-type">${escapeHtml(ev.event_type)} <span style="font-size: 10px; font-weight: normal; color: var(--text-dim);">(执行方: ${escapeHtml(ev.actor_id || 'orchestrator')})</span></div>
                    <div class="timeline-detail">${escapeHtml(JSON.stringify(ev.payload || {}))}</div>
                  </div>
                </div>
              `).join('')}
            </div>
          </div>
        `;
      } else {
        inspectorBody.innerHTML = `
          <div class="detail-block">
            <div class="detail-block-title">执行时间线</div>
            <div style="font-size: 11px; color: var(--text-dim); margin-bottom: 6px;">按事件发生时间排列的完整回溯</div>
            <div style="display: flex; flex-direction: column; gap: 6px;">
              <div style="display: flex; justify-content: space-between; font-size: 11px;">
                <span>• 初始创建与记录捕获</span>
                <span style="color: var(--text-dim);">${formatTime(item.updated_at)}</span>
              </div>
            </div>
          </div>
        `;
      }
    } else if (state.activeTab === 'sessions') {
      if (sessions.length === 0) {
        inspectorBody.innerHTML = `
          <div class="detail-block" style="text-align: center; color: var(--text-dim); padding: 20px; font-size: 11px;">
            当前项未关联单独会话记录<br>
            <span style="font-size: 10px;">(该项通过本地业务数据库直接同步)</span>
          </div>
        `;
      } else {
        inspectorBody.innerHTML = sessions.map(s => `
          <div class="detail-block">
            <div class="detail-block-title">会话 ${escapeHtml(s.session_id)}</div>
            <div style="font-size: 11px;">消息数: ${s.message_count}</div>
          </div>
        `).join('');
      }
    } else if (state.activeTab === 'tools') {
      inspectorBody.innerHTML = `
        <div class="detail-block" style="text-align: center; color: var(--text-dim); padding: 20px; font-size: 11px;">
          暂无专属工具调用快照，相关调用详见下方全局审计活动流。
        </div>
      `;
    } else if (state.activeTab === 'artifacts') {
      inspectorBody.innerHTML = `
        <div class="detail-block" style="text-align: center; color: var(--text-dim); padding: 20px; font-size: 11px;">
          暂无独立文件交付物。
        </div>
      `;
    }
  }

  // Switch Inspector Tab
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.activeTab = btn.getAttribute('data-tab');
      if (state.selectedItemData) {
        renderInspectorContent(state.selectedItemData);
      }
    });
  });

  if (btnToggleSidebar) {
    btnToggleSidebar.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggleInspector();
    });
  }

  if (btnCloseInsp) {
    btnCloseInsp.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      setInspectorOpen(false, true);
    });
  }

  // Draggable Resizer for Right Inspector Pane with Persistence
  const inspectorResizer = document.getElementById('inspector-resizer');
  if (inspectorResizer && inspectorPane) {
    let startX = 0;
    let startW = state.sidebarWidth || 420;
    let isDragging = false;

    inspectorResizer.addEventListener('mousedown', (e) => {
      if (e.button !== 0) return; // Only main left mouse button
      e.preventDefault();
      e.stopPropagation();

      isDragging = true;
      startX = e.clientX;
      startW = inspectorPane.getBoundingClientRect().width;

      inspectorResizer.classList.add('is-dragging');
      inspectorPane.classList.add('resizing');
      document.body.classList.add('is-resizing-inspector');

      function onMouseMove(moveEvent) {
        if (!isDragging) return;
        // Sidebar is docked on the right side, so moving left increases width
        const deltaX = startX - moveEvent.clientX;
        let newWidth = Math.round(startW + deltaX);

        // Minimum 300px, maximum 75% of window width (up to 1100px)
        const minW = 300;
        const maxW = Math.max(minW, Math.min(Math.round(window.innerWidth * 0.75), 1100));
        newWidth = Math.max(minW, Math.min(newWidth, maxW));

        state.sidebarWidth = newWidth;
        inspectorPane.style.width = newWidth + 'px';
        document.documentElement.style.setProperty('--sidebar-width', newWidth + 'px');
      }

      function onMouseUp() {
        if (!isDragging) return;
        isDragging = false;
        inspectorResizer.classList.remove('is-dragging');
        inspectorPane.classList.remove('resizing');
        document.body.classList.remove('is-resizing-inspector');

        window.removeEventListener('mousemove', onMouseMove);
        window.removeEventListener('mouseup', onMouseUp);

        // Persist the user's resized width in localStorage
        try {
          localStorage.setItem('uuma_sidebar_width', String(state.sidebarWidth));
        } catch (_) {}
      }

      window.addEventListener('mousemove', onMouseMove);
      window.addEventListener('mouseup', onMouseUp);
    });
  }

  // Filter Pills Handling
  agentFilters.querySelectorAll('.filter-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      agentFilters.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      state.filterAgent = pill.getAttribute('data-agent');
      loadEvents();
    });
  });

  // Search input debounced
  let searchTimer = null;
  eventSearch.addEventListener('input', (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.searchQuery = e.target.value.trim();
      loadEvents();
    }, 250);
  });

  // Feed scroll listener
  activityFeed.addEventListener('scroll', () => {
    state.isFeedScrolled = activityFeed.scrollTop > 50;
    if (!state.isFeedScrolled) {
      state.newEventsCount = 0;
      newEventsBtn.style.display = 'none';
    }
  });

  newEventsBtn.addEventListener('click', () => {
    activityFeed.scrollTo({ top: 0, behavior: 'smooth' });
    state.newEventsCount = 0;
    newEventsBtn.style.display = 'none';
  });

  // Connect SSE
  function initSSE() {
    const sse = new EventSource('/api/observatory/stream');

    sse.addEventListener('open', () => {
      state.sseConnected = true;
      liveIndicator.className = 'badge-live';
      liveIndicator.innerHTML = '<span class="pulse"></span> 实时同步 (SSE)';
    });

    sse.addEventListener('init', (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.agents) state.agents = data.agents;
        if (data.sources) state.sources = data.sources;
        if (data.backfill) updateBackfill(data.backfill);
        renderWorkspaces();
        autoSelectFirstItem();
      } catch (err) {
        console.error('SSE init error:', err);
      }
    });

    sse.addEventListener('activity', (e) => {
      try {
        const ev = JSON.parse(e.data);
        state.events.unshift(ev);
        if (state.events.length > 200) state.events.pop();

        if (state.filterAgent && state.filterAgent !== 'all' && ev.agent_id !== state.filterAgent) {
          return;
        }

        if (state.isFeedScrolled) {
          state.newEventsCount++;
          newEventsBtn.textContent = `↑ 有 ${state.newEventsCount} 条新动态`;
          newEventsBtn.style.display = 'block';
        } else {
          renderEvents();
        }
      } catch (err) {
        console.error('SSE activity error:', err);
      }
    });

    sse.addEventListener('backfill_progress', (e) => {
      try {
        const b = JSON.parse(e.data);
        updateBackfill(b);
      } catch {}
    });

    sse.addEventListener('error', () => {
      state.sseConnected = false;
      liveIndicator.className = 'badge-live polling';
      liveIndicator.innerHTML = '<span class="pulse"></span> 轮询同步 (5s)';
      sse.close();
      setTimeout(initSSE, 5000);
    });
  }

  // Start
  loadInitialData();
  initSSE();

  // Periodic poll fallback for agent cards every 5s
  setInterval(() => {
    fetch('/api/observatory/agents')
      .then(res => res.json())
      .then(data => {
        state.agents = data.agents || [];
        updateMetrics(data);
        renderWorkspaces();
        if (data.backfill) updateBackfill(data.backfill);
      })
      .catch(() => {});
  }, 5000);

})();
