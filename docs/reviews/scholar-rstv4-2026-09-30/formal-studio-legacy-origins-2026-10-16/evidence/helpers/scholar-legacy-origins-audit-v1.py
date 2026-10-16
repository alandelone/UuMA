from pathlib import Path
from contextlib import closing
import hashlib,json,sqlite3

repo=Path(__file__).resolve().parents[1];here=repo/'.tmp/scholar-legacy-origins-native-v1'
read=lambda p:json.loads(p.read_text(encoding='utf8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
digest=lambda v:hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf8')).hexdigest()
r=read(here/'receipt.json');term=read(here/'backend-terminal.json');before=read(here/'before110-all-tables.json')
assert term['all110_exact'] and term['all_non_sidecar_bytes_exact'] and term['models_jobs_checks_started']==0
assert term['copy_final_all_tables']==before and len(before['tables'])==110
stop=read(here/'owned-stop-terminal.json');assert stop['no_other_processes_stopped']
ms='manuscript_56652adf9d054cb6ab3819efacf3475c';comment='comment_f39d35831bd0472bb9282ab116e90611'
check='response_check_6cde187dab114344895de0899fc20940';version='manuscript_version_e1c764ab2d5a4e97898eda9f5d815d01'
history=read(here/'http-0020-response.json')['history'];assert len(history)==1 and history[0]['check_id']==check
h=history[0];ctx=h['context'];state=ctx['state']
assert h['context_sha256']==digest({k:v for k,v in ctx.items() if k!='context_sha256'})
selected=[i for claim in h['request']['claims'] for i in claim['evidence_ids']];assert len(selected)==len(set(selected))==5
with closing(sqlite3.connect(Path(r['root'],'data/catalog.db').resolve().as_uri()+'?mode=ro',uri=True)) as conn:
    conn.row_factory=sqlite3.Row
    raw=conn.execute('SELECT * FROM studio_response_checks WHERE check_id=?',(check,)).fetchone()
    assert json.loads(raw['context_json'])==ctx and json.loads(raw['request_json'])==h['request']
    target=dict(conn.execute('SELECT content,inputs_json FROM manuscript_versions WHERE manuscript_id=? AND manuscript_version_id=?',(ms,version)).fetchone())
    assert digest(target)==state['generated_record_sha256']
    authors=conn.execute('SELECT c.after_json FROM studio_changes c JOIN studio_operations o USING(operation_id) WHERE c.manuscript_id=? AND o.resulting_revision=?',(ms,79)).fetchall()
    assert authors and len({a['after_json'] for a in authors})==1
    original_json=authors[0]['after_json'];assert hashlib.sha256(original_json.encode('utf8')).hexdigest()==state['current_author_document_sha256']
    current=dict(conn.execute('SELECT * FROM studio_documents WHERE manuscript_id=?',(ms,)).fetchone())
    assert current['revision']==86 and current['active_generated_version_id']=='manuscript_version_8732ec9497074d82ae2b4359a7c235e5'
    author=json.loads(original_json)
    assert conn.execute("SELECT outcome FROM studio_response_checks WHERE check_id='response_check_1b9b3eaa4905448092dd2c472f7c9324'").fetchone()[0]=='PRESENTATION_MODIFIED'
http=[];origins=[]
for path in sorted(here.glob('http-*.json')):
    if '-response' in path.name:continue
    event=read(path);http.append(event)
    assert event['status']==200 and (event['method'] in {'GET','HEAD','OPTIONS'} or event['path'] in {'/api/research/discussion/history','/api/research/discussion/context'})
    if '/origins/' not in event['path']:continue
    response=path.with_name(path.stem+'-response.json');assert sha(response)==event['response_sha256']
    item=read(response);eid=event['path'].rsplit('/',1)[1]
    assert item['check_id']==check and item['evidence_id']==eid and eid in selected
    assert item['original_context_sha256']==h['context_sha256'] and item['status']=='RECONSTRUCTED_FROM_FIXED_INPUT'
    assert item['source']==dict(manuscript_id=ms,generated_version_id=version,generated_version_number=6,input_revision=79,generated_record_sha256=state['generated_record_sha256'],author_document_sha256=state['current_author_document_sha256'])
    assert len(item['origins'])==1
    origin=item['origins'][0];row=next(x for x in ctx['evidence'] if x['evidence_id']==eid)
    assert not row.get('origins') and origin['thought_id']==row['thought_id']
    assert origin['generated_version_id']==version and origin['input_revision']==79
    paragraphs=[p for s in author['sections'] for p in s['paragraphs'] if p['id']==origin['paragraph_id']]
    assert len(paragraphs)==1
    intents=[i for i in paragraphs[0]['intents'] if i['id']==origin['intent_id']];assert len(intents)==1
    intent=intents[0];assert origin['intent_label']==intent['label']
    assert origin['intent_thoughts']==[{'thought_id':t['id'],'text':t['text']} for t in intent['thoughts']]
    assert origin['thought_text']==next(t['text'] for t in intent['thoughts'] if t['id']==origin['thought_id'])
    origins.append({'evidence_id':eid,'thought_id':origin['thought_id'],'sentence_index':row['sentence_index'],'full_intent_thoughts':len(origin['intent_thoughts']),'response_sha256':sha(response)})
assert len(origins)==5 and {x['evidence_id'] for x in origins}==set(selected)
assert sorted(x['sentence_index'] for x in origins)==[0,0,1,2,4]
assert len({x['thought_id'] for x in origins if x['sentence_index']==0})==2
dom=read(here/'native-two-origins-dom.json');assert dom['viewport']=={'width':1280,'height':720}
dialog=dom['dialog'][0];assert dialog['clientWidth']==dialog['scrollWidth'] and len(dialog['origins'])==2 and all(o['open'] for o in dialog['origins'])
final=(here/'native-all-five-origins.txt').read_text(encoding='utf8')
assert final.count('从当时固定输入补查 · 成文 v6 / 原稿 r79；原核对记录与状态保持不变。')==5
assert '回查当时固定版本的原思想' not in final and '回复、版本或关联已变化 · 需要重新核对' in final
result={'status':'PASS_NATIVE_FIVE_LEGACY_ORIGINS_READONLY','check_id':check,'historical_context_sha256':h['context_sha256'],
 'historical_version':6,'historical_input_revision':79,'current_author_revision':86,'current_generated_version':7,
 'all_five_selected_evidence_read':origins,'shared_sentence_two_distinct_original_thoughts':True,'full_original_intent_and_thought_text_exact':True,
 'original_context_and_request_bytes_unchanged':True,'all110_tables_exact':True,'all_non_sidecar_bytes_exact':True,
 'A212_stale_status_preserved':True,'A215_current_check_retained':True,'all_owned_services_stopped':True,
 'native_viewport':[1280,720],'narrow_viewport_tested_this_turn':False,'horizontal_overflow':False,
 'no_business_mutation_or_model_job_generation_package_budget_replay':True,'http_observed_count':len(http),
 'initial_fetch_failed_then_comments_recovered_explicitly':True,'initial_fetch_cause_unresolved':True,
 'scientific_approval':False,'final11_complete':False}
with (here/'final-audit.json').open('x',encoding='utf8') as f:json.dump(result,f,indent=2)
print(json.dumps(result,indent=2))
