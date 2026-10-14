from __future__ import annotations

import copy
import json

import pytest

dspy = pytest.importorskip('dspy', reason='Optional skeleton-optimization dependency')

from rstv4.skeleton_contract import SourceContractError, with_source_spans
from rstv4.skeleton_endpoint_review import EndpointVerdict
from rstv4.skeleton_normalized_endpoint_v2 import (
    NormalizedEndpointReviewer,
    endpoint_inputs,
    restore_verdict,
)


def fixture(ids=('paper:b1:r1', 'paper:b1:r2')):
    blocks = with_source_spans([{'block_id': 'paper:b0', 'text': 'The observation period is 2021.'},
                               {'block_id': 'paper:b1', 'text': 'Cost is 1 USD. Prices vary by region.'}])
    atoms = [{'atom_id': ids[0], 'block_id': 'paper:b1', 'statement': 'Cost is 1 USD in 2021.',
              'quote': 'Cost is 1 USD. ', 'source_span_ids': ['paper:b1:s1'],
              'qualifications': ['in 2021'], 'intent': 'Fact_Background'},
             {'atom_id': ids[1], 'block_id': 'paper:b1', 'statement': 'Prices vary by region.',
              'quote': 'Prices vary by region.', 'source_span_ids': ['paper:b1:s2'],
              'qualifications': [], 'intent': 'Fact_Background'}]
    candidate = {'block_atoms': [{'block_id': 'paper:b1', 'atoms': atoms}],
                 'relations': [{'source_id': ids[0], 'target_id': ids[1], 'relation': 'Contrast',
                                'rationale': 'The regional variation qualifies the specific price.'}]}
    return {'document_context': '{}', 'source_blocks': json.dumps(blocks)}, candidate


def test_alias_only_change_produces_identical_complete_scientific_model_inputs():
    inputs, canonical = fixture()
    _, alias = fixture(('r6', 'r7'))
    before = copy.deepcopy(canonical)
    old1, actual1, mapping1 = endpoint_inputs(inputs, canonical, 0)
    old2, actual2, mapping2 = endpoint_inputs(inputs, alias, 0)
    assert actual1 == actual2 and old1 != old2 and mapping1 != mapping2
    assert canonical == before
    assert len(json.loads(actual1['source_blocks'])) == 2
    assert len(json.loads(old1['source_blocks'])) == 1


def test_normalization_preserves_every_scientific_endpoint_field():
    inputs, candidate = fixture()
    _, actual, _ = endpoint_inputs(inputs, candidate, 0)
    for name, original in zip(('source_atom', 'target_atom'), candidate['block_atoms'][0]['atoms'], strict=True):
        scientific = json.loads(actual[name])
        assert {key: value for key, value in scientific.items() if key != 'atom_id'} == {
            key: value for key, value in original.items() if key != 'atom_id'}


def test_native_learner_atoms_use_containing_unit_without_rewriting_science():
    inputs, candidate = fixture()
    for atom in candidate['block_atoms'][0]['atoms']:
        del atom['block_id']
    candidate['units'] = copy.deepcopy(candidate['block_atoms'])
    before = copy.deepcopy(candidate)
    _, normalized, _ = endpoint_inputs(inputs, candidate, 0)
    assert candidate == before
    assert len(json.loads(normalized['source_blocks'])) == 2
    for name, atom in zip(('source_atom', 'target_atom'), before['block_atoms'][0]['atoms'], strict=True):
        actual = json.loads(normalized[name])
        assert 'block_id' not in actual
        assert {key: value for key, value in actual.items() if key != 'atom_id'} == {
            key: value for key, value in atom.items() if key != 'atom_id'}


def test_native_atom_cannot_borrow_a_span_from_another_unit():
    inputs, candidate = fixture()
    for atom in candidate['block_atoms'][0]['atoms']:
        del atom['block_id']
    candidate['units'] = copy.deepcopy(candidate['block_atoms'])
    candidate['block_atoms'][0]['atoms'][0]['source_span_ids'] = ['paper:b0:s1']
    with pytest.raises(SourceContractError):
        endpoint_inputs(inputs, candidate, 0)


def test_explicit_conflicting_atom_block_identity_remains_rejected():
    inputs, candidate = fixture()
    candidate['block_atoms'][0]['atoms'][0]['block_id'] = 'paper:b0'
    with pytest.raises(SourceContractError):
        endpoint_inputs(inputs, candidate, 0)


