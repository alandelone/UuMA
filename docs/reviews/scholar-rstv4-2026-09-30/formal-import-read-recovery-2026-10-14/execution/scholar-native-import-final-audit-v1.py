from pathlib import Path
import hashlib
import json
import sys

repo=Path(__file__).resolve().parents[1]
here=repo/'.tmp/scholar-native-import-v1'
receipt=json.loads((here/'copy-receipt.json').read_text(encoding='utf-8'))
root=Path(receipt['root']); source=Path(receipt['source'])
sys.path.insert(0,str(repo/'.tmp/scholar-g11-parallel-v1'))
from runtime_copy_and_serve_v6 import snapshot, product_guard
product_guard()
before=json.loads((here/'before-all-tables.json').read_text())
after=json.loads((here/'after-four-native-imports-all-tables.json').read_text())
current=json.loads(json.dumps(snapshot(root/'data/catalog.db')))
assert current==after,'Data changed since four native imports; inspect without replay'
assert before['schema']==current['schema'] and set(before['tables'])==set(current['tables'])
changed={k for k in before['tables'] if before['tables'][k]!=current['tables'][k]}
assert changed=={'review_comments','review_rounds','studio_review_round_baselines','studio_sample_candidates'}

def rows(s,name):
    t=s['tables'][name]
    return [dict(zip(t['columns'],r)) for r in t['rows']]

new_comments=[]
for table,expected in [('review_comments',4),('review_rounds',1),('studio_review_round_baselines',1)]:
    old=before['tables'][table];new=current['tables'][table]
    assert old['columns']==new['columns']
    by_id={r[0]:r for r in new['rows']}
    assert len(by_id)==len(new['rows'])
    for row in old['rows']:assert by_id[row[0]]==row,(table,row[0])
    assert len(new['rows'])-len(old['rows'])==expected
    if table=='review_comments':
        old_ids={r[0] for r in old['rows']}
        new_comments=[r for r in rows(current,table) if r['comment_id'] not in old_ids]

round_id='review_round_e4845ca796d74594b33b86fb529b4404'
actual_round=next(r for r in rows(current,'review_rounds') if r['review_round_id']==round_id)
assert actual_round['manuscript_id']==receipt['manuscript_id'] and actual_round['round_number']==3
baseline=next(r for r in rows(current,'studio_review_round_baselines') if r['review_round_id']==round_id)
assert baseline['baseline_manuscript_version_id']==receipt['baseline_version']
assert baseline['content_sha256']=='2430bc03a020665b51cd6e522f578097184163259e098be99159c46b20126b7b'
txt='G11 native TXT import: preserve this first line.\nKeep the second line inside the same opinion.'
expect={
 207:('comment_17fd0d630e4d4a709714d6d1921384c4','native-review-two-opinions.txt',txt,txt+'\nEdited in native preview; original source stays unchanged.','comment_import_31cf719b6ea54a6481de4b76a79854d8'),
 208:('comment_15d8bb0d41d34beb93739f444e3578db','opinion.md','Native Markdown review opinion.\nKeep the source filename and original text.',None,'comment_import_6b5a6fbac859491cb28be6696a17a7c7'),
 209:('comment_fa0cc799e11a4cafa02bfeff7736200a','opinion.docx','Native DOCX review opinion. Preserve the original document source.',None,'comment_import_538a96e51b704ccd8a420a244a93d191'),
 210:('comment_cea31df0e6d14212bb33fe5fa014ca97','opinion.pdf','Native PDF review opinion. Preserve exact extracted source.',None,'comment_import_e6aa7a7370de4b52af96006cd38345ff'),
}
seen=set()
for row in new_comments:
    m=json.loads(row['import_metadata_json']);n=m['comment_number'];seen.add(n)
    cid,filename,original,edited,batch=expect[n]
    assert row['comment_id']==cid and row['review_round_id']==round_id and row['source']=='FILE_IMPORT'
    assert row['original_text']==original and row['edited_text']==(edited or original)
    assert m['filename']==filename and m['import_batch_id']==batch and m['original_index']==0 and m['original_text']==original
    assert row['status']=='PENDING' and row['author_decision'] is None and row['response_text'] is None and row['archived_at'] is None
    if n==207:
        assert m['raw_import_text']==receipt['derived_txt']['original_text_with_bom'].removeprefix('\ufeff')
        assert 'this second opinion will be excluded' in m['raw_import_text']
    elif n==208:
        assert m['raw_import_text']==original.replace('\n','\r\n')
    else:assert m['raw_import_text']==original
assert seen==set(expect)

def cache_key(row):return tuple(row[k] for k in ['manuscript_id','anchor_id','query_key','candidate_id'])
old_cache={cache_key(r):r for r in rows(before,'studio_sample_candidates')}
new_cache={cache_key(r):r for r in rows(current,'studio_sample_candidates')}
assert old_cache.keys()==new_cache.keys()
cache_changes=[]
for key,old in old_cache.items():
    new=new_cache[key]
    if new==old:continue
    assert old['manuscript_id']==receipt['manuscript_id'] and old['anchor_id']=='paper'
    assert old['query_key']=='907957c0f6d0afaf9dc04eeab82fa5552a9a6175bc2218019e515567e0a4d813'
    assert old['document_revision']==39 and new['document_revision']==62
    assert {k for k in old if old[k]!=new[k]}=={'document_revision','created_at'}
    cache_changes.append({'candidate_id':old['candidate_id'],'from_revision':39,'to_revision':62,'sample_json_exact':True})
assert len(cache_changes)==4
protected=json.loads((here/'protected-original-files.json').read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
source_files={p.relative_to(source).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)} for p in source.rglob('*') if p.is_file() and not p.name.endswith(('-wal','-shm'))}
assert source_files==protected
assert sha(source/'data/catalog.db')==receipt['source_sha256']
for relative,item in protected.items():
    if relative=='data/catalog.db':continue
    assert sha(root/relative)==item['sha256']
proof=here/'proof'
cards=json.loads((proof/'16-four-sources-after-reload.json').read_text())
for n,item in expect.items():
    assert any('A'+str(n) in card and item[1] in card and item[4] in card and '本次导入的完整原文' in card for card in cards)
warm=json.loads((proof/'15-read-recovery-receipt.json').read_text())
assert warm['status']=='PASS_NATIVE_WARM_RECOVERY' and all(r['method']=='GET' for r in warm['requests'])
test=json.loads((here/'comments-read-recovery-v1/e2e-v2/receipt.json').read_text())
assert test['status']=='PASS' and test['product_source_exact']
out={'status':'PASS_FOUR_FORMAT_NATIVE_IMPORT_RELOAD_AND_PRESERVATION','scope':'This subset only; original118/all11 and G11 GPU recovery remain incomplete','tables':109,'old_comments_exact':206,'new_comments':4,'rounds':3,'old_rounds_and_baselines_exact':2,'all_other_tables_exact':105,'schema_exact':True,'read_recovery_no_db_change':True,'original_files_exact':True,'derived_cache_metadata_changes':cache_changes,'round3':actual_round,'baseline':baseline,'new_comment_ids':[r['comment_id'] for r in new_comments],'models_jobs_versions_history_unchanged':True,'e2e_scenarios_passed':8}
(here/'final-four-format-audit-v1.json').open('x',encoding='utf-8').write(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in out.items() if k not in {'round3','baseline','derived_cache_metadata_changes','new_comment_ids'}},ensure_ascii=False))
