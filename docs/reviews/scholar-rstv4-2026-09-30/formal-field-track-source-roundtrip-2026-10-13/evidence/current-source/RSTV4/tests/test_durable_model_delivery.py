from __future__ import annotations

import json
import sqlite3
from contextlib import closing

import pytest
from test_acquisition_deep_read import RecordedGateway, parse, request, setup

from rstv4 import durable_model_delivery as delivery
from rstv4.acquisition_worker import ROLE_QUEUES, AcquisitionWorker
from rstv4.durable_model_delivery import ModelRunPending, ModelRunStopped
from rstv4.model_gateway import UnlimitedLLMGateway


def completed(run_id='run_original'):
    return {'id': run_id, 'profile': 'standard', 'status': 'completed', 'response': {
        'model': 'actual-software-model', 'usage': {'total_tokens': 4},
        'choices': [{'message': {'content': '{"intent":"UNKNOWN"}'}}]}}


def test_pending_execution_persists_handle_and_resume_never_submits_again(tmp_path, monkeypatch):
    posts = []; state = 'running'
    def http(url, headers, body=None):
        if body:
            posts.append((url, headers['Idempotency-Key'], body))
            return {'id': 'run_original'}
        return completed() if state == 'completed' else {'id': 'run_original', 'profile': 'standard', 'status': state}
    monkeypatch.setattr(delivery, '_json_request', http)
    with pytest.raises(ModelRunPending) as pending:
        delivery.request(tmp_path, 'http://router/v1', 'PRIVATE_KEY', 'standard', 'Original text', 'operation-original', observe_seconds=0)
    assert pending.value.run_id == 'run_original'
    checkpoint = next((tmp_path / 'data/artifacts/model-delivery').glob('*.json'))
    assert 'PRIVATE_KEY' not in checkpoint.read_text()
    state = 'completed'
    text, contract = delivery.request(tmp_path, 'http://router/v1', 'PRIVATE_KEY', 'standard', 'Original text', 'operation-original')
    assert text == '{"intent":"UNKNOWN"}' and len(posts) == 1
    assert contract['router_run_id'] == 'run_original' and contract['actual_model'] == 'actual-software-model'


def test_lost_submit_response_reuses_same_idempotency_key(tmp_path, monkeypatch):
    keys = []
    def http(url, headers, body=None):
        if body:
            keys.append(headers['Idempotency-Key'])
            if len(keys) == 1:
                raise TimeoutError('Lost POST response after acceptance')
            return {'id': 'run_original'}
        return completed()
    monkeypatch.setattr(delivery, '_json_request', http)
    with pytest.raises(ModelRunPending) as pending:
        delivery.request(tmp_path, 'http://router/v1', 'key', 'standard', 'Original', 'same-operation')
    assert pending.value.run_id is None
    delivery.request(tmp_path, 'http://router/v1', 'key', 'standard', 'Original', 'same-operation')
    assert keys == ['same-operation', 'same-operation']


def test_changed_content_cannot_retarget_persisted_execution(tmp_path, monkeypatch):
    writes = []
    def http(url, headers, body=None):
        if body:writes.append(body);return {'id': 'run_original'}
        return completed()
    monkeypatch.setattr(delivery, '_json_request', http)
    delivery.request(tmp_path, 'http://router/v1', 'key', 'standard', 'Original', 'same-operation')
    with pytest.raises(ValueError, match='different content'):
        delivery.request(tmp_path, 'http://router/v1', 'key', 'standard', 'Changed', 'same-operation')
    assert len(writes) == 1


@pytest.mark.parametrize('status', ['failed', 'cancelled'])
def test_terminal_execution_never_automatically_resubmits(tmp_path, monkeypatch, status):
    posts = []
    def http(url, headers, body=None):
        if body:posts.append(body);return {'id':'run_original'}
        return {'id':'run_original', 'profile':'standard', 'status':status}
    monkeypatch.setattr(delivery, '_json_request', http)
    for _ in range(2):
        with pytest.raises(ModelRunStopped):
            delivery.request(tmp_path, 'http://router/v1', 'key', 'standard', 'Original', 'same-operation')
    assert len(posts) == 1


