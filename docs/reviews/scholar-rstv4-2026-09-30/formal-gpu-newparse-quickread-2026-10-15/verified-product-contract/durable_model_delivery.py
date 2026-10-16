"""Resume a persisted router run; observation timeouts never create another inference."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4


class ModelRunPending(RuntimeError):
    retry_after = 5

    def __init__(self, run_id: str | None, status: str):
        self.run_id, self.status = run_id, status
        super().__init__(f"Model execution {run_id or 'submission'} is {status}; resume the same request")


class ModelRunStopped(RuntimeError):
    def __init__(self, run_id: str, status: str):
        self.run_id, self.status = run_id, status
        super().__init__(f"Model execution {run_id} stopped ({status}); review its original request")


def _json_request(url: str, headers: dict, body: dict | None = None) -> dict:
    request = urllib.request.Request(url, headers=headers,
        data=json.dumps(body, ensure_ascii=False).encode('utf-8') if body is not None else None,
        method='POST' if body is not None else 'GET')
    with urllib.request.urlopen(request, timeout=15) as response:
        result = json.loads(response.read().decode('utf-8'))
    if not isinstance(result, dict):
        raise TypeError('Model execution response must be an object')
    return result


def request(root: Path, base_url: str, api_key: str, tier: str, prompt: str,
            operation_id: str, *, observe_seconds: float = 10) -> tuple[str, dict]:
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{8,200}', operation_id):
        raise ValueError('Invalid model operation identity')
    body = {'model': tier, 'messages': [{'role': 'user', 'content': prompt}], 'stream': False}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    directory = root / 'data/artifacts/model-delivery'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (hashlib.sha256(operation_id.encode()).hexdigest() + '.json')
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'}
    saved = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None
    if saved and (saved['request_sha256'] != digest or saved['base_url'] != base_url
                  or saved['operation_id'] != operation_id):
        raise ValueError('Original model request identity belongs to different content or service')
    if saved:
        run_id = saved['run_id']
        if not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', run_id):
            raise ValueError('Original model execution identity is invalid')
    else:
        try:
            submitted = _json_request(base_url + '/runs',
                                      {**headers, 'Idempotency-Key': operation_id}, body)
        except (TimeoutError, OSError) as error:
            if isinstance(error, urllib.error.HTTPError) and 400 <= error.code < 500 and error.code != 429:
                raise ValueError(f'Model execution submission rejected (HTTP {error.code})') from error
            # An uncertain POST is reconciled by the SAME server idempotency key.
            raise ModelRunPending(None, 'submission-unconfirmed') from error
        run_id = submitted.get('id')
        if not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', run_id):
            raise ValueError('Model service returned an invalid execution identity')
        saved = {'operation_id': operation_id, 'run_id': run_id, 'base_url': base_url,
                 'request_sha256': digest}
        temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
        with temporary.open('x', encoding='utf-8') as handle:
            json.dump(saved, handle, ensure_ascii=False, sort_keys=True)
        os.replace(temporary, path)
    deadline = time.monotonic() + observe_seconds
    while True:
        try:
            current = _json_request(base_url + '/runs/' + run_id, headers)
        except (TimeoutError, OSError) as error:
            if isinstance(error, urllib.error.HTTPError) and 400 <= error.code < 500 and error.code != 429:
                raise ValueError(f'Original model execution is unavailable (HTTP {error.code})') from error
            raise ModelRunPending(run_id, 'observation-unconfirmed') from error
        if current.get('id') != run_id or current.get('profile') != tier:
            raise ValueError('Model execution response belongs to another request or profile')
        status = current.get('status')
        if status == 'completed':
            response = current.get('response') or {}
            choices = response.get('choices') or []
            if not choices:
                raise ValueError('Completed model execution has no completion choice')
            content = choices[0].get('message', {}).get('content')
            if not isinstance(content, str) or not content.strip():
                raise ValueError('Completed model execution has no textual answer')
            return content, {'actual_model': response.get('model'), 'usage': response.get('usage'),
                'status': 'SUCCESS', 'transport_operation_id': operation_id,
                'router_run_id': run_id, 'delivery': 'durable-run-v1'}
        if status in {'failed', 'cancelled'}:
            raise ModelRunStopped(run_id, status)
        if status not in {'queued', 'running', 'retrying'}:
            raise ValueError('Model execution has an unknown status')
        if time.monotonic() >= deadline:
            raise ModelRunPending(run_id, status)
        time.sleep(min(.5, max(0, deadline - time.monotonic())))
