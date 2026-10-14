from pathlib import Path

repo = Path(__file__).resolve().parents[1]
source = (repo / '.tmp/scholar-experiment-artifacts-packaging-v1.py').read_text(encoding='utf-8')
source = source.replace('scholar-experiment-artifacts', 'scholar-experiment-controls')
source = source.replace("'experiment.py']", "'experiment.py','experiment_workspace.py','catalog_experiments.js']")
source = source.replace('PASS_ALL_EIGHT_SHIPPED_CATALOG_ASSETS', 'PASS_ALL_NINE_SHIPPED_CATALOG_ASSETS')
source = source.replace('all seven shipped JavaScript', 'all eight shipped JavaScript')
with (repo / '.tmp/scholar-experiment-controls-packaging-v1.py').open('x', encoding='utf-8') as h:
    h.write(source)
source = (repo / '.tmp/scholar-experiment-artifacts-refresh-v1.py').read_text(encoding='utf-8')
source = source.replace('scholar-experiment-artifacts', 'scholar-experiment-controls')
with (repo / '.tmp/scholar-experiment-controls-refresh-v1.py').open('x', encoding='utf-8') as h:
    h.write(source)
source = (repo / '.tmp/scholar-experiment-artifacts-original-final-v1.py').read_text(encoding='utf-8')
source = source.replace('scholar-experiment-artifacts', 'scholar-experiment-controls')
source = source.replace("('/catalog-track-decisions.js', 'catalog_track_decisions.js')]:",
                        "('/catalog-track-decisions.js', 'catalog_track_decisions.js'), ('/catalog-experiments.js', 'catalog_experiments.js')]:")
with (repo / '.tmp/scholar-experiment-controls-original-final-v1.py').open('x', encoding='utf-8') as h:
    h.write(source)
