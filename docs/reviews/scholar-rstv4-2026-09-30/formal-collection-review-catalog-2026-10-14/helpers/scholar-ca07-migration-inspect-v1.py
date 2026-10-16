import importlib.util
from pathlib import Path
import json

path = Path('.tmp/scholar-ca07-native-v1.py')
spec = importlib.util.spec_from_file_location('ca07', path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
before = mod.read_json(mod.OUT / 'source-before.json')
root = Path(mod.read_json(mod.OUT / 'allocated.json')['root'])
after = mod.snap(root / 'data/catalog.db')
lookup = {(r[0],r[1]):r for r in after['schema']}
diffs = [{'key': [row[0],row[1]], 'before': row, 'after': lookup.get((row[0],row[1]))}
         for row in before['schema'] if lookup.get((row[0],row[1])) != row]
report = {'diffs':diffs,'new_columns':{name:sorted(set(after['tables'][name]['columns'])-set(t['columns']))
          for name,t in before['tables'].items()
          if after['tables'][name]['columns']!=t['columns']},
          'source_exact':mod.digest(mod.SOURCE)==mod.CONTRACT['source_raw_sha256']}
mod.exclusive_json(mod.OUT / 'migration-inspection.json', report)
print(json.dumps(report, indent=2))
