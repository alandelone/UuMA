"""Read-only legacy source reconstruction from actual frozen versions and compiler output."""
import hashlib
import json
import sqlite3
from contextlib import closing
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_studio_correspondence import mapped_fixture
from test_studio_response_checks import prepared
from test_writing_studio import wait_for_job

from rstv4.database import transaction
from rstv4.studio_api import create_app
from rstv4.studio_history_origins import read_origins
from rstv4.studio_response_checks import canonical, digest


def record_legacy(service, ms, comment, context, request):
    """Create an explicit old-format fixture BEFORE confirmation; never rewrite a check."""
    legacy = deepcopy(context)
    replacement = {}
    for row in legacy["evidence"]:
        old_id = row["evidence_id"]
        row.pop("origins", None)
        row["evidence_id"] = digest({k:v for k,v in row.items() if k not in {"evidence_id", "display_changed_text"}})
        replacement[old_id] = row["evidence_id"]
    legacy["context_sha256"] = digest({k:v for k,v in legacy.items() if k not in {"context_sha256", "history", "verification"}})
    request = deepcopy(request)
    request["context_sha256"] = legacy["context_sha256"]
    for claim in request["claims"]:
        claim["evidence_ids"] = [replacement[identifier] for identifier in claim["evidence_ids"]]
    original = service.response_review_context
    service.response_review_context = lambda *args: legacy
    try:
        result = service.confirm_response_review(ms, comment, request)
    finally:
        service.response_review_context = original
    return result, legacy


@pytest.fixture(scope="module")
def legacy_fixture(tmp_path_factory):
    service, ms, comment, context, request, document, _ = prepared(tmp_path_factory.mktemp("legacy-origins"))
    result, legacy = record_legacy(service, ms, comment, context, request)
    expected = next(r for r in context["evidence"] if r["status"] == "GENERATED_TEXT_CHANGED")["origins"][0]
    evidence_id = result["history"][0]["request"]["claims"][0]["evidence_ids"][0]
    later = deepcopy(document)
    later["sections"][0]["paragraphs"][0]["intents"][0]["label"] = "CURRENT MUTABLE LABEL"
    later["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"][0]["text"] = "Current mutable wording."
    service.save_document(ms, base_revision=2, operation_id="historical-later-author", document=later)
    service._executor.shutdown(wait=True)
    yield service, ms, comment, result["check_id"], evidence_id, expected, legacy


def tables(path):
    with closing(sqlite3.connect(path)) as conn:
        return {name:sorted(conn.execute(f'SELECT * FROM "{name}"').fetchall(),key=repr)
                for name, in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def files(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and not p.name.endswith(('-wal','-shm'))}


def route(ms, comment, check, evidence):
    return f"/api/manuscripts/{ms}/comments/{comment}/response-checks/{check}/origins/{evidence}"


def test_http_reconstructs_exact_old_thought_after_current_edits_without_any_table_or_file_write(legacy_fixture):
    service, ms, comment, check, evidence, expected, original_context = legacy_fixture
    with TestClient(create_app(service.root)) as client:
        with closing(sqlite3.connect(service.db_path)) as conn:
            assert conn.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0] == 0
        before_tables, before_files = tables(service.db_path), files(service.root)
        first = client.get(route(ms,comment,check,evidence))
        second = client.get(route(ms,comment,check,evidence))
        assert first.status_code == second.status_code == 200
        actual = first.json()
        assert actual == second.json() and actual["status"] == "RECONSTRUCTED_FROM_FIXED_INPUT"
        assert actual["origins"] == [expected]
        assert actual["source"]["input_revision"] == 2
        assert actual["source"]["author_document_sha256"] == original_context["state"]["current_author_document_sha256"]
        assert actual["original_context_sha256"] == original_context["context_sha256"]
        assert tables(service.db_path) == before_tables and files(service.root) == before_files
        assert service.list_comments(ms)[0]["response_verification"]["status"] == "STALE"


