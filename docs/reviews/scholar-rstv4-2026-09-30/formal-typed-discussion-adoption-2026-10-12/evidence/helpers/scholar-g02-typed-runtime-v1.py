from pathlib import Path
source=Path('.tmp/scholar-g02-partial-runtime-v1.py').read_text(encoding='utf-8')
source=source.replace("out=repo/'.tmp/scholar-g02-partial-native-v1'","out=repo/'.tmp/scholar-g02-typed-native-v1'")
source=source.replace("['revision']==11","['revision']==12").replace("['studio_model_calls'])==11","['studio_model_calls'])==12").replace("['studio_chat_messages'])==9","['studio_chat_messages'])==11")
source=source.replace("backend=inventory['chains']['8881']","backend=json.loads((repo/'.tmp/scholar-g02-partial-native-v1/runtime.json').read_text(encoding='utf-8'))['new_verified_port8881_chain']")
source=source.replace("==104544","==118440").replace('scholar-g02-partial-native-server-v1.py','scholar-g02-typed-native-server-v1.py').replace('PASS_G02_SOFTWARE_GATEWAY_READY','PASS_G02_TYPED_SOFTWARE_GATEWAY_READY')
assert "backend=json.loads" in source and "['revision']==12" in source
exec(compile(source,__file__,'exec'))
