"""Read-only audit of the owned native citation fixture and actual browser downloads."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,sqlite3,shutil,subprocess,sys
repo=Path.cwd();sys.path.insert(0,str(repo.parent/'RSTV4/src'))
from rstv4.studio_read_views import generated_version
from rstv4.studio_sources import original_pdf
from pypdf import PdfReader
fixture=json.loads((repo/'.tmp/scholar-citation-source-native-v1.json').read_text(encoding='utf-8'))
root=Path(fixture['root']);db=root/'data/catalog.db';before=hashlib.sha256(db.read_bytes()).hexdigest()
out=repo/'.tmp/scholar-citation-source-native-audit-v1';out.mkdir();ms=fixture['manuscript_id']
def sha(raw):return hashlib.sha256(raw).hexdigest()
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as conn:
 conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON')
 tables={r[0]:[dict(row) for row in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
 failed=json.loads((repo/'.tmp/scholar-citation-source-failed-discussion-v1/original-records.json').read_text(encoding='utf-8'))
 for table,rows in failed.items():
  key={'research_discussion_jobs':'request_id','research_discussion_messages':'message_id','studio_model_calls':'call_id','studio_chat_messages':'message_id'}[table]
  current={row[key]:row for row in tables[table]}
  assert all(current[row[key]]==row for row in rows),(table,'original failed/source rows changed')
 jobs=[r for r in tables['studio_jobs'] if r['manuscript_id']==ms]
 assert len(jobs)==2 and all(r['job_kind']=='GENERATE' and r['status']=='SUCCEEDED' for r in jobs)
 assert sorted(r['input_revision'] for r in jobs)==[1,4]
 versions=[generated_version(conn,root/'data/writing-studio',ms,json.loads(job['result_json'])['generated_version_id']) for job in sorted(jobs,key=lambda r:r['created_at'])]
 first,second=versions
 assert [r['paper_id'] for r in first['references']]==['existing','existing']
 assert all(r['title']=='Catalog selected source' for r in first['references'])
 assert [r['paper_id'] for r in second['references']]==['other','existing']
 assert [r['title'] for r in second['references']]==['Other selected source','Refreshed live catalog title - software']
 assert first['references'][0]['source_context']['unit']['page_idx']==2
 assert second['references'][0]['source_context']['unit']['page_idx']==1
 assert first['references'][0]['evidence_id'] not in {r['evidence_id'] for r in second['references']}
 assert first['blocks'][-1]['display_text']==second['blocks'][-1]['display_text']=='First source [1]. Next [2]. Repeat [1].'
 original=original_pdf(conn,first['references'][0]);assert sha(original)==fixture['original_pdf_sha256']
 doc=next(r for r in tables['studio_documents'] if r['manuscript_id']==ms)
 assert doc['revision']==doc['last_generated_revision']==4
 assert doc['active_generated_version_id']==second['generated_version_id']
 current=json.loads(doc['document_json']);initial=deepcopy(fixture['initial_document'])
 thought=current['sections'][0]['paragraphs'][0]['intents'][0]['thoughts'][0]
 original_thought=initial['sections'][0]['paragraphs'][0]['intents'][0]['thoughts'][0]
 assert len(thought['citations'])==3 and thought['citation_mode']=='SELECTED'
 assert thought['citations'][0]==original_thought['citations'][0]
 assert {**thought['citations'][1],'selected':True}==original_thought['citations'][1]
 assert thought['citations'][1]['selected'] is False and thought['citations'][2]['selected'] is True
 assert thought['citations'][2]['evidence_id']==second['references'][0]['evidence_id']
 original_thought['citations']=thought['citations'];assert current==initial
 calls=[r for r in tables['studio_model_calls'] if r['manuscript_id']==ms]
 assert len(calls)==5 and sorted(r['status'] for r in calls)==['REJECTED','RETURNED','RETURNED','VALIDATED','VALIDATED']
 assert sum(json.loads(r['contract_json'] or '{}').get('actual_model')=='gemini-3.8-flash' for r in calls)==1
 passed=[r for r in calls if r['status']=='RETURNED']
 frozen_ids=[r['evidence_id'] for r in first['references']]
 for call in passed:
  payload=json.loads(call['input_json']);response=json.loads(call['output_json'])
  assert sha(call['input_json'].encode())==call['input_sha256']
  assert json.loads(call['contract_json'])['actual_model']=='TEST_FIXTURE_SOURCE_NATIVE'
  assert response['evidence_ids']==frozen_ids
  assert payload['generated_version']['generated_version_id']==first['generated_version_id']
  supplied={r['evidence_id']:r for r in payload['retrieved_evidence']}
  assert all(supplied[r['evidence_id']]['title']==r['title'] and supplied[r['evidence_id']]['source_context']['context_sha256']==r['source_context']['context_sha256'] for r in first['references'])
  assert 'Original software source body 3.' not in call['input_json']
 shared=tables['research_discussion_jobs'];assert len(shared)==3
 assert sorted(r['status'] for r in shared)==['COMPLETE','COMPLETE','FAILED']
 assert len(tables['studio_chat_messages'])==5
 artefacts=tables['studio_artifacts'];assert len(artefacts)==10
 for row in artefacts:
  raw=Path(row['storage_path']).read_bytes();assert len(raw)==row['size_bytes'] and sha(raw)==row['sha256']
(out/'all-tables.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'fixed-generated-versions.json').write_text(json.dumps(versions,ensure_ascii=False,indent=2),encoding='utf-8')
downloads=Path.home()/'Downloads';proofs=[]
for number,name in [(1,'manuscript (3).pdf'),(2,'manuscript (4).pdf')]:
 version=versions[number-1];job=next(r for r in jobs if json.loads(r['result_json'])['generated_version_id']==version['generated_version_id'])
 artifact=next(r for r in artefacts if r['job_id']==job['job_id'] and r['artifact_kind']=='PDF')
 raw=(downloads/name).read_bytes();assert sha(raw)==artifact['sha256'] and len(raw)==artifact['size_bytes']
 target=out/f'downloaded-manuscript-v{number}.pdf';target.write_bytes(raw);proofs.append({'file':str(target),'browser_download':str(downloads/name),'sha256':sha(raw),'generated_version_id':version['generated_version_id']})
raw=(downloads/'original-source (1).pdf').read_bytes();assert raw==original
target=out/'downloaded-original-v1.pdf';target.write_bytes(raw);proofs.append({'file':str(target),'browser_download':str(downloads/'original-source (1).pdf'),'sha256':sha(raw)})
render=out/'render';render.mkdir();pages=[];poppler=shutil.which('pdftoppm');assert poppler
for item in proofs:
 path=Path(item['file']);reader=PdfReader(path);expected=3 if 'original' in path.name else 1
 assert len(reader.pages)==expected
 text='\n'.join(page.extract_text() or '' for page in reader.pages)
 if 'original' in path.name:
  assert all(f'Original software source body {i}.' in (reader.pages[i-1].extract_text() or '') for i in range(1,4))
 elif 'v1' in path.name:
  assert 'Catalog selected source' in text and 'Other selected source' not in text
 else:
  assert 'Other selected source' in text and 'Refreshed live catalog title' in text
 result=subprocess.run([poppler,'-r','110','-png',str(path),str(render/path.stem)],capture_output=True,text=True);assert result.returncode==0,result.stderr
 item['pages']=expected;item['text_sha256']=sha(text.encode());pages.extend(str(p) for p in sorted(render.glob(path.stem+'-*.png')))
assert len(pages)==5 and hashlib.sha256(db.read_bytes()).hexdigest()==before
receipt={'status':'PASS_READ_ONLY_RECORD_AND_DOWNLOAD_AUDIT','database_bytes_preserved':True,'tables':len(tables),'author_revision':4,'generated_versions':[r['generated_version_id'] for r in versions],'all_original_failed_rows_preserved':True,'recorded_real_model_replies':1,'real_http_attempt_count_unknown':True,'software_generation_calls':2,'software_discussion_replies':2,'sources_remain_candidates_not_scientific_approval':True,'downloads':proofs,'rendered_pages':pages,'all_pages_visual_review_required':True,'full_11_groups_complete':False}
(out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(receipt),flush=True)
