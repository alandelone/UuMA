from pathlib import Path
repo=Path(__file__).resolve().parents[1]
source=(repo/'.tmp/scholar-template-mapping-refresh-v1.py').read_text(encoding='utf-8')
source=source.replace('scholar-hierarchy-runtime-final-v1.json','scholar-material-download-runtime-before-final-v1.json')
source=source.replace('scholar-hierarchy-refresh-v4.json','scholar-material-download-refresh-v1.json')
source=source.replace('scholar-template-mapping-build-v1.json','scholar-material-download-build-v2.json')
source=source.replace('scui-template-mapping-build-','scui-material-download-build-').replace("['document_revision']==49", "['document_revision']==65")
source=source.replace("path=repo/'.tmp/scholar-template-mapping-refresh-v1.json'", "path=repo/'.tmp/scholar-material-download-refresh-v2.json'")
source=source.replace('scholar-template-mapping-frontend-v1.log','scholar-material-download-frontend-v2.log')
source=source.replace('--max-old-space-size=1536','--max-old-space-size=512').replace("RAYON_NUM_THREADS='2',UV_THREADPOOL_SIZE='2'","RAYON_NUM_THREADS='1',UV_THREADPOOL_SIZE='1'")
exec(compile(source,__file__,'exec'))
