from pathlib import Path

prior = Path(__file__).with_name('scholar-experiment-controls-browser-server-v1.py')
source = prior.read_text(encoding='utf-8')
source = source.replace('scui-plan-browser-', 'scui-plan-browser-v2-')
source = source.replace('scholar-experiment-controls-browser-v1.json',
                        'scholar-experiment-controls-browser-v2.json')
source = source.replace('import json,os\\n', 'import json,os,sys\\n')
source = source.replace("'selected_env':os.environ.get('SELECTED_ENV')",
                        "'selected_env':os.environ.get('SELECTED_ENV'),'executable':sys.executable")
exec(compile(source, str(prior), 'exec'))
