from pathlib import Path

repo = Path(__file__).resolve().parents[1]
source = (repo / '.tmp/scholar-experiment-artifacts-full-v1.py').read_text(encoding='utf-8')
source = source.replace('scholar-experiment-artifacts-full', 'scholar-experiment-controls-full')
source = source.replace("'experiment.py']", "'experiment.py','experiment_workspace.py']")
source = source.replace("'tests/test_experiment_artifact_trace.py'])", "'tests/test_experiment_artifact_trace.py','tests/test_experiment_workspace.py'])")
source = source.replace("commands.append(['git','diff','--check'])", "commands.append(['node','tests/catalog_experiments.mjs'])\ncommands.append(['node','--check','src/rstv4/catalog_experiments.js'])\ncommands.append(['git','diff','--check'])")
path = repo / '.tmp/scholar-experiment-controls-full-v1.py'
with path.open('x', encoding='utf-8') as handle:
    handle.write(source)
