from pathlib import Path
code=Path('.tmp/scholar-g09-recovery-full-tests-v1.py').read_text(encoding='utf-8')
code=code.replace('scholar-g09-recovery-full-tests-v1','scholar-g10-current-full-tests-v3')
old="for p in (source / \"src/rstv4\").rglob(\"*\")"
assert code.count(old)==1
code=code.replace(old,"for directory in [source / 'src/rstv4', source / 'tests'] for p in directory.rglob('*')")
exec(compile(code,__file__,'exec'))
