from pathlib import Path
repo=Path(__file__).resolve().parents[1]
prior=repo/'.tmp/scholar-experiment-controls-original-final-v2.py'
source=prior.read_text(encoding='utf-8').replace("path = repo / '.tmp/scholar-experiment-controls-original-final-v2.json'", "path = repo / '.tmp/scholar-hierarchy-original-final-v1.json'")
exec(compile(source,str(prior),'exec'))
