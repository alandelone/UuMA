from pathlib import Path
source=Path('.tmp/scholar-template-build-v3.py').read_text(encoding='utf-8').replace('scholar-template-build-v3','scholar-g01-loading-build-v1').replace('scui-template-build-','scui-g01-loading-build-').replace('127.0.0.1:8877','127.0.0.1:8881').replace('--max-old-space-size=1536','--max-old-space-size=512').replace("RAYON_NUM_THREADS='2', UV_THREADPOOL_SIZE='2'","RAYON_NUM_THREADS='1', UV_THREADPOOL_SIZE='1'")
exec(compile(source,__file__,'exec'))
