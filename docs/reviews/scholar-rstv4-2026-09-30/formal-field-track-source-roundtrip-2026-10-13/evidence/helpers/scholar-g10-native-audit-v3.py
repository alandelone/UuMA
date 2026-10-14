from pathlib import Path
code=Path('.tmp/scholar-g10-native-audit-v2.py').read_text(encoding='utf-8')
code=code.replace('final-audit-v2','final-audit-v3')
code=code.replace("(context/'failed-audit-v1.py').write_bytes((repo/'.tmp/scholar-g10-native-audit-v1.py').read_bytes())", "(context/'failed-audit-v1.py').write_bytes((repo/'.tmp/scholar-g10-native-audit-v1.py').read_bytes())\n(context/'failed-audit-v2.py').write_bytes((repo/'.tmp/scholar-g10-native-audit-v2.py').read_bytes())")
code=code.replace("This is initializer and", "V2 then rejected two concurrent shared default-endpoint source changes. RO byte comparison proves ONLY one default endpoint literal changed in each model_gateway.py/skeleton_dspy.py; reversing the literal in memory exactly reconstructs both old hashes. No product file reverted or remote call permitted. V3 requires those exact old/new hashes and all175 other sources unchanged, freezes all177 current bytes and pairs with current-full-tests-v2. This is initializer and")
old="for name,digest in vector.items():assert sha(repo.parent/'RSTV4'/name)==digest,name"
assert code.count(old)==1
new="""changes=load(repo/'.tmp/scholar-g10-native-v1/concurrent-source-change-v1.json')
assert set(changes)=={'src\\\\rstv4\\\\model_gateway.py','src\\\\rstv4\\\\skeleton_dspy.py'}
for name,digest in vector.items():
    p=repo.parent/'RSTV4'/name
    if name not in changes:
        assert sha(p)==digest,name
        continue
    item=changes[name]
    assert item['expected']==digest and sha(p)==item['actual'],name
    raw=p.read_bytes()
    assert raw.count(b'https://api.95963210.xyz/v1')==1,name
    restored=raw.replace(b'https://api.95963210.xyz/v1',b'http://127.0.0.1:8080/v1')
    assert hashlib.sha256(restored).hexdigest()==digest,name
    (out/(p.name+'.current.raw')).write_bytes(raw)
current_vector={name:sha(repo.parent/'RSTV4'/name) for name in vector}
(out/'current177-source-vector.json').write_text(json.dumps(current_vector,indent=2),encoding='utf-8')
"""
code=code.replace(old,new)
code=code.replace("'all177_backend_sources_exact':True","'unchanged_backend_sources':175,'explicit_default_endpoint_literal_changes':changes,'all177_current_sources_frozen':True")
exec(compile(code,__file__,'exec'))
