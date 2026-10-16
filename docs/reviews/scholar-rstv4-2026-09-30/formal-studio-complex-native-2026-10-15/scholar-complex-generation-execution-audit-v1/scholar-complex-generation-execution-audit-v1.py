from pathlib import Path
from collections import Counter
import hashlib,json,re,shutil,sys,xml.etree.ElementTree as ET

repo=Path(__file__).resolve().parents[1];here=repo/'.tmp/scholar-complex-generation-execution-audit-v1';runtime=repo/'.tmp/scholar-complex-native-runtime-v1';proposal=repo/'.tmp/scholar-complex-generation-proposal-v3'
read=lambda p:json.loads(p.read_text(encoding='utf-8'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();enc=lambda x:json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'));digest=lambda x:hashlib.sha256(enc(x).encode()).hexdigest()
sys.path[:0]=[str(repo.parent/'RSTV4/src'),str(repo/'.tmp/scholar-g11-parallel-v1')]
from runtime_copy_and_serve import snapshot
from rstv4.studio_realization import validate as validate_realization
from rstv4.studio_sources import validate_references
from rstv4.studio_structure import argument_context
def rows(s,n):t=s['tables'][n];return [dict(zip(t['columns'],r)) for r in t['rows']]
def snap(p):s=snapshot(p);s['schema']=[list(r) for r in s['schema']];return s
def put(n,v):
 with (here/n).open('x',encoding='utf-8') as stream:json.dump(v,stream,ensure_ascii=False,indent=2)
def filemap(root):return {p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file() and not p.name.endswith(('-wal','-shm'))}
receipt=read(runtime/'receipt.json');root=Path(receipt['root']);ms='manuscript_56652adf9d054cb6ab3819efacf3475c';jid='studio_job_e1b44f87565846198e4166948b2b480d';vid='manuscript_version_e1c764ab2d5a4e97898eda9f5d815d01';a212='comment_f39d35831bd0472bb9282ab116e90611'
base=read(proposal/'all110-before.json');captured=read(here/'captured-all110.json');live=snap(root/'data/catalog.db')
contract=read(proposal/'proposed-generation-contracts.json');assert sha(runtime/'generation-contracts.json')==sha(proposal/'proposed-generation-contracts.json')=='7c3e70d1eb7becb142b398eca9c577a71480ee4dad67e0ccd2054e2b6fee2305'
assert read(proposal/'explicit-arm-receipt.json')['db110_and_all_root_files_unchanged']
assert read(runtime/'generation-post-once.json')=={'kind':'GENERATE','input_revision':79,'request':{}}
assert read(runtime/'action-087-response.json')['status_code']==202
assert read(runtime/'action-087-response.json')['body']['job_id']==jid
for s in [base,captured,live]:assert len(s['tables'])==110 and s['schema']==base['schema']
generation_tables={'manuscript_versions','manuscripts','studio_artifacts','studio_documents','studio_jobs','studio_model_calls'}
concurrent_tables={'review_comments','studio_comment_response_state','studio_response_checks'}
audit_diffs={}
for label,state in [('capture',captured),('after_read',live)]:
 changed=[n for n in base['tables'] if base['tables'][n]!=state['tables'][n]]
 assert generation_tables<=set(changed) and set(changed)<=generation_tables|concurrent_tables
 table_diffs={}
 for n in changed:
  old=Counter(map(enc,base['tables'][n]['rows']));new=Counter(map(enc,state['tables'][n]['rows']))
  table_diffs[n]={'before_rows':sum(old.values()),'after_rows':sum(new.values()),'removed':[json.loads(x) for x in (old-new).elements()],'added':[json.loads(x) for x in (new-old).elements()]}
 for name,count in {'manuscript_versions':1,'studio_artifacts':5,'studio_jobs':1,'studio_model_calls':10}.items():
  assert not table_diffs[name]['removed'] and len(table_diffs[name]['added'])==count
 for n,key in [('manuscripts','manuscript_id'),('studio_documents','manuscript_id')]:
  old={r[key]:r for r in rows(base,n)};new={r[key]:r for r in rows(state,n)};assert old.keys()==new.keys()
  assert all(r==new[k] for k,r in old.items() if k!=ms)
  changed_fields={k for k in old[ms] if old[ms][k]!=new[ms][k]}
  if n=='manuscripts':assert changed_fields=={'revision','updated_at'} and old[ms]['revision']==6 and new[ms]['revision']==7
  else:
   assert changed_fields=={'active_generated_version_id','last_generated_revision','updated_at'}
   assert old[ms]['revision']==new[ms]['revision']==79 and old[ms]['document_json']==new[ms]['document_json']==contract['author_document_json']
   assert new[ms]['active_generated_version_id']==vid and new[ms]['last_generated_revision']==79
 for n in concurrent_tables & set(changed):
  if n=='review_comments':
   old={r['comment_id']:r for r in rows(base,n)};new={r['comment_id']:r for r in rows(state,n)};assert old.keys()==new.keys()
   assert all(r==new[k] for k,r in old.items() if k!=a212)
   assert {k for k in old[a212] if old[a212][k]!=new[a212][k]}<={'author_decision','response_text','status','updated_at'}
  elif n=='studio_comment_response_state':
   old={r['comment_id']:r for r in rows(base,n)};new={r['comment_id']:r for r in rows(state,n)}
   assert set(new)-set(old)<={a212} and all(r==new[k] for k,r in old.items() if k!=a212)
  else:
   assert not table_diffs[n]['removed']
   for added in table_diffs[n]['added']:assert dict(zip(state['tables'][n]['columns'],added))['comment_id']==a212
 audit_diffs[label]={'changed_tables':changed,'table_diffs':table_diffs}
assert all(captured['tables'][n]==live['tables'][n] for n in generation_tables)
job=next(r for r in rows(live,'studio_jobs') if r['job_id']==jid);assert job['status']=='SUCCEEDED' and job['input_revision']==79 and job['error_json'] is None
assert job['job_kind']=='GENERATE' and json.loads(job['result_json'])['generated_version_id']==vid
version=next(r for r in rows(live,'manuscript_versions') if r['manuscript_version_id']==vid);assert version['version']==6
generated=read(here/'exact-artifacts/generated.json');inputs=json.loads(version['inputs_json'])
assert inputs['generated']==generated and inputs['studio_revision']==79 and inputs['job_id']==jid
assert version['content']==(here/'exact-artifacts/manuscript.md').read_text(encoding='utf-8')
expected={item['input_sha256']:item for item in contract['paragraph_contracts']};assert len(expected)==10
calls=[r for r in rows(live,'studio_model_calls') if r['job_id']==jid];assert len(calls)==10
assert {r['input_sha256'] for r in calls}==set(expected)
for call in calls:
 item=expected[call['input_sha256']];assert digest(json.loads(call['input_json']))==call['input_sha256']
 assert json.loads(call['input_json'])==item['payload'] and json.loads(call['output_json'])==item['response']
 assert json.loads(call['contract_json'])==item['response']['_contract']
 assert call['status']=='SUCCEEDED' and call['task']=='paragraph_realization' and call['input_revision']==79 and call['error_json'] is None
 assert call['started_at']>=job['started_at'] and call['completed_at']<=job['completed_at']
callids={r['input_sha256']:r['call_id'] for r in calls}
fixturecalls=[read(p) for p in sorted(runtime.glob('fixture-call-*.json'))];assert len(fixturecalls)==10 and {r['input_sha256'] for r in fixturecalls}==set(expected)
assert all(r['honest_software_fixture'] and r['task']=='paragraph_realization' and expected[r['input_sha256']]['paragraph_id']==r['paragraph_id'] for r in fixturecalls)
paragraphs={p['paragraph_id']:p for s in generated['sections'] for p in s['paragraphs']};assert len(paragraphs)==10
author=json.loads(contract['author_document_json']);assert generated['argument_relations']==author['argument_relations'] and len(generated['argument_relations'])==3
for item in expected.values():
 p=paragraphs[item['paragraph_id']];payload=item['payload'];tids={t['id'] for i in payload['intents'] for t in i['thoughts']};eids={e['evidence_id'] for e in payload['selected_evidence']}
 realized=validate_realization(item['response'],tids,eids)
 assert p['text']==realized['text'] and p['sentence_mappings']==realized['sentence_mappings'] and p['sentences']==realized['sentences'] and p['sentence_positions_verified']
 assert set(p['thought_ids'])==tids and set(p['evidence_ids'])==eids and p['model_call_id']==callids[item['input_sha256']]
 assert p['model_contract']==item['response']['_contract']
 for i in payload['intents']:
  for t in i['thoughts']:assert t['text'] in p['text']
alpha=paragraphs['paragraph_e197b886c810436a823c7171839afac2'];assert len(alpha['sentences'])==5
alphaids=['thought_author_1','thought_5f3edebed89d482cb0b2d9d42c4930d8']
assert [m['thought_ids'] for m in alpha['sentence_mappings']]==[alphaids,[alphaids[0]],[alphaids[0]],[alphaids[1]],[alphaids[1]]]
for section in author['sections']:
 for p in section['paragraphs']:
  item=next(x for x in expected.values() if x['paragraph_id']==p['id'])
  assert item['payload'].get('argument_relations',[])==argument_context(author,p)
frozen=read(proposal/'frozen-evidence.json');validate_references(generated,frozen,[r['evidence_id'] for r in generated['references']]);assert len(generated['references'])==3
materials=read(proposal/'frozen-materials.json');actualmaterials={a['asset_id']:a for p in paragraphs.values() for a in p.get('assets',[])};assert actualmaterials==materials
gdir=Path(next(r for r in rows(live,'studio_artifacts') if r['job_id']==jid)['storage_path']).parent
for name,metadata in read(proposal/'material-files.json').items():assert sha(gdir/name)==metadata['sha256'] and (gdir/name).stat().st_size==metadata['bytes']
for asset in actualmaterials.values():
 original=next(r for r in rows(live,'studio_assets') if r['asset_id']==asset['asset_id'])
 assert sha(Path(original['storage_path']))==asset['sha256'] and Path(original['storage_path']).read_bytes()==(gdir/asset['source_file']).read_bytes()
for evidence in frozen.values():
 ctx=evidence['source_context'];assert ctx['available'] and ctx['full_text_available']
 assert digest({k:v for k,v in ctx.items() if k!='context_sha256'})==ctx['context_sha256']
 sf=next(r for r in rows(live,'source_file_versions') if r['file_version_id']==ctx['file_version_id'])
 assert sha(Path(sf['storage_path']))==ctx['file_version']['sha256'] and Path(sf['storage_path']).stat().st_size==ctx['file_version']['size_bytes']
artifacts=[r for r in rows(live,'studio_artifacts') if r['job_id']==jid];assert {r['artifact_kind'] for r in artifacts}=={'MARKDOWN','GENERATED_JSON','TEX','BIB','PDF'}
for artifact in artifacts:
 p=Path(artifact['storage_path']);assert sha(p)==artifact['sha256'] and p.stat().st_size==artifact['size_bytes'] and p.read_bytes()==(here/'exact-artifacts'/p.name).read_bytes()
beforefiles=read(proposal/'all-files-before.json');currentfiles=filemap(root)
assert all(currentfiles[p]==v for p,v in beforefiles.items() if p!='data/catalog.db')
newfiles=set(currentfiles)-set(beforefiles);assert newfiles=={p.relative_to(root).as_posix() for p in gdir.iterdir() if p.is_file()} and len(newfiles)==13
vectors=read(proposal/'source-vectors.json');build=Path(receipt['frontend_root'])
assert all(sha(repo.parent/'RSTV4'/p)==v for p,v in vectors['backend311'].items())
assert all(sha(repo.parent/'writing-studio'/p)==v and sha(build/p)==v for p,v in vectors['frontend91'].items())
assert all(sha(build/p)==v for p,v in vectors['dist76'].items())
log=(gdir/'manuscript.log').read_text(encoding='utf-8',errors='replace');assert 'Output written on manuscript.pdf' in log
assert 'Overfull' not in log and 'Undefined control sequence' not in log and 'Emergency stop' not in log
compile_diagnostics={'pdf_info':(here/'pdfinfo-stdout.txt').read_text(encoding='utf-8'),'overfull_box_messages':re.findall(r'.*Overfull.*',log),'warning_lines':[line for line in log.splitlines() if 'Warning' in line or 'warning' in line],'compiler':'XeTeX/xdvipdfmx from actual preserved log and PDF metadata','tex_product_uses_no_shell_escape_and_restrictive_openin_openout':True,'full_compile_subprocess_args_not_separately_traced':True}
xhtml=ET.parse(here/'pdf-bbox.xhtml');ns={'h':'http://www.w3.org/1999/xhtml'};geometry=[]
for page in xhtml.findall('.//h:page',ns):
 width=float(page.attrib['width']);height=float(page.attrib['height']);words=page.findall('.//h:word',ns)
 outside=[{'text':w.text,'bbox':w.attrib} for w in words if float(w.attrib['xMin'])<0 or float(w.attrib['yMin'])<0 or float(w.attrib['xMax'])>width+.01 or float(w.attrib['yMax'])>height+.01]
 assert not outside
 geometry.append({'width':width,'height':height,'word_count':len(words),'outside_page':outside,'bounds':[min(float(w.attrib['xMin']) for w in words),min(float(w.attrib['yMin']) for w in words),max(float(w.attrib['xMax']) for w in words),max(float(w.attrib['yMax']) for w in words)]})
assert len(geometry)==2
layout=(here/'pdf-layout.txt').read_text(encoding='utf-8');normalized=re.sub(r'\s+',' ',re.sub(r'-\s*\n\s*','',layout))
assert all(text in normalized for text in ['SOFTWARE_FIXTURE','fictional_value','qualification','alpha_demo','beta_demo','Software rendering test only; no scientific measurement','No scientific measurements or findings','References'])
assert len(list((here/'render').glob('*.png')))==2
put('all110-after-read.json',live);put('all-files-after-read.json',currentfiles);put('full110-declared-diffs.json',audit_diffs);put('compile-and-pdf-geometry.json',{'compile':compile_diagnostics,'geometry':geometry,'visual_review':'Both rendered pages inspected: complete table qualification wraps, intact SVG, Alpha prose and 3 source references; no clipping or overflow observed.'})
for name in ['manuscript.log','manuscript.aux','manuscript.bbl','manuscript.blg',*read(proposal/'material-files.json')]:shutil.copyfile(gdir/name,here/'exact-artifacts'/name)
result={'status':'PASS_SCOPED_NATIVE_GENERATION_EXECUTION_AND_RENDER_AUDIT_NOT_FINAL_FORMAL_SEAL','job_id':jid,'generated_version_id':vid,'version':6,'author_revision':79,'one_actual_native_generate_post':True,'actual_compile_completed':True,'actual_paragraph_fixture_calls':10,'remote_model_calls':0,'all10_input_output_contracts_exact':True,'alpha_actual_sentences':5,'shared_and_separate_mapping_exact':True,'all11_complete_author_thought_texts_preserved':True,'three_argument_relation_conditions_and_endpoint_author_texts_frozen':True,'three_selected_evidence_source_snapshots_exact':True,'two_original_material_sources_and_render_exact':True,'five_main_artifacts_exact':True,'old_generation_rows_and_other_manuscripts_exact':True,'old_durable_checks_links_sources_exact':True,'concurrent_parent_a212_reply_check_changes_declared_separately':True,'full110_captured_before_and_after_reads_retained':True,'all_other_tables_exact':True,'all_old_owned_non_database_files_exact':True,'new_generated_files':13,'current311_91_76_exact':True,'pdf_pages':2,'pdf_bytes':50360,'pdf_sha256':'ec3988b80410560cd1b40d9bd15615718b2c9ab144147a2d028af461d497c0a1','pdf_visual_no_clipping_observed':True,'scientific_approval':False,'formal_report_sealed':False,'all11_complete':False}
put('audit-receipt.json',result);print(json.dumps(result,ensure_ascii=False))
