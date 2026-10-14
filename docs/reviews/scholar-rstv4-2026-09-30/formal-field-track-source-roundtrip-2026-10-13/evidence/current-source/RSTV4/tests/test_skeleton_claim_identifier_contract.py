from __future__ import annotations

import copy
import json

import pytest

dspy = pytest.importorskip('dspy', reason='Optional skeleton-optimization dependency')

from rstv4.skeleton_boundary_reference_v4 import (
    CLAIM_IDENTIFIER_CONTRACT,
    BoundarySourceReferenceBuilder,
    canonical_claim_id_reference,
)
from rstv4.skeleton_contract import BlockRole, SourceContractError, digest, with_source_spans
from rstv4.skeleton_experiment import ReferenceClaim
from rstv4.skeleton_source_reference import SOURCE_REFERENCE_VERSION


def source():
    block = with_source_spans([{'block_id': 'p:b1', 'block_type': 'TEXT',
                               'text': 'Cost is 0.2 USD/kWh in scenario A. Emissions may decline by 5 percent.'}])[0]
    claims = [{'reference_id': 'r1', 'block_id': 'p:b1',
               'statement': 'Cost is 0.2 USD/kWh in scenario A (Smith, 2020).', 'quote': '',
               'source_span_ids': ['p:b1:s1'], 'qualifications': ['scenario A', '0.2 USD/kWh'],
               'intent': 'Objective_Finding'},
              {'reference_id': 'r2', 'block_id': 'p:b1',
               'statement': 'Emissions may decline by 5 percent (Smith, 2020).', 'quote': '',
               'source_span_ids': ['p:b1:s2'], 'qualifications': ['may', '5 percent'],
               'intent': 'Implication'}]
    role = {'block_id': 'p:b1', 'role': 'Result_Performance', 'confidence': 0.9,
            'rationale': 'Reported cost and conditional emissions implication.'}
    return block, claims, role


def test_shared_bibliographic_source_has_distinct_claims_without_changing_content():
    block, claims, role = source()
    before = copy.deepcopy(claims)
    result = canonical_claim_id_reference(block, claims, role)
    assert claims == before
    assert len(result['claims']) == 2
    for actual, original in zip(result['claims'], claims, strict=True):
        for field in ('block_id', 'statement', 'qualifications', 'intent', 'source_span_ids'):
            assert actual[field] == original[field]
    assert [x['reference_id'] for x in result['claims']] == ['p:b1:r1', 'p:b1:r2']


def test_duplicate_bibliographic_alias_is_rejected_with_exact_positions_without_relabelling():
    block, claims, role = source()
    for claim in claims:
        claim['reference_id'] = 'Smith, 2020'
    before = copy.deepcopy(claims)
    with pytest.raises(SourceContractError, match='Duplicate reference claim IDs') as error:
        canonical_claim_id_reference(block, claims, role)
    assert 'Smith, 2020' in str(error.value) and '[1,2]' in str(error.value).replace(' ', '')
    assert 'NOT a bibliographic citation' in str(error.value)
    assert claims == before


@pytest.mark.parametrize('invalid', ['p:b1', 'p:b1:s1', 'Smith, 2020', '', 'r0', 'other:b1:r1'])
def test_claim_alias_domain_does_not_accept_source_or_bibliographic_identifiers(invalid):
    block, claims, role = source()
    claims[0]['reference_id'] = invalid
    with pytest.raises(SourceContractError, match='field/domain'):
        canonical_claim_id_reference(block, claims, role)


def test_identifier_fix_preserves_actual_source_scope_gate():
    block, claims, role = source()
    claims[0]['source_span_ids'] = ['another:b2:s1']
    with pytest.raises(SourceContractError):
        canonical_claim_id_reference(block, claims, role)


class Predictor:
    def __init__(self, claims, role, invalid_attempts=0):
        self.claims, self.role, self.invalid_attempts = claims, role, invalid_attempts
        self.calls = []

    def __call__(self, **values):
        self.calls.append(values)
        claims = copy.deepcopy(self.claims)
        if len(self.calls) <= self.invalid_attempts:
            for claim in claims:
                claim['reference_id'] = 'Smith, 2020'
        return dspy.Prediction(claims=[ReferenceClaim.model_validate(x) for x in claims],
                               role=BlockRole.model_validate(self.role), source_boundaries=[], corrections=[])


def builder(tmp_path, attempts):
    block, claims, role = source()
    instance = object.__new__(BoundarySourceReferenceBuilder)
    instance.output, instance.parent_references = tmp_path, {}
    instance.lm = dspy.LM('test/model')
    context = json.dumps({'title': 'Synthetic isolated test'})
    instance.bind_window({'document_context': context, 'source_blocks': json.dumps([block])})
    instance.annotator = Predictor(claims, role, attempts)
    instance.reviewer = Predictor(claims, role)
    return instance, context, block


def test_bounded_protocol_feedback_preserves_failed_output_and_independent_review(tmp_path):
    instance, context, block = builder(tmp_path, 1)
    result = instance.block(context, block)
    key = digest({'version': SOURCE_REFERENCE_VERSION, 'context': context, 'block': block})
    saved = json.loads((tmp_path / 'blocks' / f'{key}.json').read_text(encoding='utf-8'))
    stage = saved['stages']['ANNOTATION']
    assert len(instance.annotator.calls) == 2 and len(instance.reviewer.calls) == 1
    assert stage['rejected_attempts'][0]['model_output']['claims'][0]['reference_id'] == 'Smith, 2020'
    assert stage['rejected_attempts'][0]['protocol_error'] == stage['failed_attempts'][0]
    assert instance.annotator.calls[1]['repair_feedback'] == stage['failed_attempts'][0]
    assert all(x['claim_identifier_contract'] == CLAIM_IDENTIFIER_CONTRACT for x in instance.annotator.calls)
    assert result == saved['stages']['INDEPENDENT_REVIEW']['reference']
    assert json.loads(instance.reviewer.calls[0]['draft_reference']) == saved['draft']


def test_three_invalid_outputs_remain_fatal_without_review_or_saved_reference(tmp_path):
    instance, context, block = builder(tmp_path, 3)
    with pytest.raises(SourceContractError, match='stage exhausted'):
        instance.block(context, block)
    assert len(instance.annotator.calls) == 3 and not instance.reviewer.calls
    assert not list((tmp_path / 'blocks').glob('*.json'))
    failed = json.loads(next((tmp_path / 'failures').glob('*.json')).read_text(encoding='utf-8'))
    assert len(failed['failures']) == len(failed['rejected_attempts']) == 3
