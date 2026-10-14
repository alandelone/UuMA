"""Serve-only explicit Stage 3 software-review fixture; no seeding or remote fallback."""
from pathlib import Path
from types import SimpleNamespace
import json,sys
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo.parent/'RSTV4/src'))
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from rstv4.studio_api import create_app
fixture=json.loads((repo/'.tmp/scholar-citation-source-native-v1.json').read_text(encoding='utf-8'))
app=create_app(fixture['root']);app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:3008'],allow_methods=['*'],allow_headers=['*'])
review_calls=0
def software_review(task,payload):
    global review_calls
    assert task=='writing_review', 'G04 fixture permits only its explicit whole-paper review.'
    assert review_calls==0, 'G04 fixture permits one explicit review; no repeat or remote fallback.'
    assert payload['generated_version_id']=='manuscript_version_2feb293fad7e4e6591d4217cd322d9d9'
    assert payload['author_input_revision']==11
    doc=payload['author_structure'];assert doc['manuscript_id']==fixture['manuscript_id']
    assert [p['id'] for p in doc['sections'][0]['paragraphs']]==['paragraph_895901de3a694d6f9a4b996e5459feeb','paragraph_e197b886c810436a823c7171839afac2']
    assert 'Beta software paragraph cites original page 1 [1] and additional source [2].' in payload['generated_manuscript']
    assert len(payload['fixed_references'])==2
    review_calls+=1
    return {'findings':[{'kind':'SEMANTIC_CHECK','severity':'WARNING','anchor':{'paragraph_id':'paragraph_895901de3a694d6f9a4b996e5459feeb'},'detail':'G04 software review marker: keep this unresolved finding while returning from Stage 3 structure editing. No scientific judgment is asserted.'}],
            '_contract':{'actual_model':'TEST_FIXTURE_G04_STAGE3_DONE_NATIVE','task':task,'fixture':True}}
app.state.studio.gateway=SimpleNamespace(analyze=software_review);app.state.discussions.gateway=SimpleNamespace(analyze=software_review)
uvicorn.run(app,host='127.0.0.1',port=8881,log_level='warning')
