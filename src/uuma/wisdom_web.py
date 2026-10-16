from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import quote


def _inline(text: str) -> str:
    escaped = html.escape(text)
    # Bold: **bold**
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    # Italic: *italic*
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
    # Citations or standard markdown links: [Title](URL)
    pattern = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")

    def _replace_link(match: re.Match) -> str:
        label = match.group(1)
        url = html.escape(match.group(2), quote=True)
        # If label is like S1, S2, format as citation pill
        if re.match(r"^S\d+$", label):
            return f'<a href="{url}" target="_blank" rel="noreferrer" class="citation-pill" title="查看来源文献">{label}</a>'
        return f'<a href="{url}" target="_blank" rel="noreferrer">{label}</a>'

    escaped = pattern.sub(_replace_link, escaped)

    # Stylize mechanical prefixes if present
    if escaped.startswith("资料支持："):
        escaped = '<span class="badge badge-evidence">实证依据</span> ' + escaped[5:]
    elif escaped.startswith("暂定解释："):
        escaped = '<span class="badge badge-inference">推论分析</span> ' + escaped[5:]
    elif escaped.startswith("来源范围："):
        escaped = '<span class="badge badge-scope">来源范围</span> ' + escaped[5:]

    return escaped


def markdown_to_html(markdown: str) -> str:
    output: list[str] = []
    in_list = False
    in_callout = False

    def close_list():
        nonlocal in_list
        if in_list:
            output.append("</ul>")
            in_list = False

    def close_callout():
        nonlocal in_callout
        if in_callout:
            output.append("</div>")
            in_callout = False

    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("<a id=\"") and line.endswith("</a>"):
            anchor = re.sub(r"[^a-zA-Z0-9_-]", "", line[7:-6])
            output.append(f'<span id="{anchor}"></span>')
            continue

        if line.startswith("- "):
            if not in_list:
                output.append('<ul class="doc-list">')
                in_list = True
            output.append(f"<li>{_inline(line[2:])}</li>")
            continue

        close_list()

        if not line:
            continue

        if line.startswith("# "):
            close_callout()
            output.append(f'<h1 class="doc-title">{_inline(line[2:])}</h1>')
        elif line.startswith("## "):
            close_callout()
            title = line[3:]
            if title in ("未解决问题", "研究状态"):
                box_cls = "callout-gaps" if title == "未解决问题" else "callout-status"
                output.append(f'<div class="callout-box {box_cls}"><h2 class="section-title">{_inline(title)}</h2>')
                in_callout = True
            else:
                output.append(f'<h2 class="section-title">{_inline(title)}</h2>')
        elif line.startswith("### "):
            close_callout()
            subtitle = line[4:]
            callout_class = "callout-conditions" if "适用条件" in subtitle else (
                "callout-sources" if "来源" in subtitle else (
                    "callout-conflicts" if "证据与争议" in subtitle else "callout-research"
                )
            )
            output.append(f'<div class="callout-box {callout_class}"><h3 class="subsection-title">{_inline(subtitle)}</h3>')
            in_callout = True
        elif line.startswith("> "):
            output.append(f'<blockquote class="doc-quote">{_inline(line[2:])}</blockquote>')
        else:
            output.append(f"<p>{_inline(line)}</p>")

    close_list()
    close_callout()
    return "\n".join(output)


