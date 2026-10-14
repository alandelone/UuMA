from __future__ import annotations

import copy
import json

import pytest

pytest.importorskip('dspy', reason='Optional skeleton-optimization dependency')

from rstv4.skeleton_boundary_reference_v4 import canonical_claim_id_reference
from rstv4.skeleton_contract import SourceContractError, digest, with_source_spans
from rstv4.skeleton_mapped_graph_v2 import MAPPED_VERIFIED_VERSION
from rstv4.skeleton_test_cue_reference_v3 import PostCompileCueReferenceBuilder, PreviousBuilder


def setup(tmp_path):
    block = with_source_spans([{'block_id': 'p:b1', 'block_type': 'TEXT',
                               'text': 'Cost is 0.2 USD/kWh in scenario A.'}])[0]
    claims = [{'reference_id': 'r1', 'block_id': 'p:b1', 'statement': block['text'],
               'quote': '', 'source_span_ids': ['p:b1:s1'], 'qualifications': ['scenario A'],
               'intent': 'Objective_Finding'}]
    role = {'block_id': 'p:b1', 'role': 'Result_Performance', 'confidence': 0.9,
            'rationale': 'Reported conditional cost.'}
    inputs = {'document_context': '{}', 'source_blocks': json.dumps([block])}
    reference = canonical_claim_id_reference(block, claims, role)
    saved = {'inputs_digest': digest(inputs), 'candidate_access': False,
             'source_graph_review_gate_passed': True, 'reference': reference,
             'original_stage_path': 'original-immutable-model-stage'}
    builder = object.__new__(PostCompileCueReferenceBuilder)
    builder.output = tmp_path / 'child'
    builder.historical_source_parent = tmp_path / 'parent'
    key = digest({'version': MAPPED_VERIFIED_VERSION, 'inputs': inputs})
    paths = [directory / 'references' / f'{key}.json'
             for directory in (builder.output, builder.historical_source_parent)]
    for path in paths:
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(saved), encoding='utf-8')
    audits = []

    def audit(actual_inputs, path):
        audits.append((actual_inputs, path))
        return {'status': 'COMPLETE_ACTUAL_SOURCE_REPLAY_AUDIT',
                'reference_record_digest': digest(json.loads(path.read_text(encoding='utf-8'))),
                'model_calls': 0}

    builder.source_replay_auditor = audit
    return builder, inputs, saved, paths, audits


def test_complete_independent_audit_precedes_byte_identical_history_replay(tmp_path):
    builder, inputs, saved, paths, audits = setup(tmp_path)
    before = [path.read_bytes() for path in paths]
    returned = builder.build(inputs)
    assert audits == [(inputs, paths[0])]
    assert returned == saved['reference']
    assert before == [path.read_bytes() for path in paths]
    returned['claims'][0]['qualifications'].append('mutation')
    assert json.loads(paths[0].read_text(encoding='utf-8')) == saved
    receipt = json.loads(next((builder.output / 'historical-replay-audits').glob('*.json')).read_text(encoding='utf-8'))
    assert receipt['original_evidence_paths_preserved'] and receipt['candidate_access'] is False


def test_history_with_missing_actual_auditor_remains_fatal(tmp_path):
    builder, inputs, _, _, _ = setup(tmp_path)
    builder.source_replay_auditor = None
    with pytest.raises(SourceContractError, match='requires independent'):
        builder.build(inputs)


def test_relocated_evidence_path_is_rejected_before_history_audit(tmp_path):
    builder, inputs, saved, paths, audits = setup(tmp_path)
    changed = copy.deepcopy(saved)
    changed['original_stage_path'] = 'relocated-stage'
    paths[0].write_text(json.dumps(changed), encoding='utf-8')
    with pytest.raises(SourceContractError, match='exact declared parent'):
        builder.build(inputs)
    assert not audits


def test_auditor_failure_cannot_publish_historical_replay(tmp_path):
    builder, inputs, _, _, _ = setup(tmp_path)

    def fail(*args):
        raise ValueError('Actual independent completion missing')

    builder.source_replay_auditor = fail
    with pytest.raises(ValueError, match='completion missing'):
        builder.build(inputs)
    assert not (builder.output / 'historical-replay-audits').exists()


def test_forged_actual_audit_digest_remains_fatal(tmp_path):
    builder, inputs, _, _, _ = setup(tmp_path)
    builder.source_replay_auditor = lambda *args: {'status': 'COMPLETE_ACTUAL_SOURCE_REPLAY_AUDIT',
                                                  'reference_record_digest': 'wrong'}
    with pytest.raises(SourceContractError, match='actual audit'):
        builder.build(inputs)


def test_new_source_window_runs_ordinary_model_pipeline(tmp_path, monkeypatch):
    builder, inputs, _, _, audits = setup(tmp_path)
    inputs = {**inputs, 'document_context': '{"new": true}'}
    calls = []
    monkeypatch.setattr(PreviousBuilder, 'build', lambda self, actual: calls.append(actual) or {'new': True})
    assert builder.build(inputs) == {'new': True}
    assert calls == [inputs] and not audits
