from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import quote


def _inline(text: str) -> str:
    escaped = html.escape(text)
    pattern = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
    return pattern.sub(
        lambda match: (
            f'<a href="{html.escape(match.group(2), quote=True)}" '
            f'target="_blank" rel="noreferrer">{match.group(1)}</a>'
        ),
        escaped,
    )


def markdown_to_html(markdown: str) -> str:
    output: list[str] = []
    in_list = False
    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("<a id=\"") and line.endswith("</a>"):
            anchor = re.sub(r"[^a-zA-Z0-9_-]", "", line[7:-6])
            output.append(f'<span id="{anchor}"></span>')
            continue
        if line.startswith("- "):
            if not in_list:
                output.append("<ul>")
                in_list = True
            output.append(f"<li>{_inline(line[2:])}</li>")
            continue
        if in_list:
            output.append("</ul>")
            in_list = False
        if not line:
            continue
        if line.startswith("# "):
            output.append(f"<h1>{_inline(line[2:])}</h1>")
        elif line.startswith("## "):
            output.append(f"<h2>{_inline(line[3:])}</h2>")
        elif line.startswith("### "):
            output.append(f"<h3>{_inline(line[4:])}</h3>")
        else:
            output.append(f"<p>{_inline(line)}</p>")
    if in_list:
        output.append("</ul>")
    return "\n".join(output)


def render_topic_page(data: dict[str, Any], token: str) -> str:
    topic = data["topic"]
    latest = data.get("latest_version")
    body = latest["body_markdown"] if latest else (
        f"# {topic['title']}\n\n主题已经建立，研究成果尚未发布。"
    )
    sections = latest.get("sections", []) if latest else []
    toc = "".join(
        f'<li><a href="#{html.escape(item["anchor"], quote=True)}">'
        f'{html.escape(item["title"])}</a></li>'
        for item in sections
    )
    changes = "".join(
        "<li>"
        f"v{item['version']} · {html.escape(item['created_at'])}<br>"
        f"{html.escape(item['change_summary'])}"
        "</li>"
        for item in data.get("versions", [])[:20]
    )
    graph_url = (
        f"/wisdom/api/topics/{quote(topic['topic_id'])}/graph?token={quote(token)}"
    )
    safe_title = html.escape(topic["title"])
    return f"""<!doctype html>
<html lang="zh-Hans">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_title} · Wisdom-Oldman</title>
<style>
:root {{ color-scheme: light; --ink:#243028; --muted:#68736c; --paper:#fbfaf5;
--panel:#fff; --accent:#2f6d4f; --line:#dce3dc; }}
* {{ box-sizing:border-box }} body {{ margin:0; background:var(--paper); color:var(--ink);
font:16px/1.72 system-ui,"Segoe UI",sans-serif }}
.shell {{ max-width:1180px; margin:auto; padding:28px; display:grid;
grid-template-columns:250px minmax(0,1fr); gap:34px }}
aside {{ position:sticky; top:20px; align-self:start }} main {{ min-width:0 }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:14px;
padding:20px; margin-bottom:20px; box-shadow:0 7px 24px #173c2410 }}
h1,h2,h3 {{ line-height:1.25 }} h2 {{ margin-top:2.2rem; border-bottom:1px solid var(--line);
padding-bottom:.45rem }} a {{ color:var(--accent) }} .muted {{ color:var(--muted) }}
[id="overview"] {{ scroll-margin-top:24px }}
button {{ border:1px solid var(--accent); background:white; color:var(--accent); padding:9px 13px;
border-radius:9px; cursor:pointer; margin-right:8px }} button.active {{ color:white;background:var(--accent) }}
#graph {{ display:none }} .node {{ border-left:4px solid var(--accent); padding:10px 12px;
margin:8px 0; background:#f6faf7 }} .edge {{ color:var(--muted); font-size:.92rem }}
ul {{ padding-left:1.25rem }} @media(max-width:800px) {{ .shell {{ grid-template-columns:1fr }}
aside {{ position:static }} }}
</style>
</head>
<body><div class="shell">
<aside>
  <div class="card"><strong>{safe_title}</strong>
  <p class="muted">长期主题知识文档</p>
  <button id="show-doc" class="active">文档</button><button id="show-graph">关系图谱</button></div>
  <div class="card"><strong>目录</strong><ul>{toc or '<li>等待首个章节</li>'}</ul></div>
  <div class="card"><strong>版本记录</strong><ul>{changes or '<li>尚无版本</li>'}</ul></div>
</aside>
<main>
  <article id="document" class="card">{markdown_to_html(body)}</article>
  <section id="graph" class="card"><h1>相关知识</h1><p class="muted">正在读取……</p></section>
</main></div>
<script>
const doc=document.getElementById('document'), graph=document.getElementById('graph');
const docButton=document.getElementById('show-doc'), graphButton=document.getElementById('show-graph');
docButton.onclick=()=>{{doc.style.display='block';graph.style.display='none';docButton.className='active';graphButton.className=''}};
document.querySelectorAll('aside a[href^="#"]').forEach(link=>{{link.addEventListener('click',()=>{{docButton.click();}})}});
window.addEventListener('hashchange',()=>{{if(location.hash)docButton.click();}});
graphButton.onclick=async()=>{{doc.style.display='none';graph.style.display='block';docButton.className='';graphButton.className='active';
if(graph.dataset.loaded)return; const response=await fetch({json.dumps(graph_url)}); const data=await response.json();
graph.innerHTML='<h1>相关知识</h1>' + data.nodes.map(n=>`<div class="node"><strong>${{escapeHtml(n.label)}}</strong><br><span class="muted">${{escapeHtml(n.kind)}}</span></div>`).join('') + '<h2>关系</h2>' + data.edges.map(e=>`<div class="edge">${{escapeHtml(e.source)}} → ${{escapeHtml(e.kind)}} → ${{escapeHtml(e.target)}}</div>`).join(''); graph.dataset.loaded='1';}};
function escapeHtml(value){{const div=document.createElement('div');div.textContent=String(value);return div.innerHTML}}
</script></body></html>"""


def render_topic_index(records: list[dict[str, Any]], token: str) -> str:
    items = "".join(
        f'<li><a href="/wisdom/topics/{quote(item["topic_id"])}?token={quote(token)}">'
        f'{html.escape(item["title"])}</a></li>'
        for item in records
    )
    return (
        "<!doctype html><html lang='zh-Hans'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Wisdom-Oldman 主题文档</title></head>"
        "<body style='max-width:800px;margin:40px auto;font:16px/1.7 system-ui'>"
        f"<h1>Wisdom-Oldman 主题文档</h1><ul>{items or '<li>尚无主题</li>'}</ul></body></html>"
    )