def render_topic_page(data: dict[str, Any], token: str) -> str:
    topic = data["topic"]
    latest = data.get("latest_version")
    current_orbit = next(iter(data.get("orbits") or []), None)
    if current_orbit:
        live_status = html.escape(str(current_orbit["status"]))
        live_updated = html.escape(str(current_orbit.get("updated_at") or ""))
        live_reason = current_orbit.get("stop_reason")
        status_panel = (
            '<section class="card status-card" aria-label="当前研究状态">'
            '<div class="status-header">'
            '<span class="status-indicator"></span>'
            f'<strong>当前研究状态：{live_status}</strong>'
            '</div>'
            f'<p class="muted">状态更新时间：{live_updated}。正文记录的是发布时的状态。</p>'
            + (f'<p>原因：{html.escape(str(live_reason))}</p>' if live_reason else "")
            + '</section>'
        )
    else:
        status_panel = ""

    body = latest["body_markdown"] if latest else (
        f"# {topic['title']}\n\n主题已经建立，研究成果尚未发布。"
    )
    sections = latest.get("sections", []) if latest else []
    toc = "".join(
        f'<li><a href="#{html.escape(item["anchor"], quote=True)}">'
        f'<span class="toc-bullet"></span>{html.escape(item["title"])}</a></li>'
        for item in sections
    )
    changes = "".join(
        '<li class="version-item">'
        f'<span class="version-badge">v{item["version"]}</span> '
        f'<span class="muted font-mono">{html.escape(item["created_at"][:19].replace("T", " "))}</span><br>'
        f'<span class="version-summary">{html.escape(item["change_summary"])}</span>'
        '</li>'
        for item in data.get("versions", [])[:20]
    )
    graph_url = f"/wisdom/api/topics/{quote(topic['topic_id'])}/graph?token={quote(token)}"
    topic_index_url = f"/wisdom/topics?token={quote(token, safe='')}"
    safe_title = html.escape(topic["title"])

    return f"""<!doctype html>
<html lang="zh-Hans">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_title} · Wisdom-Oldman 知识中心</title>
<style>
:root {{
  color-scheme: light;
  --bg: #f8fafc;
  --panel: #ffffff;
  --panel-hover: #f1f5f9;
  --ink: #0f172a;
  --ink-secondary: #334155;
  --muted: #64748b;
  --line: #e2e8f0;
  --line-strong: #cbd5e1;
  
  --topic-blue: #2563eb;
  --topic-blue-bg: #eff6ff;
  --question-green: #16a34a;
  --question-green-bg: #f0fdf4;
  --evidence-orange: #ea580c;
  --evidence-orange-bg: #fff7ed;
  --gap-red: #dc2626;
  --gap-red-bg: #fef2f2;
  --accent: #0f766e;
  --accent-light: #f0fdfa;
  
  --shadow-sm: 0 1px 3px rgba(15,23,42,0.06);
  --shadow-md: 0 4px 16px -2px rgba(15,23,42,0.08);
  --shadow-lg: 0 10px 25px -4px rgba(15,23,42,0.1);
  --radius: 12px;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 15px/1.75 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
  -webkit-font-smoothing: antialiased;
}}
.shell {{
  max-width: 1280px;
  margin: 0 auto;
  padding: 24px 20px;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 28px;
}}
aside {{ position: sticky; top: 20px; align-self: start; display: flex; flex-direction: column; gap: 16px; }}
main {{ min-width: 0; }}

.card {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 22px;
  box-shadow: var(--shadow-sm);
  transition: box-shadow 0.2s ease;
}}
.card:hover {{ box-shadow: var(--shadow-md); }}

.back-link {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  color: var(--muted);
  text-decoration: none;
  font-weight: 500;
  font-size: 0.9rem;
  transition: all 0.15s ease;
}}
.back-link:hover {{ color: var(--ink); border-color: var(--line-strong); background: #fff; }}

.topic-header-card h2 {{
  font-size: 1.15rem;
  margin: 0 0 6px 0;
  line-height: 1.4;
  color: var(--ink);
}}
.sub-badge {{
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--accent-light);
  color: var(--accent);
  font-size: 0.78rem;
  font-weight: 600;
  margin-bottom: 14px;
}}

/* Segmented mode switcher */
.mode-switcher {{
  display: flex;
  background: #f1f5f9;
  padding: 4px;
  border-radius: 10px;
  gap: 4px;
}}
.mode-btn {{
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: none;
  background: transparent;
  color: var(--muted);
  font-weight: 600;
  font-size: 0.88rem;
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}}
.mode-btn:hover {{ color: var(--ink); }}
.mode-btn.active {{
  background: var(--panel);
  color: var(--topic-blue);
  box-shadow: 0 2px 6px rgba(0,0,0,0.06);
}}

/* Sidebar navigation */
.sidebar-section-title {{
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
  font-weight: 700;
  margin: 0 0 10px 0;
}}
.toc-list, .version-list {{
  list-style: none;
  padding: 0;
  margin: 0;
  max-height: 380px;
  overflow-y: auto;
  font-size: 0.88rem;
}}
.toc-list li {{ margin-bottom: 6px; }}
.toc-list a {{
  display: flex;
  align-items: flex-start;
  gap: 8px;
  color: var(--ink-secondary);
  text-decoration: none;
  padding: 5px 8px;
  border-radius: 6px;
  transition: all 0.12s ease;
  line-height: 1.4;
}}
.toc-list a:hover {{ background: #f1f5f9; color: var(--topic-blue); }}
.toc-bullet {{
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--line-strong);
  margin-top: 6px;
  flex-shrink: 0;
}}
.version-item {{
  padding: 8px 0;
  border-bottom: 1px dashed var(--line);
}}
.version-item:last-child {{ border-bottom: none; }}
.version-badge {{
  display: inline-block;
  background: #e2e8f0;
  color: #334155;
  font-size: 0.75rem;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
}}
.version-summary {{
  display: block;
  font-size: 0.82rem;
  color: var(--muted);
  margin-top: 2px;
}}

/* Document article styling */
#document {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 36px 42px;
  box-shadow: var(--shadow-sm);
}}
.anchor-target {{ scroll-margin-top: 30px; display: block; }}
.doc-title {{
  font-size: 1.85rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  margin: 0 0 16px 0;
  color: var(--ink);
  line-height: 1.3;
}}
.section-title {{
  font-size: 1.35rem;
  font-weight: 700;
  margin: 2.4rem 0 1rem 0;
  padding-bottom: 8px;
  border-bottom: 2px solid #f1f5f9;
  color: var(--ink);
  display: flex;
  align-items: center;
  gap: 8px;
}}
.subsection-title {{
  font-size: 1.05rem;
  font-weight: 600;
  margin: 1.4rem 0 0.6rem 0;
  color: var(--ink-secondary);
}}
.doc-list {{ padding-left: 1.4rem; margin: 0.8rem 0; }}
.doc-list li {{ margin-bottom: 0.45rem; }}
p {{ margin: 0.85rem 0; line-height: 1.8; }}

/* Status card */
.status-card {{
  border-left: 4px solid var(--accent);
  background: var(--accent-light);
  margin-bottom: 24px;
}}
.status-header {{
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--accent);
  font-size: 1rem;
}}
.status-indicator {{
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 0 3px rgba(15,118,110,0.2);
}}

/* Callout boxes */
.callout-box {{
  border-radius: 8px;
  padding: 16px 18px;
  margin: 18px 0;
  border: 1px solid transparent;
}}
.callout-conditions {{
  background: #f8fafc;
  border-color: #cbd5e1;
}}
.callout-sources {{
  background: #f0fdf4;
  border-color: #bbf7d0;
}}
.callout-conflicts {{
  background: #fffbeb;
  border-color: #fde68a;
}}
.callout-gaps {{
  background: var(--gap-red-bg);
  border-color: #fecaca;
}}
.callout-status {{
  background: #f8fafc;
  border-color: var(--line);
}}

/* Badges & citation pills */
.badge {{
  display: inline-block;
  padding: 2px 7px;
  border-radius: 4px;
  font-size: 0.76rem;
  font-weight: 700;
  margin-right: 4px;
  vertical-align: 1px;
}}
.badge-evidence {{ background: #dcfce7; color: #166534; }}
.badge-inference {{ background: #eff6ff; color: #1e40af; }}
.badge-scope {{ background: #fef3c7; color: #92400e; }}
.badge-gap {{ background: #fee2e2; color: #991b1b; }}

.citation-pill {{
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  background: #f1f5f9;
  border: 1px solid #cbd5e1;
  color: var(--topic-blue);
  border-radius: 4px;
  text-decoration: none;
  font-weight: 600;
  font-size: 0.78rem;
  margin: 0 2px;
  transition: all 0.12s ease;
}}
.citation-pill:hover {{
  background: var(--topic-blue);
  color: #fff;
  border-color: var(--topic-blue);
}}

/* Graph View Container & Controls */
#graph-container {{
  display: none;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  position: relative;
}}
.graph-toolbar {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px;
  background: #f8fafc;
  border-bottom: 1px solid var(--line);
  flex-wrap: wrap;
  gap: 10px;
}}
.graph-filters {{
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}}
.filter-chip {{
  border: 1px solid var(--line-strong);
  background: #fff;
  color: var(--ink-secondary);
  font-size: 0.8rem;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 20px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  transition: all 0.15s ease;
}}
.filter-chip:hover {{ background: #f1f5f9; }}
.filter-chip.active {{
  background: var(--ink);
  color: #fff;
  border-color: var(--ink);
}}
.filter-chip[data-kind="topic"].active {{ background: var(--topic-blue); border-color: var(--topic-blue); }}
.filter-chip[data-kind="question"].active {{ background: var(--question-green); border-color: var(--question-green); }}
.filter-chip[data-kind="source"].active {{ background: var(--evidence-orange); border-color: var(--evidence-orange); }}
.filter-chip[data-kind="gap"].active {{ background: var(--gap-red); border-color: var(--gap-red); }}

.dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}
.dot-topic {{ background: var(--topic-blue); }}
.dot-question {{ background: var(--question-green); }}
.dot-source {{ background: var(--evidence-orange); }}
.dot-gap {{ background: var(--gap-red); }}

.graph-actions {{
  display: flex;
  align-items: center;
  gap: 6px;
}}
.graph-btn {{
  border: 1px solid var(--line);
  background: #fff;
  color: var(--ink);
  font-size: 0.82rem;
  font-weight: 600;
  padding: 5px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}}
.graph-btn:hover {{ background: #f1f5f9; border-color: var(--line-strong); }}

/* Canvas layout */
.canvas-wrap {{
  position: relative;
  width: 100%;
  height: 660px;
  background: radial-gradient(#e2e8f0 1px, transparent 1px);
  background-size: 20px 20px;
  background-color: #fafbfc;
  cursor: grab;
}}
.canvas-wrap:active {{ cursor: grabbing; }}
canvas#graph-canvas {{
  display: block;
  width: 100%;
  height: 100%;
}}

/* Graph Inspector Card (Slide-out or Float) */
.graph-inspector {{
  position: absolute;
  right: 16px;
  top: 16px;
  width: 320px;
  max-width: 90%;
  max-height: calc(100% - 32px);
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(8px);
  border: 1px solid var(--line);
  border-radius: 10px;
  box-shadow: var(--shadow-lg);
  padding: 18px;
  overflow-y: auto;
  display: none;
  z-index: 10;
  transition: opacity 0.2s ease;
}}
.inspector-close {{
  position: absolute;
  right: 12px;
  top: 12px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 1.1rem;
  color: var(--muted);
}}
.inspector-badge {{
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 700;
  color: #fff;
  margin-bottom: 8px;
}}
.inspector-title {{
  font-size: 1rem;
  font-weight: 700;
  margin: 0 0 10px 0;
  line-height: 1.4;
  color: var(--ink);
}}
.inspector-body {{
  font-size: 0.85rem;
  color: var(--ink-secondary);
  line-height: 1.6;
  margin-bottom: 12px;
  white-space: pre-wrap;
}}
.inspector-action {{
  display: block;
  width: 100%;
  padding: 8px 12px;
  text-align: center;
  background: var(--topic-blue);
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
}}
.inspector-action:hover {{ background: #1d4ed8; }}

@media(max-width: 860px) {{
  .shell {{ grid-template-columns: 1fr; }}
  aside {{ position: static; }}
  #document {{ padding: 22px 18px; }}
  .canvas-wrap {{ height: 500px; }}
}}
</style>
</head>
<body>
<div class="shell">
<aside>
  <a class="back-link" href="{html.escape(topic_index_url, quote=True)}">← 全部主题列表</a>
  
  <div class="card topic-header-card">
    <span class="sub-badge">Wisdom-Oldman 主题知识</span>
    <h2>{safe_title}</h2>
    
    <div class="mode-switcher" style="margin-top: 14px;">
      <button id="show-doc" class="mode-btn active">📄 知识文档</button>
      <button id="show-graph" class="mode-btn">🕸️ 关系图谱</button>
    </div>
  </div>

  <div class="card" id="sidebar-toc">
    <h3 class="sidebar-section-title">文档章节导航</h3>
    <ul class="toc-list">{toc or '<li>等待首个章节</li>'}</ul>
  </div>

  <div class="card">
    <h3 class="sidebar-section-title">版本演进历史</h3>
    <ul class="version-list">{changes or '<li>尚无版本记录</li>'}</ul>
  </div>
</aside>

<main>
  {status_panel}
  
  <article id="document">
    {markdown_to_html(body)}
  </article>

  <section id="graph-container">
    <div class="graph-toolbar">
      <div class="graph-filters">
        <span style="font-size:0.85rem;font-weight:700;color:var(--muted);margin-right:4px;">图层筛选：</span>
        <button class="filter-chip active" data-kind="all">全部</button>
        <button class="filter-chip active" data-kind="topic"><span class="dot dot-topic"></span>主题 (Topic)</button>
        <button class="filter-chip active" data-kind="question"><span class="dot dot-question"></span>研究问题 (Question)</button>
        <button class="filter-chip active" data-kind="source"><span class="dot dot-source"></span>证据与来源 (Evidence/Source)</button>
        <button class="filter-chip active" data-kind="gap"><span class="dot dot-gap"></span>待证缺口 (Gap)</button>
      </div>
      <div class="graph-actions">
        <button class="graph-btn" id="btn-zoom-in" title="放大">➕</button>
        <button class="graph-btn" id="btn-zoom-out" title="缩小">➖</button>
        <button class="graph-btn" id="btn-zoom-reset" title="复位视角">⟲ 居中</button>
      </div>
    </div>
    
    <div class="canvas-wrap" id="canvas-wrap">
      <canvas id="graph-canvas"></canvas>
      
      <div class="graph-inspector" id="graph-inspector">
        <button class="inspector-close" id="inspector-close">×</button>
        <span class="inspector-badge" id="inspector-badge">节点详情</span>
        <h4 class="inspector-title" id="inspector-title"></h4>
        <div class="inspector-body" id="inspector-body"></div>
        <a href="#" class="inspector-action" id="inspector-action" style="display:none;">📖 查看对应正文章节</a>
      </div>
    </div>
  </section>
</main>
</div>

<script>
// Tab Switching
const docEl = document.getElementById('document');
const graphContainer = document.getElementById('graph-container');
const docBtn = document.getElementById('show-doc');
const graphBtn = document.getElementById('show-graph');
const tocCard = document.getElementById('sidebar-toc');

function showDocument() {{
  docEl.style.display = 'block';
  graphContainer.style.display = 'none';
  docBtn.classList.add('active');
  graphBtn.classList.remove('active');
  if(tocCard) tocCard.style.display = 'block';
}}

function showGraph() {{
  docEl.style.display = 'none';
  graphContainer.style.display = 'block';
  docBtn.classList.remove('active');
  graphBtn.classList.add('active');
  if (!window._graphInitialized) {{
    initGraph();
  }}
}}

docBtn.addEventListener('click', showDocument);
graphBtn.addEventListener('click', showGraph);
document.querySelectorAll('aside a[href^="#"]').forEach(link => {{
  link.addEventListener('click', () => showDocument());
}});
window.addEventListener('hashchange', () => {{
  if (location.hash) showDocument();
}});

// Interactive Force-Directed Knowledge Graph Engine (Vanilla JS, 0 dependencies)
let graphData = null;
const COLOR_MAP = {{
  'topic': {{ fill: '#3b82f6', stroke: '#1d4ed8', text: '#1e3a8a', label: '主题 Topic', r: 24 }},
  'question': {{ fill: '#22c55e', stroke: '#15803d', text: '#14532d', label: '问题 Question', r: 17 }},
  'source': {{ fill: '#f97316', stroke: '#c2410c', text: '#7c2d12', label: '来源 Source', r: 13 }},
  'evidence': {{ fill: '#f97316', stroke: '#c2410c', text: '#7c2d12', label: '证据 Evidence', r: 13 }},
  'claim': {{ fill: '#ea580c', stroke: '#9a3412', text: '#7c2d12', label: '断言 Claim', r: 13 }},
  'gap': {{ fill: '#ef4444', stroke: '#b91c1c', text: '#7f1d1d', label: '待证缺口 Gap', r: 13 }},
  'other': {{ fill: '#8b5cf6', stroke: '#6d28d9', text: '#4c1d95', label: '知识节点', r: 13 }}
}};

function getNodeKind(kind) {{
  if (kind === 'topic') return 'topic';
  if (kind === 'question') return 'question';
  if (kind === 'gap') return 'gap';
  if (['source', 'evidence', 'claim'].includes(kind)) return 'source';
  return 'other';
}}

async function initGraph() {{
  window._graphInitialized = true;
  const canvas = document.getElementById('graph-canvas');
  const wrap = document.getElementById('canvas-wrap');
  const ctx = canvas.getContext('2d');
  
  // Resize canvas for crisp rendering on high-DPI displays
  function resize() {{
    const rect = wrap.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
  }}
  resize();
  window.addEventListener('resize', resize);

  // Fetch graph data
  try {{
    const resp = await fetch({json.dumps(graph_url)});
    graphData = await resp.json();
  }} catch (e) {{
    console.error('Failed to load graph data', e);
    return;
  }}

  const nodes = graphData.nodes.map((n, i) => {{
    const group = getNodeKind(n.kind);
    const style = COLOR_MAP[group] || COLOR_MAP.other;
    return {{
      id: n.id,
      kind: n.kind,
      group: group,
      label: n.label,
      radius: style.r,
      fill: style.fill,
      stroke: style.stroke,
      x: (wrap.clientWidth / 2) + (Math.random() - 0.5) * 300,
      y: (wrap.clientHeight / 2) + (Math.random() - 0.5) * 300,
      vx: 0,
      vy: 0,
      visible: true
    }};
  }});

  const nodeMap = new Map(nodes.map(n => [n.id, n]));
  const edges = graphData.edges
    .filter(e => nodeMap.has(e.source) && nodeMap.has(e.target))
    .map(e => ({{
      source: nodeMap.get(e.source),
      target: nodeMap.get(e.target),
      kind: e.kind
    }}));

  // Camera & Interaction State
  let camera = {{ x: wrap.clientWidth / 2, y: wrap.clientHeight / 2, zoom: 1 }};
  let isPanning = false;
  let panStart = {{ x: 0, y: 0 }};
  let draggedNode = null;
  let hoveredNode = null;
  let selectedNode = null;
  let simulationActive = true;
  let animFrame = null;

  // Filter handlers
  const filterChips = document.querySelectorAll('.filter-chip');
  filterChips.forEach(chip => {{
    chip.addEventListener('click', () => {{
      const kind = chip.dataset.kind;
      if (kind === 'all') {{
        const wasAllActive = chip.classList.contains('active');
        filterChips.forEach(c => c.classList.toggle('active', !wasAllActive));
      }} else {{
        chip.classList.toggle('active');
      }}
      
      const activeKinds = new Set();
      filterChips.forEach(c => {{
        if (c.classList.contains('active') && c.dataset.kind !== 'all') {{
          activeKinds.add(c.dataset.kind);
        }}
      }});
      
      nodes.forEach(n => {{
        n.visible = activeKinds.has(n.group);
      }});
      simulationActive = true;
      requestDraw();
    }});
  }});

  // Zoom buttons
  document.getElementById('btn-zoom-in').onclick = () => {{ camera.zoom = Math.min(camera.zoom * 1.25, 3.5); requestDraw(); }};
  document.getElementById('btn-zoom-out').onclick = () => {{ camera.zoom = Math.max(camera.zoom / 1.25, 0.25); requestDraw(); }};
  document.getElementById('btn-zoom-reset').onclick = () => {{
    camera.zoom = 1;
    camera.x = wrap.clientWidth / 2;
    camera.y = wrap.clientHeight / 2;
    simulationActive = true;
    requestDraw();
  }};

  // Inspector handlers
  const inspector = document.getElementById('graph-inspector');
  const inspectorClose = document.getElementById('inspector-close');
  const inspectorBadge = document.getElementById('inspector-badge');
  const inspectorTitle = document.getElementById('inspector-title');
  const inspectorBody = document.getElementById('inspector-body');
  const inspectorAction = document.getElementById('inspector-action');

  inspectorClose.onclick = () => {{
    inspector.style.display = 'none';
    selectedNode = null;
    requestDraw();
  }};

  function selectNode(n) {{
    selectedNode = n;
    if (!n) {{
      inspector.style.display = 'none';
      return;
    }}
    const cfg = COLOR_MAP[n.group] || COLOR_MAP.other;
    inspectorBadge.style.background = cfg.stroke;
    inspectorBadge.textContent = cfg.label;
    inspectorTitle.textContent = n.label;
    
    // Connected edges info
    const connected = edges.filter(e => e.source === n || e.target === n);
    let relText = '关联关系：\\n';
    connected.forEach(e => {{
      const other = e.source === n ? e.target : e.source;
      const arrow = e.source === n ? '→' : '←';
      relText += `• [${{e.kind}}] ${{arrow}} ${{other.label.slice(0, 36)}}...\\n`;
    }});
    inspectorBody.textContent = relText || '暂无直接关联关系。';

    // Link to document section if applicable
    let anchor = null;
    if (n.kind === 'topic') {{
      anchor = 'overview';
    }} else if (n.kind === 'question') {{
      anchor = 'question-' + n.id.replace('question_', '').slice(0, 12);
    }}
    
    if (anchor && document.getElementById(anchor)) {{
      inspectorAction.style.display = 'block';
      inspectorAction.onclick = (e) => {{
        e.preventDefault();
        showDocument();
        const target = document.getElementById(anchor);
        if (target) target.scrollIntoView({{ behavior: 'smooth' }});
      }};
    }} else {{
      inspectorAction.style.display = 'none';
    }}

    inspector.style.display = 'block';
    requestDraw();
  }}

  // Physics Step
  function stepPhysics() {{
    const kRepel = 2400;
    const kSpring = 0.045;
    const l0 = 95;
    const centerPull = 0.008;
    const cx = wrap.clientWidth / 2;
    const cy = wrap.clientHeight / 2;

    // Repulsion
    for (let i = 0; i < nodes.length; i++) {{
      const n1 = nodes[i];
      if (!n1.visible) continue;
      
      // Pull to center
      n1.vx += (cx - n1.x) * centerPull;
      n1.vy += (cy - n1.y) * centerPull;

      for (let j = i + 1; j < nodes.length; j++) {{
        const n2 = nodes[j];
        if (!n2.visible) continue;
        const dx = n2.x - n1.x;
        const dy = n2.y - n1.y;
        const distSq = dx * dx + dy * dy + 1;
        const dist = Math.sqrt(distSq);
        const force = kRepel / (distSq * 0.85);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        n1.vx -= fx;
        n1.vy -= fy;
        n2.vx += fx;
        n2.vy += fy;
      }}
    }}

    // Springs
    for (const e of edges) {{
      if (!e.source.visible || !e.target.visible) continue;
      const dx = e.target.x - e.source.x;
      const dy = e.target.y - e.source.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const force = (dist - l0) * kSpring;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      e.source.vx += fx;
      e.source.vy += fy;
      e.target.vx -= fx;
      e.target.vy -= fy;
    }}

    // Update positions
    let totalEnergy = 0;
    for (const n of nodes) {{
      if (!n.visible || n === draggedNode) continue;
      n.vx *= 0.82;
      n.vy *= 0.82;
      n.x += n.vx;
      n.y += n.vy;
      totalEnergy += Math.abs(n.vx) + Math.abs(n.vy);
    }}

    if (totalEnergy < 0.2 && !draggedNode) {{
      simulationActive = false;
    }}
  }}

  // Draw Function
  function draw() {{
    const w = wrap.clientWidth;
    const h = wrap.clientHeight;
    ctx.clearRect(0, 0, w, h);

    ctx.save();
    ctx.translate(camera.x, camera.y);
    ctx.scale(camera.zoom, camera.zoom);
    ctx.translate(-w / 2, -h / 2);

    // Draw Edges
    for (const e of edges) {{
      if (!e.source.visible || !e.target.visible) continue;
      ctx.beginPath();
      ctx.moveTo(e.source.x, e.source.y);
      ctx.lineTo(e.target.x, e.target.y);
      
      const isHighlighted = (hoveredNode && (e.source === hoveredNode || e.target === hoveredNode)) ||
                            (selectedNode && (e.source === selectedNode || e.target === selectedNode));
      
      if (isHighlighted) {{
        ctx.strokeStyle = '#0f172a';
        ctx.lineWidth = 2.4;
      }} else {{
        ctx.strokeStyle = e.kind === 'GAP' ? 'rgba(239, 68, 68, 0.45)' : 'rgba(203, 213, 225, 0.75)';
        ctx.lineWidth = 1.3;
      }}
      if (e.kind === 'GAP') {{
        ctx.setLineDash([4, 4]);
      }} else {{
        ctx.setLineDash([]);
      }}
      ctx.stroke();
    }}
    ctx.setLineDash([]);

    // Draw Nodes
    for (const n of nodes) {{
      if (!n.visible) continue;
      const isHover = n === hoveredNode;
      const isSelected = n === selectedNode;

      // Outer glow for selected/hovered
      if (isSelected || isHover) {{
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.radius + 6, 0, Math.PI * 2);
        ctx.fillStyle = isSelected ? 'rgba(37, 99, 235, 0.25)' : 'rgba(15, 23, 42, 0.12)';
        ctx.fill();
      }}

      // Circle
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);
      ctx.fillStyle = n.fill;
      ctx.fill();
      ctx.strokeStyle = isSelected ? '#0f172a' : n.stroke;
      ctx.lineWidth = isSelected ? 3 : 2;
      ctx.stroke();

      // Label text
      ctx.fillStyle = '#0f172a';
      ctx.font = (n.group === 'topic' ? 'bold 13px ' : '11px ') + '-apple-system, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      
      let label = n.label;
      if (label.length > 18) label = label.slice(0, 16) + '…';
      ctx.fillText(label, n.x, n.y + n.radius + 4);
    }}

    ctx.restore();
  }}

  function loop() {{
    if (simulationActive || draggedNode) {{
      stepPhysics();
    }}
    draw();
    animFrame = requestAnimationFrame(loop);
  }}
  animFrame = requestAnimationFrame(loop);

  function requestDraw() {{
    if (!simulationActive) {{
      draw();
    }}
  }}

  // Coordinate transforms
  function screenToWorld(sx, sy) {{
    const w = wrap.clientWidth;
    const h = wrap.clientHeight;
    return {{
      x: (sx - camera.x) / camera.zoom + (w / 2),
      y: (sy - camera.y) / camera.zoom + (h / 2)
    }};
  }}

  function findNodeAt(sx, sy) {{
    const pos = screenToWorld(sx, sy);
    for (let i = nodes.length - 1; i >= 0; i--) {{
      const n = nodes[i];
      if (!n.visible) continue;
      const dx = pos.x - n.x;
      const dy = pos.y - n.y;
      if (dx * dx + dy * dy <= (n.radius + 4) * (n.radius + 4)) {{
        return n;
      }}
    }}
    return null;
  }}

  // Mouse & Drag Events
  wrap.addEventListener('mousedown', (e) => {{
    if (e.target !== canvas) return;
    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;
    
    const node = findNodeAt(sx, sy);
    if (node) {{
      draggedNode = node;
      selectNode(node);
      simulationActive = true;
    }} else {{
      isPanning = true;
      panStart = {{ x: e.clientX - camera.x, y: e.clientY - camera.y }};
    }}
  }});

  window.addEventListener('mousemove', (e) => {{
    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    if (draggedNode) {{
      const world = screenToWorld(sx, sy);
      draggedNode.x = world.x;
      draggedNode.y = world.y;
      draggedNode.vx = 0;
      draggedNode.vy = 0;
      simulationActive = true;
    }} else if (isPanning) {{
      camera.x = e.clientX - panStart.x;
      camera.y = e.clientY - panStart.y;
      requestDraw();
    }} else {{
      const node = findNodeAt(sx, sy);
      if (node !== hoveredNode) {{
        hoveredNode = node;
        wrap.style.cursor = node ? 'pointer' : 'grab';
        requestDraw();
      }}
    }}
  }});

  window.addEventListener('mouseup', () => {{
    draggedNode = null;
    isPanning = false;
  }});

  // Wheel Zoom
  wrap.addEventListener('wheel', (e) => {{
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.12 : 0.89;
    camera.zoom = Math.min(Math.max(camera.zoom * factor, 0.2), 4.0);
    simulationActive = true;
    requestDraw();
  }}, {{ passive: false }});
}}
</script>
</body>
</html>"""


def render_topic_index(records: list[dict[str, Any]], token: str) -> str:
    items = "".join(
        f'<li style="margin-bottom:12px;"><a style="color:#2563eb;text-decoration:none;font-weight:600;" href="/wisdom/topics/{quote(item["topic_id"])}?token={quote(token)}">'
        f'{html.escape(item["title"])}</a></li>'
        for item in records
    )
    return (
        "<!doctype html><html lang='zh-Hans'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Wisdom-Oldman 主题知识文档库</title></head>"
        "<body style='max-width:860px;margin:40px auto;padding:0 20px;font:16px/1.75 system-ui'>"
        "<h1 style='font-size:1.8rem;border-bottom:2px solid #e2e8f0;padding-bottom:12px;'>Wisdom-Oldman 主题知识文档库</h1>"
        f"<ul style='padding-left:1.25rem;'>{items or '<li>尚无主题</li>'}</ul></body></html>"
    )
