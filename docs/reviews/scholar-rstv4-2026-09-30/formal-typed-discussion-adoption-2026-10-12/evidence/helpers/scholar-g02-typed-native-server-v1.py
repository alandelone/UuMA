"""Serve-only explicit SOURCE/WORDING software fixtures, no model fallback or database seeding."""
from pathlib import Path
from types import SimpleNamespace
import json,sys
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo.parent/'RSTV4/src'))
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from rstv4.studio_api import create_app
fixture=json.loads((repo/'.tmp/scholar-citation-source-native-v1.json').read_text(encoding='utf-8'))
app=create_app(fixture['root']);app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:3008'],allow_methods=['*'],allow_headers=['*'])
def software_gateway(task,payload):
    assert task=='writing_chat'
    question=payload['author_question'];version=payload['generated_version'];assert version and version['version']==3 and version['input_revision']==10
    assert question.startswith(('G02 SOFTWARE SOURCE:','G02 SOFTWARE WORDING:'))
    doc=payload['document'];alpha,beta=doc['sections'][0]['paragraphs']
    assert alpha['id']=='paragraph_e197b886c810436a823c7171839afac2' and beta['id']=='paragraph_895901de3a694d6f9a4b996e5459feeb'
    if question.startswith('G02 SOFTWARE SOURCE:'):
        evidence=[r for r in payload['retrieved_evidence'] if r['evidence_id']=='evidence_3a2639ee8b5e432aafd7e3743c825f33'];assert len(evidence)==1 and evidence[0]['statement']=='Original software source body 2.'
        thought=beta['intents'][0]['thoughts'][0];assert all(c['evidence_id']!=evidence[0]['evidence_id'] for c in thought['citations'])
        proposal={'kind':'SOURCE','title':'G02 software source candidate','rationale':'Add this existing owned page 2 source as an unselected candidate. Keep both original selected sources and the original author text.',
                  'changes':[{'action':'ADD_SOURCE','target_type':'thought','target_id':thought['id'],'evidence_id':evidence[0]['evidence_id']}]}
        ids=[evidence[0]['evidence_id']]
    else:
        thought=alpha['intents'][0]['thoughts'][0];assert thought['id']=='thought_author_1' and thought['text'].startswith('Check original sources only;')
        proposal={'kind':'WORDING','title':'G02 software wording rejection','rationale':'Offer a five-character wording edit for explicit rejection. Preserve the original author thought when rejected.',
                  'changes':[{'action':'REPLACE_TEXT','target_type':'thought','target_id':thought['id'],'field':'text','value':'Review','quote':{'text':'Check','start':0,'end':5,'offset_unit':'utf16'}}]}
        ids=[]
    return {'answer':'Software-only typed suggestion for author review. The reply does not change the manuscript or approve scientific evidence.','suggestions':[proposal],'evidence_ids':ids,
            '_contract':{'actual_model':'TEST_FIXTURE_G02_TYPED_NATIVE','task':task,'fixture':True}}
app.state.studio.gateway=SimpleNamespace(analyze=software_gateway);app.state.discussions.gateway=SimpleNamespace(analyze=software_gateway)
uvicorn.run(app,host='127.0.0.1',port=8881,log_level='warning')