def test_foreign_execution_identity_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(delivery, '_json_request', lambda url, headers, body=None: {'id':'run_original'} if body else completed('run_foreign'))
    with pytest.raises(ValueError, match='another request'):
        delivery.request(tmp_path, 'http://router/v1', 'key', 'standard', 'Original', 'same-operation')


class DurableFixture(RecordedGateway):
    mode = 'http'
    def __init__(self, root):
        self.gateway = UnlimitedLLMGateway(root)
        self.started = []
        self.pending = True
    def operation_id(self, task, payload, scope):
        return self.gateway.operation_id(task, payload, scope)
    def analyze_for_operation(self, task, payload, operation_id):
        self.started.append(task)
        if task == 'skeleton_layer_3' and self.pending:
            raise ModelRunPending('fixture_run3', 'running')
        result = super().analyze(task, payload)
        result['_contract'].update(transport_operation_id=operation_id, router_run_id='fixture_' + task, delivery='durable-run-v1')
        return result


def test_worker_resume_reuses_completed_layers_and_same_call_identity(tmp_path, monkeypatch):
    monkeypatch.setitem(ROLE_QUEUES, 'model', ['MODEL_SKELETON'])
    service, cid, db, _ = setup(tmp_path)
    parse(service, cid);job = request(service, cid)
    gateway = DurableFixture(tmp_path)
    worker = AcquisitionWorker(tmp_path, 'model', model_gateway=gateway, worker_id='durable-fixture')
    waiting = worker.run_once()
    assert waiting['status'] == 'RESOURCE_WAIT'
    first = service.get_paper('existing')['model_calls']
    assert [c['status'] for c in first] == ['RETURNED', 'RETURNED', 'WAITING']
    assert first[-1]['contract']['router_run_id'] == 'fixture_run3'
    gateway.pending = False
    service.retry_step(job['job_id'], waiting['fencing_token'], expected_status='RESOURCE_WAIT', expected_updated_at=waiting['updated_at'])
    finished = worker.run_once()
    assert finished['status'] == 'SUCCEEDED'
    assert gateway.started == ['skeleton_layer_1', 'skeleton_layer_2', 'skeleton_layer_3', 'skeleton_layer_3', 'skeleton_layer_4']
    calls = service.get_paper('existing')['model_calls']
    assert len(calls) == 4 and all(c['status'] == 'RETURNED' for c in calls)
    assert [c['call_id'] for c in calls[:3]] == [c['call_id'] for c in first]
    with closing(sqlite3.connect(db)) as conn:
        events = conn.execute('SELECT event_kind FROM acquisition_model_call_events WHERE call_id=? ORDER BY event_seq', (first[-1]['call_id'],)).fetchall()
        assert events == [('STARTED',), ('WAITING',), ('RETURNED',)]
        assert conn.execute('SELECT COUNT(*) FROM paper_skeletons').fetchone()[0] == 1


def test_new_request_or_contract_does_not_reuse_a_different_execution(tmp_path):
    gateway = UnlimitedLLMGateway(tmp_path)
    payload = {'raw_text':'Same text'}
    first = gateway.operation_id('skeleton_layer_3', payload, {'job_id':'job1'})
    assert first != gateway.operation_id('skeleton_layer_3', payload, {'job_id':'job2'})
    assert first != gateway.operation_id('skeleton_layer_3', {'raw_text':'Changed'}, {'job_id':'job1'})
    assert first == gateway.operation_id('skeleton_layer_3', payload, {'job_id':'job1'})


def test_modified_checkpoint_cannot_select_an_arbitrary_execution_path(tmp_path, monkeypatch):
    monkeypatch.setattr(delivery, '_json_request', lambda url, headers, body=None: {'id':'run_original'} if body else completed())
    delivery.request(tmp_path, 'http://router/v1', 'key', 'standard', 'Original', 'same-operation')
    path = next((tmp_path/'data/artifacts/model-delivery').glob('*.json'))
    checkpoint = json.loads(path.read_text())
    checkpoint['run_id'] = '../other-endpoint'
    path.write_text(json.dumps(checkpoint))
    with pytest.raises(ValueError, match='identity is invalid'):
        delivery.request(tmp_path, 'http://router/v1', 'key', 'standard', 'Original', 'same-operation')
