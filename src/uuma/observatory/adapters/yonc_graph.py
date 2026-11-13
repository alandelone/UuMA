"""Read-only projection of the canonical YONC Graph into Observatory metrics."""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from datetime import UTC, datetime
from typing import Any

DATABASE_ID = '43a70a25-bb31-47cf-9810-80566f4b62da'


class RemoteYoncReader:
    """Read the existing owner API through SSH; never substitute an obsolete local database."""

    def __init__(self) -> None:
        self.error: str | None = None
        self.snapshot: dict | None = None
        self.checked = float('-inf')
        self.lock = threading.Lock()

    def read(self) -> dict | None:
        with self.lock:
            if time.monotonic() - self.checked < 10:
                return self.snapshot
            script = f'''import json
from urllib.request import urlopen
def read(path):
    with urlopen('http://127.0.0.1:8766/api/v2/'+path, timeout=15) as r:
        return json.load(r)
health=read('health')
if not health['ok'] or health['database_id'] != {DATABASE_ID!r}:
    raise ValueError('Unexpected YONC Graph database')
graph=read('graph')
payload={{key: graph[key] for key in ('graph_version', 'nodes', 'edges')}}
payload['database_id']=health['database_id']
print(json.dumps(payload,ensure_ascii=True))
'''
            try:
                result = subprocess.run(
                    ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
                     os.environ.get('UUMA_OBSERVATORY_YONC_SSH_HOST', 'ubuntu-server'),
                     'python3', '-B', '-'], input=script, capture_output=True, text=True,
                    encoding='utf-8', timeout=38, check=False,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                )
                if result.returncode:
                    raise OSError('Owner Graph API or SSH unavailable')
                snapshot = json.loads(result.stdout)
                if (snapshot.get('database_id') != DATABASE_ID
                        or not isinstance(snapshot.get('nodes'), list)
                        or not isinstance(snapshot.get('edges'), list)
                        or not isinstance(snapshot.get('graph_version'), int)):
                    raise ValueError('Invalid Graph response')
                self.snapshot = snapshot
                self.error = None
            except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
                self.snapshot = None
                self.error = f'服务器 Project Graph 暂不可用（{type(exc).__name__}）；请检查连接。'
            self.checked = time.monotonic()
            return self.snapshot


def summarize_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Calculate actual leaf depth, keeping history and retired branches out of active totals."""
    all_nodes = {n['id']: n for n in graph['nodes']}
    children: dict[str, list[str]] = {}
    for edge in graph['edges']:
        if edge['relation'] == 'contains' and not edge.get('is_proposed'):
            children.setdefault(edge['source_id'], []).append(edge['target_id'])
    excluded = set()
    for ident, n in all_nodes.items():
        tags = n.get('tags') or {}
        if isinstance(tags, str):
            tags = json.loads(tags)
        if (n.get('is_proposed') or n.get('archived') or n.get('archived_at')
                or n.get('status') in ('CANCELLED', 'SUPERSEDED') or tags.get('history')):
            stack = [ident]
            while stack:
                current = stack.pop()
                if current in excluded:
                    continue
                excluded.add(current)
                stack.extend(children.get(current, []))
    nodes = {i: n for i, n in all_nodes.items() if i not in excluded}
    projects = [n for n in nodes.values() if n.get('wbs_level') == 1
                and not n.get('parent_id') and n.get('node_kind', 'WORK') == 'WORK']
    timeline = []
    full = partial = zero = 0
    for root in projects:
        tree = []
        leaves = []
        seen = set()
        stack = [root['id']]
        while stack:
            ident = stack.pop()
            if ident in seen or ident not in nodes:
                continue
            seen.add(ident)
            tree.append(nodes[ident])
            ch = [c for c in children.get(ident, []) if c in nodes]
            if ch:
                stack.extend(ch)
            else:
                leaves.append(nodes[ident])
        l4 = sum(n.get('wbs_level') == 4 for n in leaves)
        is_full = bool(leaves and l4 == len(leaves))
        pct = min(99.9, round(100 * l4 / len(leaves), 1)) if leaves else 0.0
        if is_full:
            pct = 100.0
        full += is_full
        partial += bool(0 < l4 < len(leaves))
        zero += not l4
        if not any(root.get(f) for f in ('planned_start', 'planned_end', 'deadline')):
            continue
        done = sum(n.get('status') == 'DONE' or n.get('lifecycle') == 'DONE' for n in tree)
        timeline.append({
            'id': root['id'], 'title': root['title'],
            'due_date': root.get('deadline') or root.get('planned_end'),
            'planned_start': root.get('planned_start'),
            'completion_pct': round(100 * done / len(tree), 1),
            'total_tasks': len(tree), 'done_tasks': done, 'has_l4': bool(l4),
            'max_level': max(n.get('wbs_level') or 0 for n in tree),
            'l4_decomposition_pct': pct, 'l4_leaves': l4, 'total_leaves': len(leaves),
            'is_fully_l4': is_full, 'status': root.get('status', 'TODO'),
        })
    timeline.sort(key=lambda n: n['due_date'] or '9999-99-99')
    levels = {f'L{i}': sum(n.get('wbs_level') == i for n in nodes.values()) for i in range(1, 5)}
    statuses: dict[str, int] = {}
    for n in nodes.values():
        st = n.get('status') or 'TODO'
        statuses[st] = statuses.get(st, 0) + 1
    return {
        'part1_timeline_projects': timeline,
        'part2_assign_suggestions': [],
        'part3_macro_stats': {
            'total_projects': len(projects),
            'completed_projects': sum(n.get('status') == 'DONE' for n in projects),
            'fully_l4_projects': full, 'partial_l4_projects': partial, 'zero_l4_projects': zero,
            'l4_decomposed_projects': full + partial, 'timeline_assigned_count': len(timeline),
            'total_nodes': len(nodes),
            'total_edges': sum(e['source_id'] in nodes and e['target_id'] in nodes
                               for e in graph['edges'] if not e.get('is_proposed')),
            'level_breakdown': levels, 'status_breakdown': statuses,
        },
        'source_available': True, 'source_error': None,
        'database_id': graph.get('database_id'), 'graph_version': graph.get('graph_version'),
        'read_at': datetime.now(UTC).isoformat(),
    }