@pytest.mark.parametrize("field", ["manuscript", "comment", "check", "evidence"])
def test_cross_owner_and_unknown_id_reads_are_scoped_404(legacy_fixture, field):
    service, ms, comment, check, evidence, *_ = legacy_fixture
    args = [ms,comment,check,evidence]
    args[["manuscript","comment","check","evidence"].index(field)] = "unknown-or-foreign"
    with TestClient(create_app(service.root)) as client:
        assert client.get(route(*args)).status_code == 404


def rewrite_fixture_context(conn, check_id, mutate):
    row = conn.execute('SELECT * FROM studio_response_checks WHERE check_id=?',(check_id,)).fetchone()
    context, request = json.loads(row['context_json']), json.loads(row['request_json'])
    mutate(context)
    state_sha = digest(context['state'])
    context['state_sha256'] = state_sha
    context['context_sha256'] = digest({k:v for k,v in context.items() if k != 'context_sha256'})
    request['context_sha256'] = context['context_sha256']
    conn.execute('UPDATE studio_response_checks SET context_json=?,request_json=?,context_sha256=?,state_sha256=? WHERE check_id=?',
                 (canonical(context),canonical(request),context['context_sha256'],state_sha,check_id))


@pytest.mark.parametrize("invalid", ["context", "missing_fixed_hash", "record", "author_serialization", "model_call",
                                      "wrong_thought", "duplicate_evidence", "missing_revision", "stored_wrong_origin"])
def test_corrupt_or_insufficient_fixed_proof_never_uses_latest_fallback(legacy_fixture, invalid):
    service, ms, comment, check, evidence, *_ = legacy_fixture
    before = tables(service.db_path)
    with transaction(service.db_path) as conn:
        conn.execute('BEGIN')
        if invalid == 'context':
            conn.execute('UPDATE studio_response_checks SET context_json=? WHERE check_id=?',('{}',check))
        elif invalid == 'missing_fixed_hash':
            rewrite_fixture_context(conn,check,lambda c:c['state'].pop('generated_record_sha256'))
        elif invalid == 'record':
            conn.execute("UPDATE manuscript_versions SET inputs_json=inputs_json || ' ' WHERE manuscript_version_id=(SELECT generated_version_id FROM studio_response_checks WHERE check_id=?)",(check,))
        elif invalid == 'author_serialization':
            conn.execute("UPDATE studio_changes SET after_json=after_json || ' ' WHERE operation_id='map-author-2'")
        elif invalid == 'model_call':
            conn.execute("UPDATE studio_model_calls SET input_json='{}' WHERE input_revision=2")
        elif invalid == 'wrong_thought':
            rewrite_fixture_context(conn,check,lambda c:c['evidence'][0].update(thought_id='not-recorded'))
        elif invalid == 'duplicate_evidence':
            rewrite_fixture_context(conn,check,lambda c:c['evidence'].append(deepcopy(c['evidence'][0])))
        elif invalid == 'missing_revision':
            rewrite_fixture_context(conn,check,lambda c:c['state'].update(generated_input_revision=None))
        else:
            rewrite_fixture_context(conn,check,lambda c:c['evidence'][0].update(origins=[{'thought_text':'invented'}]))
        result = read_origins(conn,service.storage_root,ms,comment,check,evidence)
        assert result['status'] in {'UNAVAILABLE','AMBIGUOUS'} and result['origins'] == []
        conn.rollback()
    assert tables(service.db_path) == before


def test_original_pdf_absence_does_not_force_recompilation_for_verified_source_read(legacy_fixture):
    service, ms, comment, check, evidence, expected, context = legacy_fixture
    view = service.get_generated_version(ms,context['state']['generated_version_id'])
    pdf = Path(next(a['storage_path'] for a in view['artifacts'] if a['artifact_kind']=='PDF'))
    original = pdf.read_bytes()
    pdf.unlink()
    try:
        before = files(service.root)
        result = service.historical_response_origins(ms,comment,check,evidence)
        assert result['status'] == 'RECONSTRUCTED_FROM_FIXED_INPUT' and result['origins'] == [expected]
        assert files(service.root) == before
    finally:
        pdf.write_bytes(original)


