from pathlib import Path

prior = Path(__file__).with_name('scholar-durable-model-reconcile-step-v4.py')
source = prior.read_text(encoding='utf-8')
exec(compile(source, str(prior), 'exec'))
