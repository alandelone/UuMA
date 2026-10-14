from pathlib import Path

path=Path(__file__).with_name('scholar-withdrawal-original-final-v1.py')
source=path.read_text(encoding='utf-8').replace('scholar-withdrawal-original-final-v1.json','scholar-withdrawal-original-final-v3.json')
exec(compile(source,str(path),'exec'))