def test_real_template_projection_shared_sentence_reads_original_author_bank(tmp_path):
    service, ms, _, mapped, _, _ = mapped_fixture(tmp_path)
    first_intent = next(p for s in mapped['sections'] if s.get('placement_status')=='UNPLACED' for p in s['paragraphs'])['intents'][0]
    second = deepcopy(first_intent['thoughts'][0]);second.update(id='historical-shared-thought-two',text='Independent original software qualification.')
    first_intent['thoughts'].append(second)
    service.save_document(ms,base_revision=3,operation_id='history-place-originals',document=mapped)
    phase = ['Earlier']
    def generate(task,payload):
        ts = [t for i in payload['intents'] for t in i['thoughts']]
        refs = list(dict.fromkeys(c['evidence_id'] for t in ts for c in t['citations'] if c['selected']))
        sentence = f"{phase[0]} software paragraph for {ts[0]['id']} preserves conditions" + ''.join(f" [@{ref}]" for ref in refs) + '.'
        return {'paragraph':sentence,'sentences':[sentence],'sentence_mappings':[{'sentence':0,'thought_ids':[t['id'] for t in ts]}]}
    service.gateway.analyze = generate
    baseline_job = wait_for_job(service,service.create_job(ms,'GENERATE',input_revision=4))
    assert baseline_job['status']=='SUCCEEDED', baseline_job
    review=service.create_review_round(ms,round_number=1,venue='Legacy template software fixture')
    comment=service.import_comments(review['review_round_id'],[{'text':'Clarify both original thoughts.'}],source='FIXTURE')[0]['comment_id']
    for t in first_intent['thoughts']:t['text'] += ' Clarified original qualification.'
    service.save_document(ms,base_revision=4,operation_id='history-clarified-originals',document=mapped,comment_ids=[comment])
    phase[0]='Updated'
    target_job = wait_for_job(service,service.create_job(ms,'GENERATE',input_revision=5))
    assert target_job['status']=='SUCCEEDED', target_job
    service.update_comment(comment,{'response_text':'We clarified both original thoughts.','author_decision':'Software provenance only.'})
    context=service.response_review_context(ms,comment)
    rows=[r for r in context['evidence'] if r['status']=='GENERATED_TEXT_CHANGED']
    assert len(rows)==2 and rows[0]['changed_text']==rows[1]['changed_text'] and rows[0]['boxes']==rows[1]['boxes']
    assert all(r['paragraph_id']!=r['origins'][0]['paragraph_id'] for r in rows)
    text=context['state']['response_text']
    request={'request_id':'legacy-projected-shared-fixture','context_sha256':context['context_sha256'],'outcome':'MODIFIED',
             'claims':[{'start':0,'end':len(text),'text':text,'offset_unit':'utf16','evidence_ids':[r['evidence_id'] for r in rows]}],
             'acknowledged_all_assertions':True}
    result,_=record_legacy(service,ms,comment,context,request)
    identifiers=result['history'][0]['request']['claims'][0]['evidence_ids']
    origins=[service.historical_response_origins(ms,comment,result['check_id'],identifier) for identifier in identifiers]
    assert all(x['status']=='RECONSTRUCTED_FROM_FIXED_INPUT' for x in origins)
    assert origins[0]['origins'][0]['thought_id'] != origins[1]['origins'][0]['thought_id']
    assert all(x['origins'][0]['intent_id']==first_intent['id'] for x in origins)
    assert all(x['origins'][0]['intent_thoughts']==[{'thought_id':t['id'],'text':t['text']} for t in first_intent['thoughts']] for x in origins)
    service._executor.shutdown(wait=True)
