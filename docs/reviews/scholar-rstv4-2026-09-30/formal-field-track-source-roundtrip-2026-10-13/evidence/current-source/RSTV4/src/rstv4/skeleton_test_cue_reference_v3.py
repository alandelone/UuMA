"""Replay byte-identical source history only after complete independent source audit."""
from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_dspy import write_json
from rstv4.skeleton_experiment import validate_reference
from rstv4.skeleton_mapped_graph_v2 import MAPPED_VERIFIED_VERSION
from rstv4.skeleton_test_cue_reference_v2 import PostCompileCueReferenceBuilder as PreviousBuilder

TEST_CUE_REFERENCE_VERSION = 'post-compile-unique-claim-id-and-exact-audited-source-history-v3'


class PostCompileCueReferenceBuilder(PreviousBuilder):
    def __init__(self, *args: Any, historical_source_parent: Path | None = None,
                 source_replay_auditor: Callable[[dict, Path], dict] | None = None,
                 **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.historical_source_parent = historical_source_parent
        self.source_replay_auditor = source_replay_auditor

    def build(self, inputs: dict[str, str]) -> dict:
        key = digest({'version': MAPPED_VERIFIED_VERSION, 'inputs': inputs})
        path = self.output / 'references' / f'{key}.json'
        parent = (self.historical_source_parent / 'references' / f'{key}.json'
                  if self.historical_source_parent is not None else None)
        if parent is None or not parent.exists():
            return super().build(inputs)
        if self.source_replay_auditor is None:
            raise SourceContractError('Exact historical source replay requires independent actual source audit')
        if not path.exists() or path.read_bytes() != parent.read_bytes():
            raise SourceContractError('Historical source record differs from its exact declared parent')
        saved = json.loads(path.read_text(encoding='utf-8'))
        if (saved['inputs_digest'] != digest(inputs) or saved['candidate_access'] is not False
                or saved['source_graph_review_gate_passed'] is not True):
            raise SourceContractError('Historical source raw inputs/isolation/acceptance changed')
        validate_reference(saved['reference'], json.loads(inputs['source_blocks']))
        receipt = self.source_replay_auditor(inputs, path)
        if (receipt['status'] != 'COMPLETE_ACTUAL_SOURCE_REPLAY_AUDIT'
                or receipt['reference_record_digest'] != digest(saved)
                or path.read_bytes() != parent.read_bytes()):
            raise SourceContractError('Historical source actual audit or immutable parent changed')
        write_json(self.output / 'historical-replay-audits' / f'{key}.json', {
            'version': TEST_CUE_REFERENCE_VERSION, 'inputs': inputs, 'inputs_digest': digest(inputs),
            'parent_path': str(parent), 'parent_digest': digest(saved), 'record_digest': digest(saved),
            'actual_source_audit': receipt, 'original_evidence_paths_preserved': True,
            'candidate_access': False, 'held_out_source_access': True, 'after_compile_only': True,
        })
        return copy.deepcopy(saved['reference'])
