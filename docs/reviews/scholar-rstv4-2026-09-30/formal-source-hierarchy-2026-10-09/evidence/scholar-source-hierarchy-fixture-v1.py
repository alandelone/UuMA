"""New isolated software-only source and author fixture; leave prior native workspaces intact."""
import hashlib
import json
import shutil
import sqlite3
import tempfile
from copy import deepcopy
from pathlib import Path

from rstv4.acquisition import AcquisitionService
from rstv4.database import initialize_catalog, transaction
from rstv4.models import (CollectionCreateInput, FieldInput, TrackFirstEvidenceInput,
                          TrackFirstTopicInput, TrackFirstTrackInput, new_id)
from rstv4.parser_quality import normalize_mineru_result
from rstv4.research_views import skeleton_source
from rstv4.studio import StudioService

repo = Path(__file__).resolve().parents[1]
baseline = json.loads((repo / '.tmp/scholar-source-hierarchy-before-v1/baseline.json').read_text(encoding='utf-8'))
old_db = Path(baseline['database'])
old_root = old_db.parents[1]
root = Path(tempfile.mkdtemp(prefix='scui-source-hierarchy-native-')).resolve()
assert root.parent == Path(tempfile.gettempdir()).resolve()
shutil.copytree(old_root, root, dirs_exist_ok=True,
                ignore=lambda directory, names: [n for n in names if n == 'catalog.db' or n.endswith(('-wal', '-shm'))])
