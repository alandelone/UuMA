from pathlib import Path
code=Path('.tmp/scholar-g07-state-v1.py').read_text(encoding='utf-8')
start=code.index("expected_count={'single':");end=code.index("assert sha(db)==digest",start)
replacement="""expected_count={'corrected100':204,'corrected101':205,'final':205}[phase]
assert len(tables['review_comments'])==expected_count
single='G07 single software comment: preserve this entire block as one original opinion.\\n\\nSecond paragraph belongs to the same single comment.\\nKeep this line break; no scientific request.'
new=[r for r in tables['review_comments'] if r not in base['review_comments']]
assert len(new)==expected_count-2
old_bulk=read(out/'proof/101-complete-preview.values.json');old_texts=[r['value'] for r in old_bulk['rows']]
corrected=read(out/'proof/fixed-after-100-retained-101.values.json');texts=[r['value'] for r in corrected['rows']];raw_corrected='\\n\\n'.join(texts)
assert len(old_texts)==len(texts)==101 and corrected['input']==texts[100]
for i,r in enumerate(new[:2],3):
    assert r['original_text']==r['edited_text']==single
    metadata=json.loads(r['import_metadata_json']);assert metadata['comment_number']==i and metadata['raw_import_text']==single
for index,r in enumerate(new[2:102]):
    assert r['original_text']==r['edited_text']==old_texts[index]
    metadata=json.loads(r['import_metadata_json']);assert metadata['comment_number']==index+5 and metadata['original_index']==index and metadata['raw_import_text']==old_bulk['input']
for index,r in enumerate(new[102:202]):
    assert r['original_text']==r['edited_text']==texts[index]
    metadata=json.loads(r['import_metadata_json']);assert metadata['comment_number']==index+105 and metadata['original_index']==index and metadata['raw_import_text']==raw_corrected
assert len(new[102:202])==100
if expected_count==205:
    last=new[-1];metadata=json.loads(last['import_metadata_json'])
    assert last['original_text']==last['edited_text']==texts[100] and metadata['comment_number']==205 and metadata['original_index']==100 and metadata['raw_import_text']==raw_corrected
for r in new:assert r['status']=='PENDING' and r['archived_at'] is None
"""
code=code[:start]+replacement+code[end:]
last_print=code.index("print(json.dumps({'new_comment_ids':")
code=code[:last_print]+"print(json.dumps({'total_comment_count':len(tables['review_comments']),'last_number':json.loads(new[-1]['import_metadata_json'])['comment_number'],'old_original101_source_preserved':True,'corrected_original101_source_preserved':True},ensure_ascii=False),flush=True)\n"
exec(compile(code,__file__,'exec'))
