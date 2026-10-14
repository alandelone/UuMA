"""Explicit software gateways for BOTH native services; no remote-model fallback."""
from pathlib import Path
import json,sys
from types import SimpleNamespace
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo.parent/'RSTV4/src'))
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from rstv4.studio_api import create_app
fixture=json.loads((repo/'.tmp/scholar-citation-source-native-v1.json').read_text(encoding='utf-8'))
app=create_app(fixture['root'])
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:3008'],allow_methods=['*'],allow_headers=['*'])
def software_gateway(task,payload):
 contract={'actual_model':'TEST_FIXTURE_G01_NATIVE','task':task,'fixture':True}
 if task=='writing_chat':
  references=[r for r in payload['retrieved_evidence'] if r.get('reference_snapshot_source')=='generation_input' and (r.get('source_context') or {}).get('available') is True]
  assert len(references)==2 and payload['generated_version']
  return {'answer':f"Software discussion keeps the original generated v{payload['generated_version']['version']} paragraph and its exact original quote; no author edit is applied.",'evidence_ids':[r['evidence_id'] for r in references],'_contract':contract}
 assert task=='paragraph_realization'
 evidence=payload['selected_evidence'];thoughts=[t for i in payload['intents'] for t in i['thoughts']]
 assert len(evidence)==2 and thoughts
 if any('Beta software original paragraph' in t['text'] for t in thoughts):
  paragraph=f"Beta software paragraph cites original page 1 [@{evidence[0]['evidence_id']}] and additional source [@{evidence[1]['evidence_id']}]."
 else:
  paragraph=f"First source [@{evidence[1]['evidence_id']}]. Next [@{evidence[0]['evidence_id']}]. Repeat [@{evidence[1]['evidence_id']}]."
 return {'paragraph':paragraph,'sentence_mappings':[{'sentence':0,'thought_ids':[t['id'] for t in thoughts]}],'_contract':contract}
app.state.studio.gateway=SimpleNamespace(analyze=software_gateway)
app.state.discussions.gateway=SimpleNamespace(analyze=software_gateway)
uvicorn.run(app,host='127.0.0.1',port=8881,log_level='warning')
