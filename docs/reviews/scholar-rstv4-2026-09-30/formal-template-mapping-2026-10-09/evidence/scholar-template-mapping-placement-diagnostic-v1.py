import json
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
receipt=json.loads((repo/'.tmp/scholar-template-mapping-observe-final-compensate-template-v1.json').read_text(encoding='utf-8'))
for item in receipt['operations']:
    print(item['operation']['resulting_revision'],[{k:v for k,v in s.items() if k not in ['paragraphs','paragraph_groups']} for s in item['after']['sections'] if s['title'] in ['Author child Ω','Author grandchild']])
