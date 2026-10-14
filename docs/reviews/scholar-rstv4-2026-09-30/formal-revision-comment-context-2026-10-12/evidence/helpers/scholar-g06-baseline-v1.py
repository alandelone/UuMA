from pathlib import Path
code=Path('.tmp/scholar-g04-baseline-v1.py').read_text(encoding='utf-8')
code=code.replace('scholar-g04-native-v1', 'scholar-g06-native-v1')
code=code.replace("repo/'.tmp/scholar-g03-native-v1/final-all-tables.json'", "repo/'.tmp/scholar-g04-native-v1/reopened-v2/all-tables.json'")
code=code.replace("len(tables['studio_model_calls'])==14", "len(tables['studio_model_calls'])==16")
code=code.replace("repo/'.tmp/scholar-g03-native-v1/online-runtime.json'", "repo/'.tmp/scholar-g04-native-v1/runtime-v2.json'")
code=code.replace('PASS_CURRENT_G04_BASELINE', 'PASS_CURRENT_G06_BASELINE').replace("'author_revision':13", "'author_revision':14")
code=code.replace("print(json.dumps({'jobs':", "print(json.dumps({'jobs':")
# Keep the structured receipt concise; the complete table snapshot retains all jobs/results.
code=code[:code.index("print(json.dumps({'jobs':")]
exec(compile(code,__file__,'exec'))
