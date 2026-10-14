from pathlib import Path

code = Path(".tmp/scholar-template-build-v3.py").read_text(encoding="utf-8")
code = code.replace("scholar-template-build-v3", "scholar-g09-source-build-v1")
code = code.replace("scui-template-build-", "scui-g09-source-build-")
code = code.replace("127.0.0.1:8877", "127.0.0.1:8881")
code = code.replace("--max-old-space-size=1536", "--max-old-space-size=512")
code = code.replace("RAYON_NUM_THREADS='2', UV_THREADPOOL_SIZE='2'", "RAYON_NUM_THREADS='1', UV_THREADPOOL_SIZE='1'")
exec(compile(code, __file__, "exec"))
