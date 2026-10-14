from pathlib import Path
code=Path('.tmp/scholar-g07-state-v1.py').read_text(encoding='utf-8')
start=code.index("expected_count={'single':")
end=code.index("assert sha(db)==digest",start)
replacement="""expected_count={'bulk100-imported':104,'remainder-imported':105,'final':105}[phase]
assert len(tables['review_comments'])==expected_count
single='G07 single software comment: preserve this entire block as one original opinion.\\n\\nSecond paragraph belongs to the same single comment.\\nKeep this line break; no scientific request.'
new=[r for r in tables['review_comments'] if r not in base['review_comments']]
assert len(new)==expected_count-2
bulk=read(out/'proof/101-complete-preview.values.json');raw_bulk=bulk['input'];texts=[r['value'] for r in bulk['rows']]
assert len(texts)==101 and raw_bulk=='\\n\\n'.join(texts)
for i,r in enumerate(new[:2],3):
    assert r['original_text']==r['edited_text']==single and r['status']=='PENDING' and r['archived_at'] is None
    metadata=json.loads(r['import_metadata_json']);assert metadata['comment_number']==i and metadata['original_text']==single and metadata['raw_import_text']==single
for index,r in enumerate(new[2:102]):
    assert r['original_text']==r['edited_text']==texts[index] and r['status']=='PENDING' and r['archived_at'] is None
    metadata=json.loads(r['import_metadata_json']);assert metadata['comment_number']==index+5 and metadata['original_index']==index and metadata['original_text']==texts[index] and metadata['raw_import_text']==raw_bulk
assert len(new[2:102])==100
if expected_count==105:
    last=new[-1];metadata=json.loads(last['import_metadata_json'])
    assert last['original_text']==last['edited_text']==texts[100] and metadata['comment_number']==105 and metadata['raw_import_text']==texts[100]
"""
code=code[:start]+replacement+code[end:]
code=code.replace("'whole_blank_line_text_exact':True", "'whole_blank_line_text_exact':True,'original101_retained_in_saved_bulk_sources':True")
exec(compile(code,__file__,'exec'))
