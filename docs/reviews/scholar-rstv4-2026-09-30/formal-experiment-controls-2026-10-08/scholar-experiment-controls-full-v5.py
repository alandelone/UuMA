from pathlib import Path

prior = Path(__file__).with_name('scholar-experiment-controls-full-v1.py')
source = prior.read_text(encoding='utf-8').replace('scholar-experiment-controls-full-v1',
                                               'scholar-experiment-controls-full-v5')
source = source.replace('scholar-experiment-controls-full-inline-v1',
                        'scholar-experiment-controls-full-inline-v5')
exec(compile(source, str(prior), 'exec'))
