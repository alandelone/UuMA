"""Create explicitly synthetic template data, never source/science approval, in the owned clone."""
import hashlib
import json
import sqlite3
import subprocess
from copy import deepcopy
from pathlib import Path

from rstv4.database import transaction
from rstv4.models import (FieldInput, FieldKGBuildInput, TrackFirstEvidenceInput,
                          TrackFirstTopicInput, TrackFirstTrackInput, new_id)
from rstv4.studio import StudioService

repo = Path(__file__).resolve().parents[1]
info = json.loads((repo / '.tmp/scholar-revision-isolated-services-v1.json').read_text())
root = Path(info['root']).resolve()
assert root.name == 'scui-revision-native-p48co4i6'
assert hashlib.sha256((Path(info['golden_root']) / 'data/catalog.db').read_bytes()).hexdigest() == info['golden_database_sha256']
owner = json.loads(subprocess.run(['powershell', '-NoProfile', '-Command',
    "[pscustomobject]@{Root=(Get-CimInstance Win32_Process -Filter 'ProcessId=82248' | Select-Object ProcessId,CommandLine); Child=(Get-CimInstance Win32_Process -Filter 'ProcessId=83352' | Select-Object ProcessId,ParentProcessId,CommandLine); Listener=(Get-NetTCPConnection -State Listen -LocalPort 8877 | Select-Object OwningProcess)} | ConvertTo-Json -Depth 5"],
    capture_output=True, text=True, check=True).stdout)
