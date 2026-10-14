from pathlib import Path
code=Path('.tmp/scholar-g01-loading-runtime-refresh-v1.py').read_text(encoding='utf-8')
code=code.replace("'scui-g01-loading-build-1ou2ff1y'",'root.parent.name')
code=code.replace('scholar-g01-loading','scholar-g02-source').replace('scui-g01-loading-build-','scui-g02-source-build-')
code=code.replace("chain=inventory['chains']['3008'];backend=inventory['chains']['8881']","chain=json.loads((repo/'.tmp/scholar-g01-loading-runtime-refresh-v1.json').read_text(encoding='utf-8'))['new_verified_port3008_chain'];backend=json.loads((repo/'.tmp/scholar-g02-typed-native-v1/runtime.json').read_text(encoding='utf-8'))['new_verified_port8881_chain']")
assert "chain=json.loads" in code and "assert root.parent.name in" in code
exec(compile(code,__file__,'exec'))
