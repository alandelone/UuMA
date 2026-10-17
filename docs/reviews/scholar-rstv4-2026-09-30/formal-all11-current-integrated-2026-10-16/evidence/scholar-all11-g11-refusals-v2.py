"""Exclusive current-source G11 refusal executions; never replay successful work."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

REPO = Path(__file__).resolve().parents[1]
RUNTIME = REPO / '.tmp/scholar-all11-g11-runtime-v2.py'
spec = importlib.util.spec_from_file_location('g11_runtime', RUNTIME)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
base, receipt = runtime.load_base()
folder = runtime.HERE / 'upstream'
root = Path(receipt['copies']['upstream']['root'])

def assert_guard():
    runtime.plan_guard('upstream', base, receipt)
    for value in receipt['copies'].values():
        assert not (Path(value['root']) / 'old-method-must-not-run.txt').exists()
    assert not (base.HISTORICAL / 'old-method-must-not-run.txt').exists()

def method():
    assert_guard()
    runtime.put(folder / 'old-method-started.json', {'plan_id': base.PLAN, 'exclusive_single_call': True})
    state = base.snapshot(root / 'data/catalog.db')
    plan = base.one(state, 'experiment_plans', 'plan_id', base.PLAN)
    node = base.one(state, 'research_nodes', 'node_id', base.METHOD)
    assert plan['status'] == 'APPROVED' and plan['method_node_id'] == base.METHOD
    assert node['status'] == 'SUPERSEDED' and node['track_id'] == plan['track_id']
    sys.path.insert(0, str(base.RST / 'src'))
    from rstv4.track_first import TrackFirstService, RevisionConflictError
    service = TrackFirstService(root)
    assert_guard()
    try:
        service.run_experiment(base.PLAN)
    except RevisionConflictError as exc:
        assert str(exc) == 'The experiment method is no longer approved in this track'
        response = {'exception_type': type(exc).__name__, 'message': str(exc)}
    else:
        raise AssertionError('Old Method was not refused')
    assert_guard()
    runtime.put(folder / 'old-method-refusal.json', {'status': 'PASS_ACTUAL_CURRENT_CORE_REFUSAL',
        'plan_id': base.PLAN, 'method_id': base.METHOD, 'response': response,
        'all110_files_originals_source_exact': True, 'marker_absent': True,
        'new_runs_models_grants': 0})
    print('PASS_ACTUAL_CURRENT_OLD_METHOD_REFUSAL_ALL110_EXACT')

def zero():
    assert_guard()
    runtime.put(folder / 'four-zero-started.json', {'exclusive_single_sequence': True})
    responses = []
    for index, (ms, (original, target)) in enumerate(base.ZERO.items(), 1):
        assert_guard()
        body = {'stage': target, 'expected_revision': 1, 'reason': runtime.REASON}
        request = urllib.request.Request('http://127.0.0.1:8877/api/manuscripts/' + ms + '/stage',
            data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'}, method='POST')
        runtime.put(folder / f'zero-{index}-request.json', {'manuscript_id': ms,
            'original_stage': original, 'url': request.full_url, 'body': body})
        try:
            urllib.request.urlopen(request, timeout=30)
        except urllib.error.HTTPError as exc:
            status = exc.code
            response = json.loads(exc.read())
            assert status == 422 and 'successful generated version' in response['detail']
        else:
            raise AssertionError('Zero version stage transition was not refused')
        assert_guard()
        value = {'manuscript_id': ms, 'target': target, 'status': status, 'body': response,
                 'all110_files_originals_source_exact': True}
        runtime.put(folder / f'zero-{index}-response.json', value)
        responses.append(value)
    runtime.put(folder / 'four-zero-refusals.json', {'status': 'PASS_FOUR_REAL_CURRENT_HTTP_REFUSALS',
        'responses': responses, 'new_stages_versions_jobs_approvals': 0})
    print('PASS_FOUR_REAL_CURRENT_HTTP_422_ALL110_EXACT')

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['method', 'zero'])
    {'method': method, 'zero': zero}[p.parse_args().mode]()
