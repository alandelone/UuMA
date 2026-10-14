from pathlib import Path
code = Path(".tmp/scholar-g09-source-build-v1.py").read_text(encoding="utf-8")
code = code.replace('"scholar-g09-source-build-v1"', '"scholar-g09-readable-build-v1"')
code = code.replace('"scui-g09-source-build-"', '"scui-g09-readable-build-"')
exec(compile(code,__file__,"exec"))
