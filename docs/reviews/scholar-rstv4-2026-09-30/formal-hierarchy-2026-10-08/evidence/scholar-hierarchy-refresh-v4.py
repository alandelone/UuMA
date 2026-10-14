import ast
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
source=(repo/'.tmp/scholar-hierarchy-refresh-v2.py').read_text(encoding='utf-8')
tree=ast.parse((repo/'.tmp/scholar-hierarchy-refresh-v3.py').read_text(encoding='utf-8'))
query=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='query' for t in node.targets))
start=source.index('query="""');end=source.index('"""',start+9)+3
source=source[:start]+query+source[end:]
source=source.replace('capture_output=True,text=True,check=True','capture_output=True,text=True,encoding="utf-8",check=True')
source=source.replace('CommandLine,CreationDate','CommandLine,ExecutablePath,CreationDate')
source=source.replace("'node.exe' in old['CommandLine']", "old['ExecutablePath'].lower().endswith('node.exe')")
source=source.replace('scholar-hierarchy-refresh-v2.json','scholar-hierarchy-refresh-v4.json')
exec(compile(source,__file__,'exec'))
