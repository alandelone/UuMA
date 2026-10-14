from pathlib import Path
import hashlib,json
repo=Path.cwd();source=repo/'.tmp/scholar-g02-partial-state-v1.py';raw=source.read_bytes()
context=repo/'.tmp/scholar-g02-partial-native-v1/auditor-sqlite-counter-context-v1';context.mkdir(exist_ok=True)
(context/'original-auditor.py').write_bytes(raw)
(context/'diagnosis.json').write_text(json.dumps({'failure':'Original immutability auditor treated sqlite_sequence as an immutable application row.','observed_before':[{'name':'research_discussion_messages','seq':9}],'observed_after':[{'name':'research_discussion_messages','seq':11}],'execution_contract':'The native discussion legitimately appends exactly two messages. Require this sole counter to advance from 9 to 11, matching the exact 11 stored messages; keep all other old application row preservation assertions. No product assertion or source changed.','original_auditor_sha256':hashlib.sha256(raw).hexdigest()},indent=2),encoding='utf-8')
code=source.read_text(encoding='utf-8')
code=code.replace("/phase;out.mkdir()","/(phase+'-v2');out.mkdir()")
code=code.replace("assert len(tables)==109","assert len(tables)==109\nassert baseline['sqlite_sequence']==[{'name':'research_discussion_messages','seq':9}] and tables['sqlite_sequence']==[{'name':'research_discussion_messages','seq':11}]")
code=code.replace("{'studio_documents','manuscripts','studio_sample_candidates'}","{'studio_documents','manuscripts','studio_sample_candidates','sqlite_sequence'}")
assert "(phase+'-v2')" in code and "tables['sqlite_sequence']==" in code
exec(compile(code,__file__,'exec'))
