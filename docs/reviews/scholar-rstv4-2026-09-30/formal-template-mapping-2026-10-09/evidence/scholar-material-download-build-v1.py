from pathlib import Path
repo=Path(__file__).resolve().parents[1]
source=(repo/'.tmp/scholar-template-build-v3.py').read_text(encoding='utf-8')
source=source.replace('scholar-template-build-v3.','scholar-material-download-build-v1.').replace('scui-template-build-','scui-material-download-build-')
source=source.replace('--max-old-space-size=1536','--max-old-space-size=512').replace("RAYON_NUM_THREADS='2', UV_THREADPOOL_SIZE='2'","RAYON_NUM_THREADS='1', UV_THREADPOOL_SIZE='1'")
exec(compile(source,__file__,'exec'))
