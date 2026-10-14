from pathlib import Path

code = Path(".tmp/scholar-g09-source-checks-v1.py").read_text(encoding="utf-8")
code = code.replace("checks-v1", "checks-v2")
code = code.replace('for name, command, cwd in checks:', 'checks = checks[1:]\nfor name, command, cwd in checks:')
exec(compile(code, __file__, "exec"))
