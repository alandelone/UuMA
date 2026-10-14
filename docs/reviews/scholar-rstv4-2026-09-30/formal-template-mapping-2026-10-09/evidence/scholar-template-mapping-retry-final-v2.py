from pathlib import Path
repo=Path(__file__).resolve().parents[1]
prior=repo/'.tmp/scholar-template-mapping-retry-final-v1.py'
source=prior.read_text(encoding='utf-8').replace("assert body['adoption']['template_instance_id']==template['template_instance_id']", "assert body['idempotent_replay'] and body['operation']['resulting_revision']==56").replace('scholar-template-mapping-retry-final-v1.json','scholar-template-mapping-retry-final-v2.json')
exec(compile(source,str(prior),'exec'))