db = root / 'data/catalog.db'
with sqlite3.connect(f'file:{old_db.as_posix()}?mode=ro', uri=True) as conn:
    conn.row_factory = sqlite3.Row
    before = {r[0]: [dict(v) for v in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')]
              for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
    assert before == baseline['tables'], 'Existing native fixture changed; review before copying'
    with sqlite3.connect(db) as target:
        conn.backup(target)
    legacy_sources = {r[0]: skeleton_source(conn, r[0]) for r in conn.execute('SELECT skeleton_id FROM paper_skeletons')}
initialize_catalog(db)
with transaction(db) as conn:
    migrated = {r[0]: [dict(v) for v in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')]
                for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
    assert all(migrated[t] == values for t, values in before.items() if t != 'schema_version')
    assert migrated['skeleton_source_outlines'] == []
    assert {key: skeleton_source(conn, key) for key in legacy_sources} == legacy_sources
    assert not conn.execute('PRAGMA foreign_key_check').fetchone()
service = StudioService(root)
acquisition = AcquisitionService(root)
field = service.track_service.create_field(FieldInput(name='Source hierarchy software fixture Field'))
topic = service.track_service.create_topic(TrackFirstTopicInput(field_id=field['field_id'], name='Source hierarchy software fixture'))
track = service.track_service.create_track(TrackFirstTrackInput(
    field_id=field['field_id'], primary_topic_id=topic['topic_id'],
    title='Source hierarchy software fixture Track', research_type='conceptual_framework'))
paper_id, file_id = new_id('paper'), new_id('source_file')
pdf = root / 'software-source-hierarchy.pdf'
pdf.write_bytes(b'%PDF-1.4 explicitly synthetic source hierarchy software fixture; not a scholarly PDF')
timestamp = '2026-10-09T00:00:00+00:00'
with transaction(db) as conn:
    conn.execute('INSERT INTO papers VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (
        paper_id, paper_id, None, 'source hierarchy software fixture', 'Source hierarchy software fixture',
        '["Software Fixture"]', 2026, 'Synthetic structural fixture only', None, None, timestamp, timestamp))
    conn.execute('INSERT INTO source_file_versions VALUES(?,?,?,?,?,?,?,?,?,?,?)', (
        file_id, paper_id, hashlib.sha256(pdf.read_bytes()).hexdigest(), pdf.stat().st_size,
        'application/pdf', str(pdf), 'SOFTWARE_FIXTURE', None, 'VERIFIED',
        json.dumps({'software_only': True, 'scientific_approval': False}), timestamp))
collection = acquisition.create_collection(CollectionCreateInput.model_validate({
    'field_id': field['field_id'], 'topic_id': topic['topic_id'], 'track_id': track['track_id'],
    'name': 'Source hierarchy software-only fixture', 'dois': [], 'paper_ids': [paper_id],
    'idempotency_key': 'source-hierarchy-software-fixture-v1'}))
items = []
for index, (title, level) in enumerate([('Source Alpha Ω', 1), ('Repeated source heading', 2),
                                       ('Source Detail Ω', 3), ('Repeated source heading', 2),
                                       ('Source Omega Ω', 1)]):
    items.extend([{'type': 'text', 'text_level': level, 'text': title, 'page_idx': index,
                   'bbox': [10, 20, 300, 40]},
                  {'type': 'text', 'text': f'SOFTWARE_SOURCE_BODY_{index}_NEVER_AUTHOR_TEXT. '
                   'This content is synthetic structural test material, without scientific claims.',
                   'page_idx': index, 'bbox': [10, 50, 300, 120]}])
markdown = root / 'software-source-hierarchy.md'
content = root / 'software-source-hierarchy-content.json'
markdown.write_text('Synthetic source hierarchy software fixture', encoding='utf-8')
content.write_text(json.dumps(items, ensure_ascii=False), encoding='utf-8')
normalized = normalize_mineru_result({'manifest': {'markdown_path': str(markdown),
                                       'content_list_path': str(content)}, 'blocks': [], 'references': []})
parsed = acquisition.publish_parse_result(collection['collection_id'], paper_id, file_id,
    parser_name='SOFTWARE_EXPLICIT_MINERU_CONTENT', parser_version='1', config={'software_only': True},
    manifest=normalized['manifest'], blocks=normalized['blocks'], references=normalized['references'])
with transaction(db) as conn:
    units = [{'block_id': b['block_id'], 'raw_text': b['text'], 'page_number': b['page_number'],
              'section': b['section'], 'layer1': {'triplets': []},
              'layer2': {'discourse_relation': 'Context', 'software_only': True},
              'layer3': {'intent': 'Section_Context' if b['block_type'] == 'HEADING' else 'Software_Claim'},
              'layer4': {'role': 'Software_Test'}} for b in conn.execute(
                  'SELECT * FROM document_blocks WHERE parse_run_id=? ORDER BY sequence', (parsed['parse_run_id'],))]
published = acquisition.publish_skeleton_result(parsed['parse_run_id'], units, model_name='TEST_FIXTURE')
evidence = service.track_service.add_evidence(TrackFirstEvidenceInput(
    track_id=track['track_id'], paper_id=paper_id, statement='Synthetic hierarchy software fixture',
    excerpt='Synthetic source only', location='software fixture page 1', confidence=0.8,
    relation='SUPPORTS', extractor_model='TEST_FIXTURE', prompt_version='TEST_FIXTURE'))
workspace = service.create_manuscript(track['track_id'], 'Source hierarchy native acceptance Ω — software fixture')
manuscript_id = workspace['manuscript']['manuscript_id']
document = deepcopy(workspace['document'])
section = document['sections'][0]
section['title'] = 'Original author root Ω'
paragraph = section['paragraphs'][0]
paragraph.update(purpose='Original author purpose Ω', paradigm='Original author organization',
                 logical_relation='Author comparison', logic={'discourse_relation': 'Author comparison'})
paragraph['intents'][0].update(label='Original author intent', thoughts=[{
    'id': new_id('thought'), 'text': 'AUTHOR original wording Ω with its selected software citation.',
    'citation_mode': 'SELECTED', 'citations': [{'evidence_id': evidence['evidence_id'], 'selected': True}]}])
paragraph['formulas'] = [{'id': new_id('formula'), 'latex': 'x=1', 'caption': 'Original author formula'}]
asset = service.store_asset(manuscript_id, 'author-software-table.csv', 'text/csv', b'x,y\n1,2\n')
paragraph['asset_ids'] = [asset['asset_id']]
second = deepcopy(paragraph)
second['id'] = new_id('paragraph')
second['intents'][0]['id'] = new_id('intent')
second['intents'][0]['thoughts'][0]['id'] = new_id('thought')
second['intents'][0]['thoughts'][0]['text'] = 'AUTHOR second original wording stays independent.'
second['formulas'][0]['id'] = new_id('formula')
section['paragraphs'].append(second)
group_id = new_id('paragraph_group')
section.update(paragraph_groups=[{'id': group_id, 'label': 'Original author group Ω',
                'paragraph_ids': [paragraph['id'], second['id']]}], block_order=[group_id])
document['argument_relations'] = [{'id': new_id('argument_relation'), 'source_id': paragraph['id'],
    'target_id': second['intents'][0]['thoughts'][0]['id'], 'relation': 'Author comparison Ω',
    'condition': 'Software-only relation condition Ω'}]
service.save_document(manuscript_id, base_revision=0, operation_id='source-hierarchy-fixture-author-v1', document=document)
preview = service.preview_template(manuscript_id, published['skeleton_id'])
with transaction(db) as conn:
    after = {r[0]: [dict(v) for v in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')]
              for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
    for table, old in before.items():
        if table != 'schema_version':
            assert after[table][:len(old)] == old, table
    for table in ['approval_grants', 'acquisition_model_call_events', 'studio_model_calls', 'studio_jobs']:
        assert after[table] == before[table], table
    assert not conn.execute('PRAGMA foreign_key_check').fetchone()
assert hashlib.sha256(Path(baseline['golden_database']).read_bytes()).hexdigest() == baseline['golden_sha256']
receipt = {'root': str(root), 'database': str(db), 'prior_runtime_root': str(old_root),
           'manuscript_id': manuscript_id, 'skeleton_id': published['skeleton_id'],
           'paper_id': paper_id, 'parsed': parsed, 'preview': preview, 'initial_document': document,
           'before_tables': before, 'after_fixture_tables': after, 'legacy_sources_exact': legacy_sources,
           'schema_version': 13, 'old_table_count': len(before), 'new_table_count': len(after),
           'migrated_old_rows_unchanged': True, 'scientific_approval': False,
           'actual_model_calls_added': 0, 'download_tests_paused': True}
(repo / '.tmp/scholar-source-hierarchy-fixture-v1.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
service._executor.shutdown(wait=True)
print(json.dumps({key: receipt[key] for key in ['root', 'manuscript_id', 'skeleton_id', 'schema_version',
      'old_table_count', 'new_table_count', 'migrated_old_rows_unchanged', 'scientific_approval', 'actual_model_calls_added']}))
