"""Serve-only explicit G02 software discussion fixture; never seeds or uses a remote fallback."""
from pathlib import Path
from types import SimpleNamespace
import json,sys
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo.parent/'RSTV4/src'))
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from rstv4.studio_api import create_app
fixture=json.loads((repo/'.tmp/scholar-citation-source-native-v1.json').read_text(encoding='utf-8'))
app=create_app(fixture['root'])
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:3008'],allow_methods=['*'],allow_headers=['*'])
def software_gateway(task,payload):
    assert task=='writing_chat', 'G02 native fixture permits only the requested discussion'
    assert payload['author_question'].startswith('G02 SOFTWARE PARTIAL:'), 'Unexpected discussion request'
    version=payload['generated_version'];assert version and version['version']==3 and version['input_revision']==10
    references=[r for r in payload['retrieved_evidence'] if r.get('reference_snapshot_source')=='generation_input' and (r.get('source_context') or {}).get('available') is True]
    assert len(references)==2
    doc=payload['document'];paragraph=doc['sections'][0]['paragraphs'][0]
    assert paragraph['id']=='paragraph_e197b886c810436a823c7171839afac2' and paragraph['purpose']==''
    assert paragraph['intents'][0]['thoughts'][0]['text']=='Check original sources only; no scientific claim is asserted.'
    return {'answer':'Software fixture proposes two structure changes for author comparison. No author change is applied by this reply. The original v3 paragraph, quote and sources stay fixed.',
            'evidence_ids':[r['evidence_id'] for r in references],
            'suggestions':[{'kind':'STRUCTURE','title':'G02 software partial adoption','rationale':'Select only the paragraph purpose. Keep the proposed extra Intent unadopted, and retain the original author thought and sources.',
                            'changes':[{'action':'SET_FIELD','target_type':'paragraph','target_id':paragraph['id'],'field':'purpose','value':'G02 adopted software boundary: preserve the original thought and sources.'},
                                       {'action':'INSERT_INTENT','target_type':'paragraph','target_id':paragraph['id'],'label':'G02 omitted software Intent'}]}],
            '_contract':{'actual_model':'TEST_FIXTURE_G02_NATIVE','task':task,'fixture':True}}
app.state.studio.gateway=SimpleNamespace(analyze=software_gateway)
app.state.discussions.gateway=SimpleNamespace(analyze=software_gateway)
uvicorn.run(app,host='127.0.0.1',port=8881,log_level='warning')
