"""Append-only receipts for actual acquisition model calls."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from .database import transaction
from .durable_model_delivery import ModelRunPending, ModelRunStopped

SCHEMA = """
CREATE TABLE IF NOT EXISTS acquisition_model_call_events (
 event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
 call_id TEXT NOT NULL,
 event_kind TEXT NOT NULL,
 job_id TEXT NOT NULL REFERENCES acquisition_jobs(job_id),
 paper_id TEXT NOT NULL REFERENCES papers(paper_id),
 fencing_token INTEGER NOT NULL,
 task TEXT NOT NULL,
 input_json TEXT NOT NULL,
 source_json TEXT NOT NULL,
 output_json TEXT,
 contract_json TEXT,
 error_type TEXT,
 created_at TEXT NOT NULL,
 UNIQUE(call_id,event_kind)
);
"""


class ModelSourceChanged(ValueError):
    """A recorded parse source is no longer usable and requires human review."""


def analyze(service, gateway, job, worker_id, task, payload, parse_run_id=None):
    call_id = 'acquisition-call-' + uuid4().hex
    raw_input = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    with transaction(service.db_path) as conn:
        service._require_publication_lease(conn, job['job_id'], worker_id, job['fencing_token'])
        service._require_membership(conn, job['collection_id'], job['paper_id'])
        source = {'collection_id':job['collection_id'], 'paper_id':job['paper_id'],
                  'job_input_digest':job['input_digest']}
        if parse_run_id:
            try:
                file = service._require_parse_source(conn, parse_run_id, job['paper_id'])
            except ValueError as error:
                raise ModelSourceChanged(str(error)) from error
            source.update(parse_run_id=parse_run_id, file_version_id=file['file_version_id'],
                          pdf_sha256=file['sha256'])
        else:
            source['screening_context'] = service._screening_context(conn, job['collection_id'], job['paper_id'])
        operation_id = None
        if getattr(gateway, 'mode', None) == 'http' and hasattr(gateway, 'analyze_for_operation'):
            operation_id = gateway.operation_id(task, payload, {'job_id': job['job_id'], **source})
            source['transport_operation_id'] = operation_id
            call_id = 'acquisition-call-' + operation_id.removeprefix('rstv4-model-')
        raw_source = json.dumps(source, ensure_ascii=False, sort_keys=True)
        if operation_id:
            previous = conn.execute("SELECT output_json,input_json,source_json FROM acquisition_model_call_events WHERE call_id=? AND event_kind='RETURNED'", (call_id,)).fetchone()
            if previous:
                if previous['input_json'] != raw_input or previous['source_json'] != raw_source:
                    raise ValueError('Original model receipt belongs to different input or source')
                cached = json.loads(previous['output_json'])
                saved_contract = cached.get('_contract') or {}
                if (saved_contract.get('transport_operation_id') != operation_id
                        or saved_contract.get('receipt_id') != call_id
                        or saved_contract.get('task') != task):
                    raise ValueError('Original model result no longer matches its execution receipt')
                return cached
        conn.execute('INSERT OR IGNORE INTO acquisition_model_call_events(call_id,event_kind,job_id,paper_id,fencing_token,task,input_json,source_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                     (call_id,'STARTED',job['job_id'],job['paper_id'],job['fencing_token'],task,raw_input,raw_source,datetime.now(UTC).isoformat()))
    try:
        result = gateway.analyze_for_operation(task, payload, operation_id) if operation_id else gateway.analyze(task, payload)
        contract = result.get('_contract')
        if not isinstance(contract, dict):
            raise TypeError('Model output has no actual execution contract')
        contract = {**contract, 'receipt_id': call_id}
        result = {**result, '_contract': contract}
        raw_output = json.dumps(result, ensure_ascii=False, sort_keys=True)
    except (ModelRunPending, ModelRunStopped) as error:
        with transaction(service.db_path) as conn:
            contract = {'transport_operation_id': operation_id, 'router_run_id': error.run_id,
                        'router_status': error.status, 'delivery': 'durable-run-v1'}
            conn.execute('INSERT OR IGNORE INTO acquisition_model_call_events(call_id,event_kind,job_id,paper_id,fencing_token,task,input_json,source_json,contract_json,error_type,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                         (call_id,('WAITING' if error.run_id else 'UNCONFIRMED') if isinstance(error, ModelRunPending) else 'STOPPED',job['job_id'],job['paper_id'],job['fencing_token'],task,raw_input,raw_source,json.dumps(contract,sort_keys=True),type(error).__name__,datetime.now(UTC).isoformat()))
        raise
    except Exception as error:
        with transaction(service.db_path) as conn:
            conn.execute('INSERT OR IGNORE INTO acquisition_model_call_events(call_id,event_kind,job_id,paper_id,fencing_token,task,input_json,source_json,error_type,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                         (call_id,'FAILED',job['job_id'],job['paper_id'],job['fencing_token'],task,raw_input,raw_source,type(error).__name__,datetime.now(UTC).isoformat()))
        raise
    with transaction(service.db_path) as conn:
        conn.execute('INSERT OR IGNORE INTO acquisition_model_call_events(call_id,event_kind,job_id,paper_id,fencing_token,task,input_json,source_json,output_json,contract_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                     (call_id,'RETURNED',job['job_id'],job['paper_id'],job['fencing_token'],task,raw_input,raw_source,raw_output,json.dumps(contract,ensure_ascii=False,sort_keys=True),datetime.now(UTC).isoformat()))
    return result


def list_calls(conn, paper_id, *, include_details=True, call_id=None):
    calls = {}
    for row in conn.execute('SELECT * FROM acquisition_model_call_events WHERE paper_id=? AND (? IS NULL OR call_id=?) ORDER BY event_seq', (paper_id,call_id,call_id)):
        event = dict(row)
        call = calls.setdefault(event['call_id'], {'call_id':event['call_id'], 'started_at':event['created_at']})
        call.update(job_id=event['job_id'], fencing_token=event['fencing_token'], task=event['task'],
                    status=event['event_kind'], input=json.loads(event['input_json']),
                    source=json.loads(event['source_json']), output=json.loads(event['output_json']) if event['output_json'] else None,
                    contract=json.loads(event['contract_json']) if event['contract_json'] else None,
                    error_type=event['error_type'], completed_at=event['created_at'] if event['event_kind']!='STARTED' else None)
    if not include_details:
        for call in calls.values():
            call.pop("input", None)
            call.pop("output", None)
    return list(calls.values())
