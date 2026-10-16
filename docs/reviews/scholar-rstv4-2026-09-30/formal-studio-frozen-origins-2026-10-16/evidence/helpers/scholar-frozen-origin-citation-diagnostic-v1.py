from pathlib import Path
import json, urllib.request

repo = Path(__file__).resolve().parents[1]
here = repo/'.tmp/scholar-frozen-origin-native-v1'
context = json.loads((here/'http-0021-response.json').read_text(encoding='utf8'))
views = {}
for name, key in [('baseline','baseline_manuscript_version_id'),('target','generated_version_id')]:
    identifier = context['state'][key]
    url = f"http://127.0.0.1:8877/api/manuscripts/{context['state']['manuscript_id']}/generated-versions/{identifier}"
    with urllib.request.urlopen(url,timeout=30) as response:
        raw = response.read()
    (here/f'citation-diagnostic-{name}-view.json').write_bytes(raw)
    view = json.loads(raw)
    pid = next(r['paragraph_id'] for r in context['evidence'] if r['thought_id']=='thought_009a96629cb14586b44697b3ec73f2bc')
    views[name] = {'block':next(b for b in view['blocks'] if b['object_id']==pid),
                   'realization':next((r for r in view.get('realizations',[]) if r['paragraph_id']==pid),None)}
(here/'citation-diagnostic-exact-beta.json').write_text(json.dumps(views,indent=2),encoding='utf8')
print(json.dumps(views,indent=2))