@pytest.mark.parametrize('change', ['qualifier', 'raw_context', 'direction', 'rationale'])
def test_scientific_or_context_change_cannot_hit_the_same_normalized_input(change):
    inputs, candidate = fixture()
    changed_inputs, changed = copy.deepcopy(inputs), copy.deepcopy(candidate)
    if change == 'qualifier':
        changed['block_atoms'][0]['atoms'][0]['qualifications'] = ['in 2022']
    elif change == 'raw_context':
        blocks = json.loads(changed_inputs['source_blocks'])
        blocks[0]['text'] = 'The observation period is 2022.'
        changed_inputs['source_blocks'] = json.dumps(blocks)
    elif change == 'direction':
        edge = changed['relations'][0]
        edge['source_id'], edge['target_id'] = edge['target_id'], edge['source_id']
    else:
        changed['relations'][0]['rationale'] = 'A different scientific relation rationale.'
    assert endpoint_inputs(inputs, candidate, 0)[1] != endpoint_inputs(changed_inputs, changed, 0)[1]


@pytest.mark.parametrize('verdict', ['SUPPORTED', 'UNSUPPORTED', 'UNCERTAIN'])
def test_id_restoration_preserves_actual_support_or_uncertainty(verdict):
    normalized = {'source_id': 'source_endpoint', 'target_id': 'target_endpoint', 'relation': 'Contrast',
                  'verdict': verdict, 'source_evidence_span_ids': ['paper:b1:s1'],
                  'target_evidence_span_ids': ['paper:b1:s2'], 'rationale': 'Actual independent source judgment.'}
    before = copy.deepcopy(normalized)
    restored = restore_verdict(normalized, {'source_endpoint': 'r6', 'target_endpoint': 'r7'})
    assert normalized == before and restored['verdict'] == verdict
    assert restored['source_id'] == 'r6' and restored['target_id'] == 'r7'
    assert restored['rationale'] == normalized['rationale']


def test_model_cannot_reverse_fixed_alias_direction():
    with pytest.raises(SourceContractError):
        restore_verdict({'source_id': 'target_endpoint', 'target_id': 'source_endpoint'},
                        {'source_endpoint': 'r6', 'target_endpoint': 'r7'})


class Predictor:
    signature = __import__('rstv4.skeleton_normalized_endpoint_v2', fromlist=['NormalizedEdgeAssessment']).NormalizedEdgeAssessment

    def __init__(self, verdict):
        self.verdict, self.calls = verdict, []

    def __call__(self, **inputs):
        self.calls.append(inputs)
        return dspy.Prediction(verdict=EndpointVerdict.model_validate({
            'source_id': 'source_endpoint', 'target_id': 'target_endpoint', 'relation': 'Contrast',
            'verdict': self.verdict, 'source_evidence_span_ids': ['paper:b1:s1'],
            'target_evidence_span_ids': ['paper:b1:s2'], 'rationale': 'The raw source leaves this relation uncertain.'}))


def test_source_and_canonical_review_share_one_actual_uncertain_judgment_without_voting(tmp_path):
    inputs, canonical = fixture()
    _, alias = fixture(('r6', 'r7'))
    predictor = Predictor('UNCERTAIN')
    reviewers = []
    for name in ('source-diagnosis', 'complete-source-graph'):
        reviewer = object.__new__(NormalizedEndpointReviewer)
        reviewer.output, reviewer.pair_cache = tmp_path / name, tmp_path / 'same-pair-cache'
        reviewer.lm, reviewer.predictor = dspy.LM('test/model'), predictor
        reviewers.append(reviewer)
    first = reviewers[0].assess(inputs, alias, 0)
    second = reviewers[1].assess(inputs, canonical, 0)
    assert len(predictor.calls) == 1
    assert first['verdict']['verdict'] == second['verdict']['verdict'] == 'UNCERTAIN'
    assert first['normalized_pair_digest'] == second['normalized_pair_digest']
    assert first['verdict']['source_id'] == 'r6'
    assert second['verdict']['source_id'] == 'paper:b1:r1'
    assert second['shared_cache_reuse_is_not_independent_agreement'] is True
