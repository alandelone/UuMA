from pathlib import Path
code=Path('.tmp/scholar-g03-runtime-refresh-v1.py').read_text(encoding='utf-8')
code=code.replace('scholar-g03-build-v1','scholar-g07-build-v1').replace('scholar-g03-front-v1','scholar-g07-front-v1').replace('scui-g03-build-','scui-g07-build-').replace('scholar-g03-runtime','scholar-g07-runtime')
code=code.replace('len(checks)==5','len(checks)==6')
code=code.replace('scholar-g02-source-runtime-refresh-v1.json','scholar-g03-runtime-v2-refresh-v1.json')
code=code.replace("repo/'.tmp/scholar-g02-typed-native-v1/runtime.json'", "repo/'.tmp/scholar-g04-native-v1/runtime-v2.json'")
code=code.replace("['new_verified_port8881_chain']", "['chain']")
exec(compile(code,__file__,'exec'))
