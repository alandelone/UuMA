from __future__ import annotations

import hashlib
import json
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient
from test_track_first_fieldkg import create_hierarchy

from rstv4.catalog_web import create_app
from rstv4.experiment import ExperimentRunner
from rstv4.track_first import TrackFirstService


@pytest.fixture
def setup(tmp_path):
    service=TrackFirstService(tmp_path)
    field,_,track,project=create_hierarchy(service)
    work=tmp_path/'projects'/project['slug'];work.mkdir(parents=True)
    return service,track['track_id'],project['project_id'],work,TestClient(create_app(tmp_path)),field['field_id']


def detail(service,run_id):
    with sqlite3.connect(service.db_path) as conn:
        row=conn.execute('SELECT status,detail_json FROM pipeline_runs WHERE run_id=?',(run_id,)).fetchone()
    return row[0],json.loads(row[1])


def run(setup,code,**values):
    service,track,project,work,_,_=setup
    return ExperimentRunner(service.db_path).run_script([sys.executable,'-c',code],track_id=track,project_id=project,cwd=work,**values)


def test_full_output_input_environment_and_original_artifact_are_retained(setup):
    service,track,_,work,client,_=setup
    source=work/'input.txt';source.write_text('Original input',encoding='utf-8')
    result=run(setup,"from pathlib import Path; import json; print('x'*2500); Path('metrics.json').write_text(json.dumps({'accuracy':.8})); Path('result.txt').write_text('Original output')",input_files=['input.txt'],artifact_paths=['result.txt'],metrics_json_path='metrics.json')
    status,record=detail(service,result.run_id)
    assert status=='COMPLETED' and len(record['stdout'])>2500
    assert record['inputs'][0]['sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
    assert record['environment']['observer_python_version'] and record['cwd']==str(work.resolve())
    assert len(record['artifacts'])==2 and len(record['output_files'])==2
    response=client.get(f'/api/catalog/tracks/{track}/runs/{result.run_id}/artifacts/0')
    assert response.status_code==200 and response.content==b'Original output'
    assert client.get(f'/api/catalog/tracks/wrong/runs/{result.run_id}/artifacts/0').status_code==404
    (work/'result.txt').write_text('Changed output',encoding='utf-8')
    assert client.get(f'/api/catalog/tracks/{track}/runs/{result.run_id}/artifacts/0').status_code==409
    assert detail(service,result.run_id)==(status,record)


@pytest.mark.parametrize('code',["from pathlib import Path; Path('metrics.json').write_text('not-json')", "from pathlib import Path; Path('metrics.json').write_text('[]')", "print('No metrics')"])
def test_invalid_metrics_cannot_be_reported_as_successful_evidence(setup,code):
    service,*_=setup
    result=run(setup,code,metrics_json_path='metrics.json')
    assert detail(service,result.run_id)[0]=='METRICS_ERROR'
    with pytest.raises(ValueError,match='completed|incomplete'):
        service.record_experiment_evidence(result.run_id,'Result claim')


def test_stale_metrics_are_rejected_but_identical_reproduced_metrics_are_valid(setup):
    service,_,_,work,_,_=setup
    (work/'metrics.json').write_text('{"value": 1}',encoding='utf-8')
    stale=run(setup,"print('No new result')",metrics_json_path='metrics.json')
    assert detail(service,stale.run_id)[0]=='METRICS_ERROR'
    fresh=run(setup,"from pathlib import Path; Path('metrics.json').write_text('{\"value\": 1}')",metrics_json_path='metrics.json')
    assert detail(service,fresh.run_id)[0]=='COMPLETED'
    with pytest.raises(ValueError,match='metric'):
        service.record_experiment_evidence(fresh.run_id,'Result','missing-key')


def test_modified_input_or_missing_artifact_prevents_result_evidence(setup):
    service,_,_,work,_,_=setup
    (work/'input.txt').write_text('Original',encoding='utf-8')
    changed=run(setup,"from pathlib import Path; Path('input.txt').write_text('Changed')",input_files=['input.txt'])
    assert detail(service,changed.run_id)[0]=='INPUT_CHANGED'
    assert detail(service,changed.run_id)[1]['changed_inputs']==['input.txt']
    missing=run(setup,"print('Nothing produced')",artifact_paths=['missing.txt'])
    assert detail(service,missing.run_id)[0]=='ARTIFACT_ERROR'
    for result in [changed,missing]:
        with pytest.raises(ValueError):service.record_experiment_evidence(result.run_id,'Unsupported result')


def test_workspace_escape_is_rejected_before_execution(setup):
    service,_,_,work,_,_=setup
    before=service.db_path.read_bytes()
    with pytest.raises(ValueError,match='workspace'):
        run(setup,"from pathlib import Path; Path('must-not-run').write_text('bad')",artifact_paths=['../outside.txt'])
    assert not (work/'must-not-run').exists() and service.db_path.read_bytes()==before


def test_timeout_preserves_actual_partial_stdout_and_stderr(setup):
    service,*_=setup
    result=run(setup,"import time,sys; print('Partial output',flush=True); print('Partial error',file=sys.stderr,flush=True); time.sleep(10)",timeout=1)
    status,record=detail(service,result.run_id)
    assert status=='TIMEOUT'
    assert 'Partial output' in record['stdout'] and 'Partial error' in record['stderr']


def test_explicit_environment_is_recorded_without_dumping_ambient_secrets(setup,monkeypatch):
    service,*_=setup
    monkeypatch.setenv('PRIVATE_AMBIENT_TEST_SECRET','must-not-be-recorded')
    result=run(setup,"print('done')")
    record=detail(service,result.run_id)[1]
    assert 'must-not-be-recorded' not in json.dumps(record)
