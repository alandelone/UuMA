from pathlib import Path
repo=Path(__file__).resolve().parents[1]
prior=repo/'.tmp/scholar-template-mapping-runtime-before-upgrade-v1.py'
source=prior.read_text(encoding='utf-8').replace('scholar-template-mapping-refresh-v1.json','scholar-template-mapping-refresh-v2.json').replace('scholar-template-mapping-runtime-before-upgrade-v1.json','scholar-template-mapping-runtime-final-v1.json')
exec(compile(source,str(prior),'exec'))
