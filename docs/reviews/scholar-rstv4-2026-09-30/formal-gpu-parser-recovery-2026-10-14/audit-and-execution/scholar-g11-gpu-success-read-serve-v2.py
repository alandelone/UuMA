from pathlib import Path
code=Path(__file__).with_name('scholar-g11-gpu-healthy-serve-v1.py').read_text(encoding='utf-8')
code=code.replace('used=False','used=True')  # Native attempt6 retry was already consumed.
code=code.replace("'/api/catalog/discussion/history'}", "'/api/catalog/discussion/history','/api/catalog/papers/query'}")
code=code.replace("here/'service-start.json'","here/'service-start-v2.json'")
exec(compile(code,__file__,'exec'))
