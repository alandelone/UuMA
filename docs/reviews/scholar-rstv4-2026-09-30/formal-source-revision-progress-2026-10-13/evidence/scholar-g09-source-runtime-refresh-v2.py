from pathlib import Path

code = Path(".tmp/scholar-g09-source-runtime-refresh-v1.py").read_text(encoding="utf-8")
code = code.replace('"scholar-g09-source-runtime-refresh-v1"', '"scholar-g09-source-runtime-refresh-v2"')
code = code.replace('assert all(row(v["ProcessId"]) == v for v in owned)',
    'assert all(row(v["ProcessId"]) is None for v in old["frontend_chain"])\nassert all(row(v["ProcessId"]) == v for v in old["backend_chain"])\nassert before == read(repo / ".tmp/scholar-g09-source-runtime-refresh-v1/before-all-tables.json")')
code = code.replace('assert listeners(3008) == [old["frontend_chain"][0]["ProcessId"]]', 'assert not listeners(3008)')
code = code.replace('for process in owned:\n    assert row(process["ProcessId"]) == process',
    'for process in reversed(old["backend_chain"]):\n    current = row(process["ProcessId"])\n    if current is None:\n        continue\n    assert current == process')
exec(compile(code, __file__, "exec"))
