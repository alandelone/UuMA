"""One actual endpoint criterion with fixed aliases and complete source-window context."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import dspy
from dspy.utils.exceptions import AdapterParseError

from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_dspy import ReceiptLM, json_text, write_json
from rstv4.skeleton_endpoint_review import (
    ENDPOINT_REVIEW_VERSION,
    RELATION_ONTOLOGY,
    ActualEdgeAssessment,
    atom_index,
    validate_endpoint_verdict,
)

NORMALIZED_ENDPOINT_VERSION = 'fixed-endpoint-aliases-complete-raw-window-actual-review-v2'
ENDPOINT_IDENTITY_CONTRACT = '''
source_endpoint and target_endpoint are fixed request-local aliases for the actual two
propositions. They carry no scientific meaning or ordering beyond the supplied direction.
Echo them exactly. All statement, qualification, quote and source-span fields are original.
source_blocks contains the COMPLETE raw window, including fragments before/after the
endpoint blocks and intervening figures/tables. Use it to understand the actual sentence
boundary and scope; other blocks are context, not replacement endpoint propositions.
Each endpoint's supporting evidence must still belong to that atom's own source_span_ids.
Judge the relation and direction under the unchanged ontology. A discourse connective or
candidate rationale alone does not establish a relation. Preserve actual uncertainty.
'''


class NormalizedEdgeAssessment(ActualEdgeAssessment):
    endpoint_identity_contract: str = dspy.InputField()


NormalizedEdgeAssessment = NormalizedEdgeAssessment.with_instructions(
    ActualEdgeAssessment.instructions + ENDPOINT_IDENTITY_CONTRACT,
)


def endpoint_inputs(inputs: dict, candidate: dict, index: int) -> tuple[dict, dict, dict]:
    edge = candidate['relations'][index]
    atoms = atom_index(candidate)
    source_block, source = atoms[edge['source_id']]
    target_block, target = atoms[edge['target_id']]
    if edge['source_id'] == edge['target_id']:
        raise SourceContractError('Endpoint source and target must identify distinct atoms')
    blocks = json.loads(inputs['source_blocks'])
    if len({block['block_id'] for block in blocks}) != len(blocks):
        raise SourceContractError('Complete endpoint source window repeats a block')
    selected = [block for block in blocks if block['block_id'] in {source_block, target_block}]
    if {block['block_id'] for block in selected} != {source_block, target_block}:
        raise SourceContractError('Actual endpoint source block is absent')
    for block_id, atom in ((source_block, source), (target_block, target)):
        block = next(block for block in blocks if block['block_id'] == block_id)
        if (atom['block_id'] != block_id or not atom['source_span_ids']
                or not set(atom['source_span_ids']) <= {span['span_id'] for span in block['source_spans']}):
            raise SourceContractError('Endpoint scientific source scope changed')
    legacy = {'document_context': inputs['document_context'], 'source_blocks': json_text(selected),
              'source_atom': json_text(source), 'target_atom': json_text(target),
              'candidate_edge': json_text(edge), 'relation_ontology': RELATION_ONTOLOGY}
    normalized_source, normalized_target, normalized_edge = map(copy.deepcopy, (source, target, edge))
    normalized_source['atom_id'], normalized_target['atom_id'] = 'source_endpoint', 'target_endpoint'
    normalized_edge['source_id'], normalized_edge['target_id'] = 'source_endpoint', 'target_endpoint'
    normalized = {'document_context': inputs['document_context'], 'source_blocks': json_text(blocks),
                  'source_atom': json_text(normalized_source), 'target_atom': json_text(normalized_target),
                  'candidate_edge': json_text(normalized_edge), 'relation_ontology': RELATION_ONTOLOGY,
                  'endpoint_identity_contract': ENDPOINT_IDENTITY_CONTRACT}
    mapping = {'source_endpoint': edge['source_id'], 'target_endpoint': edge['target_id']}
    return legacy, normalized, mapping


def restore_verdict(normalized: dict, mapping: dict) -> dict:
    if set(mapping) != {'source_endpoint', 'target_endpoint'} or len(set(mapping.values())) != 2:
        raise SourceContractError('Normalized endpoint original-ID mapping changed')
    value = copy.deepcopy(normalized)
    if value['source_id'] != 'source_endpoint' or value['target_id'] != 'target_endpoint':
        raise SourceContractError('Actual model must echo the fixed endpoint aliases exactly')
    value['source_id'], value['target_id'] = mapping['source_endpoint'], mapping['target_endpoint']
    return value


class NormalizedEndpointReviewer:
    def __init__(self, output: Path, *, actual_model: str, pair_cache: Path | None = None) -> None:
        self.output = output
        self.pair_cache = pair_cache or output / 'normalized-pairs'
        self.lm = ReceiptLM('thinking', self.pair_cache / 'teacher-lm', max_tokens=4000,
                            required_actual_model=actual_model)
        self.predictor = dspy.Predict(NormalizedEdgeAssessment)

    def assess(self, inputs: dict[str, str], candidate: dict[str, Any], relation_index: int) -> dict:
        legacy, normalized, mapping = endpoint_inputs(inputs, candidate, relation_index)
        # The original scientific lookup remains a declared compatibility projection;
        # actual model inputs and their new protocol are separately, explicitly bound.
        key = digest({'version': ENDPOINT_REVIEW_VERSION, 'inputs': legacy})
        pair_key = digest({'version': NORMALIZED_ENDPOINT_VERSION, 'inputs': normalized})
        path = self.output / 'edges' / f'{key}.json'
        pair_path = self.pair_cache / 'records' / f'{pair_key}.json'
        if pair_path.exists():
            pair = json.loads(pair_path.read_text(encoding='utf-8'))
            if (pair['version'] != NORMALIZED_ENDPOINT_VERSION or pair['initial_inputs'] != normalized
                    or pair['input_digest'] != pair_key or pair['signature_digest'] != digest(self.predictor.signature.instructions)):
                raise SourceContractError('Actual normalized endpoint cache/protocol changed')
        else:
            attempts, feedback, pair = [], '', None
            for number in range(3):
                actual = {**normalized, 'repair_feedback': feedback}
                attempt = {'number': number + 1, 'inputs': actual, 'inputs_digest': digest(actual),
                           'model_output': None}
                try:
                    with dspy.context(lm=self.lm, adapter=dspy.JSONAdapter()):
                        result = self.predictor(**actual)
                    attempt['model_output'] = {'verdict': result.verdict.model_dump()}
                    validate_endpoint_verdict(json.loads(normalized['candidate_edge']),
                                              json.loads(normalized['source_atom']),
                                              json.loads(normalized['target_atom']),
                                              attempt['model_output']['verdict'])
                except (AdapterParseError, SourceContractError, ValueError, TypeError) as error:
                    attempt['protocol_error'] = str(error)[:2500]
                    attempts.append(attempt)
                    feedback = 'Own endpoint output field/domain violation only: ' + attempt['protocol_error']
                    continue
                attempts.append(attempt)
                pair = {'version': NORMALIZED_ENDPOINT_VERSION, 'initial_inputs': normalized,
                        'input_digest': pair_key, 'signature_digest': digest(self.predictor.signature.instructions),
                        'status': 'ASSESSED', 'verdict': attempt['model_output']['verdict'], 'attempts': attempts}
                break
            if pair is None:
                pair = {'version': NORMALIZED_ENDPOINT_VERSION, 'initial_inputs': normalized,
                        'input_digest': pair_key, 'signature_digest': digest(self.predictor.signature.instructions),
                        'status': 'EVALUATION_CONTRACT_FAILURE', 'verdict': None, 'attempts': attempts}
            write_json(pair_path, pair)
        if pair['status'] == 'ASSESSED':
            validate_endpoint_verdict(json.loads(normalized['candidate_edge']), json.loads(normalized['source_atom']),
                                      json.loads(normalized['target_atom']), pair['verdict'])
            verdict = restore_verdict(pair['verdict'], mapping)
            validate_endpoint_verdict(json.loads(legacy['candidate_edge']), json.loads(legacy['source_atom']),
                                      json.loads(legacy['target_atom']), verdict)
        else:
            verdict = None
        record = {'version': ENDPOINT_REVIEW_VERSION, 'protocol_version': NORMALIZED_ENDPOINT_VERSION,
                  'input_digest': key, 'original_inputs': legacy, 'complete_window_digest': digest(inputs),
                  'original_id_mapping': mapping, 'normalized_input_digest': pair_key,
                  'normalized_pair_path': str(pair_path), 'normalized_pair_digest': digest(pair),
                  'status': pair['status'], 'verdict': verdict,
                  'failed_attempts': [{'attempt': attempt['number'], 'error': attempt['protocol_error']}
                                      for attempt in pair['attempts'] if attempt.get('protocol_error')],
                  'shared_cache_reuse_is_not_independent_agreement': True}
        if path.exists() and json.loads(path.read_text(encoding='utf-8')) != record:
            raise SourceContractError('Normalized endpoint original scientific projection changed')
        if not path.exists():
            write_json(path, record)
        return record
