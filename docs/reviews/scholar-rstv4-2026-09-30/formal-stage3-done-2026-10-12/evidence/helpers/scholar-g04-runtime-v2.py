from pathlib import Path
code=Path('.tmp/scholar-g04-runtime-v1.py').read_text(encoding='utf-8')
code=code.replace("baseline=read(out/'baseline-all-tables.json')", "baseline=read(out/'first-failed-check/all-tables.json')")
code=code.replace("len(before['studio_model_calls'])==14", "len(before['studio_model_calls'])==15")
code=code.replace("backend=read(repo/'.tmp/scholar-g03-native-v1/online-runtime.json')['chain']", "backend=read(out/'runtime.json')['chain']")
code=code.replace('scholar-g04-native-server-v1.py', 'scholar-g04-native-server-v2.py').replace("8881,'server'", "8881,'server-v2'")
code=code.replace("(out/'runtime.json')", "(out/'runtime-v2.json')")
# Input replacement above deliberately reads the previous v1 runtime, never the new receipt.
code=code.replace("backend=read(out/'runtime-v2.json')['chain']", "backend=read(out/'runtime.json')['chain']")
assert "baseline=read(out/'first-failed-check/all-tables.json')" in code
exec(compile(code,__file__,'exec'))
