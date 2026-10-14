from pathlib import Path
repo=Path(__file__).resolve().parents[1]
prior=repo/'.tmp/scholar-template-mapping-aggregate-v1.py'
source=prior.read_text(encoding='utf-8').replace("'UNPLACED_ORIGINAL'", "'UNPLACED'").replace('scholar-template-mapping-aggregate-v1.json','scholar-template-mapping-aggregate-v2.json')
exec(compile(source,str(prior),'exec'))
