import ast,json,subprocess
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
tree=ast.parse((repo/'.tmp/scholar-hierarchy-refresh-v3.py').read_text(encoding='utf-8'))
inner=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='query' for t in node.targets))
query=ast.literal_eval(ast.parse(inner).body[0].value)
result=json.loads(subprocess.run(['powershell','-NoProfile','-Command',query],capture_output=True,text=True,encoding='utf-8',check=True).stdout)
with (repo/'.tmp/scholar-hierarchy-owner-diagnostic-v1.json').open('x',encoding='utf-8') as h:json.dump(result,h,indent=2)
print(json.dumps(result,ensure_ascii=False))
