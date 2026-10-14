import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

repo=Path(__file__).resolve().parents[1]
receipt=json.loads((repo/'.tmp/scholar-overview-services.json').read_text(encoding='utf-8'))
db=Path(receipt['root']).resolve()/'data/catalog.db'
before=json.loads((repo/'.tmp/scholar-review-pre-migration-rows-v1.json').read_text(encoding='utf-8'))
sha=lambda raw:hashlib.sha256(raw).hexdigest()
canonical=lambda value:sha(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode())
with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as conn:
 tables=[row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
 assert set(tables)==set(before)|{'catalog_review_actions'}
 actual={table:conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall() for table in tables}
 for table,old in before.items():
  rows=[list(row) for row in actual[table]]
  if table=='schema_version':
   original={row[0]:row for row in old};new={row[0]:row for row in rows}
   assert new.keys()==original.keys()
   for component in original:
    if component=='catalog':assert original[component][1]==6 and new[component][1]==7 and new[component][2]
    else:assert new[component]==original[component]
  else:assert rows==old,table
 assert actual['catalog_review_actions']==[]
 schema=conn.execute('SELECT * FROM sqlite_master ORDER BY name').fetchall()
with closing(sqlite3.connect((repo/'.tmp/scholar-review-pre-migration-v1.db').as_uri()+'?mode=ro',uri=True)) as conn:
 old={row[:3]:row[4] for row in conn.execute('SELECT * FROM sqlite_master ORDER BY name')}
new={row[:3]:row[4] for row in schema}
assert set(new)-set(old)=={('table','catalog_review_actions','catalog_review_actions'),('index','idx_catalog_review_actions_case','catalog_review_actions'),('index','sqlite_autoindex_catalog_review_actions_1','catalog_review_actions'),('index','sqlite_autoindex_catalog_review_actions_2','catalog_review_actions')}
assert all(new[key]==value for key,value in old.items())
proof={'database_sha256':sha(db.read_bytes()),'all_table_sha256':{t:canonical(rows) for t,rows in actual.items()},
       'schema_sha256':canonical(schema),'before_database_sha256':sha((repo/'.tmp/scholar-review-pre-migration-v1.db').read_bytes()),
       'old_rows_preserved':True,'original_tables':96,'current_tables':97,'new_review_actions':0,
       'allowed_change':'append-only review action table and its indexes; catalog schema version6->7 application'}
with (repo/'.tmp/scholar-review-post-migration-baseline-v1.json').open('x',encoding='utf-8') as h:json.dump(proof,h,indent=2)
print('All 96 original tables/rows preserved, v7 ledger empty, 97 current tables verified.')
