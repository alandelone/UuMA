from pathlib import Path
code=Path('.tmp/scholar-g06-state-v1.py').read_text(encoding='utf-8')
code=code.replace("row['manuscript_id']==a:continue", "row['manuscript_id'] in {a,'manuscript_bea23f3050174ed1a0df075a32c25e13'}:continue")
needle="assert all(sha(r['storage_path'])==r['sha256'] for r in tables['studio_artifacts']) and sha(db)==digest"
extra="""b='manuscript_bea23f3050174ed1a0df075a32c25e13'
b_doc=next(r for r in tables['studio_documents'] if r['manuscript_id']==b);old_b=json.loads(next(r for r in base['studio_documents'] if r['manuscript_id']==b)['document_json'])
assert b_doc['revision']==2
old_b['abstract']+=' G06 cross-manuscript edit has no A01/A02 context.'
assert old_b==json.loads(b_doc['document_json'])
assert next(r for r in tables['manuscripts'] if r['manuscript_id']==b)['workflow_stage']=='DRAFTING'
b_changes=[r for r in tables['studio_changes'] if r not in base['studio_changes'] and r['manuscript_id']==b]
assert len(b_changes)==1 and not any(r['change_id']==b_changes[0]['change_id'] for r in tables['comment_changes'])
assert doc['revision']==18
"""
assert code.count(needle)==1;code=code.replace(needle,extra+needle)
code=code.replace("print(json.dumps(receipt,ensure_ascii=False)[:7000],flush=True)", "print(json.dumps({k:v for k,v in receipt.items() if k!='review_tables'},ensure_ascii=False),flush=True)\nprint(json.dumps({'b_author_revision':b_doc['revision'],'b_change_id':b_changes[0]['change_id'],'b_has_no_A_comment_links':True,'links':tables['comment_changes']},ensure_ascii=False),flush=True)")
exec(compile(code,__file__,'exec'))
