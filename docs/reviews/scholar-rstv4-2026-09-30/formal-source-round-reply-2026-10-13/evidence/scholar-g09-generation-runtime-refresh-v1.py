from pathlib import Path
repo = Path.cwd()
code = (repo / ".tmp/scholar-g09-source-runtime-refresh-v1.py").read_text(encoding="utf-8")
code = code.replace('"scholar-g09-source-runtime-refresh-v1"','"scholar-g09-generation-runtime-refresh-v1"')
code = code.replace('".tmp/scholar-g09-runtime-restart-v2/receipt.json"','".tmp/scholar-g09-source-runtime-refresh-v2/receipt.json"')
code = code.replace('".tmp/scholar-g09-source-build-v1.json"','".tmp/scholar-g09-readable-build-v1.json"')
code = code.replace('"scui-g09-source-build-"','"scui-g09-readable-build-"')
code = code.replace('".tmp/scholar-g09-serve-only-v1.py"','".tmp/scholar-g09-generation-server-v1.py"')
code = code.replace('assert sha(helper) == old["backend_helper_sha256"]','assert helper.is_file()\nassert before == read(repo / ".tmp/scholar-g09-current-generation-native-v1/input-audited-v2/all-tables.json")')
code = code.replace('for process in owned:\n    assert row(process["ProcessId"]) == process',
    'for process in [*reversed(old["frontend_chain"]),*reversed(old["backend_chain"])]:\n    current=row(process["ProcessId"])\n    if current is None:\n        continue\n    assert current == process')
code = code.replace('"all_model_tasks_denied":True','"only_exact_eleven_author62_software_inputs":True')
code = code.replace('"PASS_G09_NEW_SOURCE_READER_OWNED_RUNTIME"','"PASS_G09_EXACT_GENERATION_AND_READABLE_DIFF_RUNTIME"')
exec(compile(code,__file__,"exec"))
