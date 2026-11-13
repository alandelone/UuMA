import json
from types import SimpleNamespace

from uuma.observatory.adapters.yonc import YoncAdapter
from uuma.observatory.adapters.yonc_graph import RemoteYoncReader, summarize_graph


def sample_graph():
    nodes=[]; edges=[]
    for i in range(1,11):
        for level in range(1,5):
            ident=f'{i}.{level}'
            parent=f'{i}.{level-1}' if level>1 else None
            nodes.append({'id':ident,'title':f'Project {i} / L{level}','wbs_level':level,
                          'node_kind':'WORK','status':'TODO','parent_id':parent,
                          'deadline':'2026-12-01' if level==1 else None})
            if parent: edges.append({'source_id':parent,'target_id':ident,'relation':'contains'})
    return {'database_id':'43a70a25-bb31-47cf-9810-80566f4b62da',
            'graph_version':518,'nodes':nodes,'edges':edges}


def test_all_ten_live_trees_reach_l4_and_history_does_not_change_depth():
    graph=sample_graph()
    graph['nodes'] += [
        {'id':'history','title':'History','tags':{'history':True},'node_kind':'ARTIFACT'},
        {'id':'old-done','title':'Completed old L3','parent_id':'history','wbs_level':3,'status':'DONE'},
        {'id':'cancelled','title':'Retired L3','parent_id':'1.2','wbs_level':3,'status':'CANCELLED'},
    ]
    graph['edges'] += [
        {'source_id':'history','target_id':'old-done','relation':'contains'},
        {'source_id':'1.2','target_id':'cancelled','relation':'contains'},
    ]
    data=summarize_graph(graph)
    assert len(data['part1_timeline_projects'])==10
    assert all(p['l4_decomposition_pct']==100 and p['is_fully_l4']
               for p in data['part1_timeline_projects'])
    assert data['part3_macro_stats']['total_nodes']==40
    assert data['graph_version']==518


def test_incomplete_branch_is_not_reported_as_full():
    graph=sample_graph()
    graph['nodes'].append({'id':'unfinished','title':'L3 not split','parent_id':'1.2',
                           'wbs_level':3,'status':'TODO'})
    graph['edges'].append({'source_id':'1.2','target_id':'unfinished','relation':'contains'})
    project=summarize_graph(graph)['part1_timeline_projects'][0]
    assert project['l4_decomposition_pct']==50
    assert not project['is_fully_l4']
    assert project['completion_pct']==0


def test_remote_reader_uses_only_get_api_and_caches_then_clears_failure(monkeypatch):
    calls=[]
    def run(command,**kwargs):
        calls.append((command,kwargs))
        return SimpleNamespace(returncode=0,stdout=json.dumps(sample_graph()))
    monkeypatch.setattr('uuma.observatory.adapters.yonc_graph.subprocess.run',run)
    reader=RemoteYoncReader()
    assert reader.read()['graph_version']==518
    assert reader.read()['graph_version']==518 and len(calls)==1
    assert calls[0][0][-3:]==['python3','-B','-']
    assert "read('graph')" in calls[0][1]['input']
    reader.checked=float('-inf')
    monkeypatch.setattr('uuma.observatory.adapters.yonc_graph.subprocess.run',
                        lambda *a,**k: SimpleNamespace(returncode=1,stdout=''))
    assert reader.read() is None
    assert reader.error and reader.snapshot is None


def test_missing_owner_is_warning_and_never_old_nine_project_snapshot(tmp_path,monkeypatch):
    adapter=YoncAdapter(tmp_path,tmp_path/'absent.db')
    monkeypatch.setattr(adapter.remote_reader,'read',lambda:None)
    adapter.remote_reader.error='Disconnected'
    data=adapter.list_items()[0]
    assert data.health=='WARNING'
    assert data.payload['source_available'] is False
    assert data.payload['part1_timeline_projects']==[]
    assert data.payload['part3_macro_stats']['total_projects']==0
    assert not adapter.probe_health().is_available
