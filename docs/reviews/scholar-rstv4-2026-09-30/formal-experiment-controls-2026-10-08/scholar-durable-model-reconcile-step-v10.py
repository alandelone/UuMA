from pathlib import Path

prior = Path(__file__).with_name('scholar-durable-model-reconcile-step-v4.py')
exec(compile(prior.read_text(encoding='utf-8'), str(prior), 'exec'))