assert owner['Root']['ProcessId'] == owner['Child']['ParentProcessId'] == 82248
assert owner['Child']['ProcessId'] == owner['Listener']['OwningProcess'] == 83352
assert all('scholar-revision-isolated-services-v1.py' in owner[key]['CommandLine'] for key in ['Root', 'Child'])
before = json.loads((repo / '.tmp/scholar-template-native-before-v2.json').read_text(encoding='utf-8'))
service = StudioService(root)
with transaction(service.db_path) as conn:
    for table, rows in before['tables'].items():
        assert [dict(row) for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid')] == rows, table
field = service.track_service.create_field(FieldInput(name='Template software acceptance fixture Field'))
topic = service.track_service.create_topic(TrackFirstTopicInput(field_id=field['field_id'], name='Template software fixture'))
track = service.track_service.create_track(TrackFirstTrackInput(field_id=field['field_id'], primary_topic_id=topic['topic_id'], title='Template software acceptance fixture Track', research_type='conceptual_framework'))
workspace = service.create_manuscript(track['track_id'], 'Template native acceptance — software fixture')
manuscript_id = workspace['manuscript']['manuscript_id']
fixture_path = root / 'template-software-fixture-v1.db'
semantics = []
for i, (section, intent) in enumerate([('Structure Alpha', 'Research_Context'), ('Structure Alpha', 'Boundary_Condition'), ('Structure Beta', 'UNKNOWN')], 1):
    semantics.append({'seq_idx': i, 'page_idx': 1, 'section': section,
                      'raw_text': f'SOFTWARE_SOURCE_{i}_NEVER_AUTHOR_TEXT. This is synthetic template test data.',
                      'layer1': {'atomic_sentences': [], 'triplets': []},
                      'layer2': {'discourse_relation': 'Context', 'software_only': True},
                      'layer3': {'rationale': 'Rationale is not an Intent label', 'intent': intent},
                      'layer4': 'Software_Test'})
with sqlite3.connect(fixture_path) as conn:
    conn.execute('CREATE TABLE paper(id INTEGER PRIMARY KEY,title TEXT,year TEXT,authors TEXT,file TEXT,DOI TEXT,ext TEXT,Pp_txt_dict TEXT,Pp_abstract TEXT,Pp_minced_semantics TEXT)')
    conn.execute('INSERT INTO paper VALUES(1,?,?,?,?,?,?,?,?,?)', ('Software-only template source', '2026', '["Software Fixture"]', None, None, None, None, 'Synthetic data, not a scholarly abstract.', json.dumps(semantics)))
build = service.track_service.create_fieldkg_build(FieldKGBuildInput(field_id=field['field_id']))
service.track_service.import_paperpool(build['build_id'], str(fixture_path), [])
with transaction(service.db_path) as conn:
    source = dict(conn.execute('SELECT ps.*,pv.paper_id FROM paper_skeletons ps JOIN paper_versions pv USING(paper_version_id) JOIN fieldkg_build_papers bp USING(paper_version_id) WHERE bp.build_id=?', (build['build_id'],)).fetchone())
evidence = service.track_service.add_evidence(TrackFirstEvidenceInput(track_id=track['track_id'], paper_id=source['paper_id'], statement='Software fixture citation; not scholarly evidence', excerpt='Synthetic software source', location='fixture page 1', confidence=0.8, relation='SUPPORTS', extractor_model='TEST_FIXTURE', prompt_version='TEST_FIXTURE'))
document = deepcopy(workspace['document'])
paragraph = document['sections'][0]['paragraphs'][0]
paragraph['purpose'] = 'Original author purpose'
paragraph['paradigm'] = 'Original custom organization'
paragraph['intents'][0].update(label='Author intent', thoughts=[{'id': new_id('thought'), 'text': 'AUTHOR software thought Ω retains its exact wording and selected citation.', 'citation_mode': 'SELECTED', 'citations': [{'evidence_id': evidence['evidence_id'], 'selected': True}]}])
paragraph['formulas'] = [{'id': new_id('formula'), 'latex': 'x=1', 'caption': 'Original author formula'}]
asset = service.store_asset(manuscript_id, 'software-table.csv', 'text/csv', b'x,y\n1,2\n')
paragraph['asset_ids'] = [asset['asset_id']]
second = deepcopy(paragraph)
second['id'] = new_id('paragraph'); second['intents'][0]['id'] = new_id('intent')
second['intents'][0]['thoughts'][0]['id'] = new_id('thought')
second['intents'][0]['thoughts'][0]['text'] = 'AUTHOR second software thought stays separate.'
second['formulas'][0]['id'] = new_id('formula')
document['sections'][0]['paragraphs'].append(second)
group_id = new_id('paragraph_group')
document['sections'][0].update(paragraph_groups=[{'id': group_id, 'label': 'Original author group', 'paragraph_ids': [paragraph['id'], second['id']]}], block_order=[group_id])
service.save_document(manuscript_id, base_revision=0, operation_id='template-native-fixture-initial', document=document)
preview = service.preview_template(manuscript_id, source['skeleton_id'])
with transaction(service.db_path) as conn:
    tables = {row[0]: [dict(item) for item in conn.execute(f'SELECT * FROM "{row[0]}" ORDER BY rowid')]
              for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
    for table, rows in before['tables'].items():
        assert tables[table][:len(rows)] == rows, table
    assert not conn.execute('SELECT 1 FROM studio_jobs WHERE manuscript_id=?', (manuscript_id,)).fetchone()
receipt = {**info, 'owned_processes': {'studio': 82248, 'frontend': 75360}, 'studio_listener_pid': 83352,
           'source_import_root': str(repo.parent/'RSTV4/src'), 'live_owner': owner,
           'native_manuscript_id': manuscript_id, 'template_skeleton_id': source['skeleton_id'],
           'fixture_science_approval': False, 'preview': preview, 'initial_document': document,
           'before_native_tables': tables}
with (repo / '.tmp/scholar-template-native-fixture-v1.json').open('x', encoding='utf-8') as handle:
    json.dump(receipt, handle, indent=2, ensure_ascii=False)
service._executor.shutdown(wait=True)
print(json.dumps({'manuscript_id': manuscript_id, 'template_skeleton_id': source['skeleton_id'], 'sections': len(preview['sections']), 'units': len(semantics), 'old_rows_unchanged': True, 'science_approval': False}))
