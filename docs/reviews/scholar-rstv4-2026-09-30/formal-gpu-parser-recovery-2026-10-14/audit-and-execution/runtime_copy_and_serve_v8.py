from pathlib import Path
code=Path(__file__).with_name('runtime_copy_and_serve_v7.py').read_text(encoding='utf-8')
assert code.count('source-repair-v1.json')==1
code=code.replace('source-repair-v1.json','source-repair-v2.json')
exec(compile(code,__file__,'exec'))
