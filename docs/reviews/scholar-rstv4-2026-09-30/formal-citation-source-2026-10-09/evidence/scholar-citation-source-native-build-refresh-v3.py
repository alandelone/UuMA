from pathlib import Path
import hashlib,json
repo=Path.cwd(); fixture=json.loads((repo/'.tmp/scholar-citation-source-native-v1.json').read_text(encoding='utf-8'))
db=Path(fixture['root'])/'data/catalog.db';before=hashlib.sha256(db.read_bytes()).hexdigest()
source=(repo/'.tmp/scholar-citation-source-native-build-refresh-v2.py').read_text(encoding='utf-8')
source=source.replace("fixture['processes']['frontend']",'96508')
source=source.replace('1791540884000','1791541753000').replace('1791540910000','1791541756500')
source=source.replace('build-v2.','build-v3.').replace('build-v2.json','build-v3.json').replace('frontend-runtime-v2','frontend-runtime-v3').replace('build-refresh-v2','build-refresh-v3')
assert '96508' in source and 'build-refresh-v3.json' in source
exec(compile(source,__file__,'exec'))
assert hashlib.sha256(db.read_bytes()).hexdigest()==before
record=json.loads((repo/'.tmp/scholar-citation-source-build-refresh-v3.json').read_text(encoding='utf-8'));record['entire_database_bytes_preserved']=True
(repo/'.tmp/scholar-citation-source-build-refresh-v3.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
