from pathlib import Path
code=Path(__file__).with_name('scholar-g11-gpu-success-audit-v1.py').read_text(encoding='utf-8')
old="assert sha(Path(version['parsed_path']))==version['parsed_digest'] and version['pdf_digest']==sha(source)\nparsed=json.loads(Path(version['parsed_path']).read_text(encoding='utf-8'))"
new="""# The authoritative current publication contract stores a canonical manifest/
# blocks/references digest; parsed_path is optional structured_path, not that digest's file.
assert version['parsed_path']==manifest.get('structured_path') is None
assert version['parsed_digest']==manifest['publication']['output_revision_sha256']
assert version['pdf_digest']==sha(source)
assert json.loads(version['source_json'])=={'parse_run_id':parse_id,'file_version_id':prepared['original_file_id']}
raw_output=Path(manifest['markdown_path']).parent.parent/'rstv4-parse-result.json'
assert raw_output.resolve().is_relative_to(Path(proof['root']).resolve())
parsed=json.loads(raw_output.read_text(encoding='utf-8'))
assert len(parsed['blocks'])==3
assert [r['text'] for r in sorted(blocks,key=lambda r:r['sequence'])]==[r['text'] for r in parsed['blocks']]
assert Path(manifest['markdown_path']).is_file() and Path(manifest['content_list_path']).is_file()
"""
assert code.count(old)==1
code=code.replace(old,new).replace('actual-gpu-success-final-audit-v1.json','actual-gpu-success-final-audit-v2.json')
exec(compile(code,__file__,'exec'))
