from pathlib import Path
code=Path('.tmp/scholar-g06-state-v1.py').read_text(encoding='utf-8')
code=code.replace("print(json.dumps(receipt,ensure_ascii=False)[:7000],flush=True)", "print(json.dumps({k:v for k,v in receipt.items() if k!='review_tables'},ensure_ascii=False),flush=True)\nprint(json.dumps({'comments':[{k:r[k] for k in ['comment_id','status','archived_at']} for r in tables['review_comments']], 'links':tables['comment_changes'],'new_changes':[{k:v for k,v in r.items() if k not in {'before_json','after_json'}} for r in tables['studio_changes'] if r not in base['studio_changes']]},ensure_ascii=False),flush=True)")
exec(compile(code,__file__,'exec'))
