from pathlib import Path
import pytest
from uuma.knowledge_service import KnowledgeService, StaleKnowledgeError
from uuma.knowledge_models import (SourceRecord, ClaimRecord, EntityRecord, RelationRecord, KnowledgePatch, PatchOperation, PatchOperationKind, ResearchRun, ConflictRecord)
from uuma.kag_adapter import KagProjectionWorker, KnowledgeReasoner, KagUnavailableError

W = 'wisdom-oldman'
O = 'orchestrator'

@pytest.fixture
def service(tmp_path):
    return KnowledgeService(tmp_path / 'wisdom.db')

def proposal(s, kind, target, changes=None):
    return s.propose_patch(KnowledgePatch(operations=[PatchOperation(kind=kind, target_id=target, changes=changes or {})], rationale='Isolated contract probe', proposed_by=W), actor_id=W)

def accept(s, kind, target):
    p = proposal(s, kind, target)
    return s.apply_patch(p['patch_id'], actor_id=O, review_note='Fixture approval')

class Backend:
    def health(self):
        return {'ready': True}
    def apply(self, job):
        return {'applied': True}

class Offline(Backend):
    def health(self):
        raise KagUnavailableError('Isolated offline fixture')

def test_interrupted_projection_is_recoverable(service):
    service.add_source(SourceRecord(locator='urn:test:crash', title='Fixture'), actor_id=W)
    job = service.store.pending_projection_jobs()[0]
    service.store.mark_projection_job(job['projection_job_id'], status='RUNNING')
    with service.store.transaction() as conn:
        conn.execute(
            "UPDATE projection_outbox SET updated_at = ? WHERE projection_job_id = ?",
            ("2000-01-01T00:00:00+00:00", job['projection_job_id']),
        )
    # Simulate termination after persistent RUNNING, then create a new worker/store.
    reopened = KnowledgeService(service.store.path)
    result = KagProjectionWorker(reopened, Backend()).sync(recover=False)
    assert result['lag'] == 0, result

def test_reversing_entity_cannot_leave_accepted_relation(service):
    a = service.propose_entity(EntityRecord(canonical_name='A', entity_type='Thing'), actor_id=W)
    b = service.propose_entity(EntityRecord(canonical_name='B', entity_type='Thing'), actor_id=W)
    pa = accept(service, PatchOperationKind.ACCEPT_ENTITY, a['entity_id'])
    accept(service, PatchOperationKind.ACCEPT_ENTITY, b['entity_id'])
    r = service.propose_relation(RelationRecord(subject_entity_id=a['entity_id'], predicate='dependsOn', object_entity_id=b['entity_id']), actor_id=W)
    accept(service, PatchOperationKind.ACCEPT_RELATION, r['relation_id'])
    try:
        service.reverse_patch(pa['patch_id'], actor_id=O, review_note='Withdraw entity approval')
    except (ValueError, StaleKnowledgeError):
        return  # Rejecting withdrawal is one valid way to preserve dependencies.
    graph = service.graph_neighborhood(b['entity_id'])
    accepted_entities = {e['entity_id'] for e in graph['entities'] if e['status'] == 'ACCEPTED'}
    assert all(r['subject_entity_id'] in accepted_entities and r['object_entity_id'] in accepted_entities for r in graph['relations']), graph

def test_budget_exhaustion_pauses_run(service):
    run = service.start_research_run(ResearchRun(objective='Fixture research', satisfaction_rationale='Probe', budget_tier='QUICK', status='ACTIVE'), actor_id=W)
    after = service.update_research_run(run['research_run_id'], {'active_seconds': 601, 'sources_used': 11, 'model_tokens_used': 50001}, actor_id=W)
    assert after['status'] == 'BUDGET_EXHAUSTED', after

def test_fallback_preserves_conditions_and_known_conflicts(service):
    a = service.propose_claim(ClaimRecord(statement='Battery lifetime is 1000 cycles.', qualifiers={'temperature': '25 C', 'discharge_rate': '0.5 C'}), actor_id=W)
    b = service.propose_claim(ClaimRecord(statement='Battery lifetime is 200 cycles.', qualifiers={'temperature': '25 C', 'discharge_rate': '0.5 C'}), actor_id=W)
    accept(service, PatchOperationKind.ACCEPT_CLAIM, a['claim_id'])
    accept(service, PatchOperationKind.ACCEPT_CLAIM, b['claim_id'])
    service.record_conflict(ConflictRecord(claim_ids=[a['claim_id'], b['claim_id']], description='Unresolved battery lifetime disagreement'), actor_id=W)
    answer = KnowledgeReasoner(service, Offline()).answer('Battery lifetime', recover=False)
    assert '25 C' in str(answer) and answer['conflicts'], answer

def test_supersession_checks_replacement_snapshot(service):
    a = service.propose_claim(ClaimRecord(statement='Old fixture claim.'), actor_id=W)
    b = service.propose_claim(ClaimRecord(statement='Reviewed replacement.'), actor_id=W)
    accept(service, PatchOperationKind.ACCEPT_CLAIM, a['claim_id'])
    replace = proposal(service, PatchOperationKind.SUPERSEDE_CLAIM, a['claim_id'], {'replacement_claim_id': b['claim_id']})
    update = proposal(service, PatchOperationKind.UPDATE_CLAIM, b['claim_id'], {'statement': 'Changed after supersession review.'})
    service.apply_patch(update['patch_id'], actor_id=O, review_note='Independent intervening edit')
    with pytest.raises(StaleKnowledgeError):
        service.apply_patch(replace['patch_id'], actor_id=O, review_note='Apply original reviewed proposal')

class RecordingExtractor(Backend):
    def __init__(self):
        self.seen = []
    def extract(self, chunks):
        self.seen.append([c['chunk_id'] for c in chunks])
        return {'chunks': [{'chunk_id': c['chunk_id'], 'entities': [], 'relations': []} for c in chunks]}

def test_repeated_extraction_can_reach_document_tail(service, tmp_path):
    from uuma.knowledge_ingest import KnowledgeIngestor
    from uuma.knowledge_construction import KnowledgeConstructor
    doc = KnowledgeIngestor(service, tmp_path / 'content').ingest_text(locator='urn:test:long', title='Long fixture', text='alpha beta gamma ' * 8000, actor_id=W)
    backend = RecordingExtractor()
    constructor = KnowledgeConstructor(service, backend)
    offset = 0
    while offset is not None:
        result = constructor.extract_document(
            doc['document']['document_id'],
            max_chunks=100,
            offset=offset,
            recover=False,
        )
        offset = result['next_offset']
    seen = set(x for batch in backend.seen for x in batch)
    assert len(seen) == len(doc['chunks']), {'unique_processed': len(seen), 'total_chunks': len(doc['chunks'])}
