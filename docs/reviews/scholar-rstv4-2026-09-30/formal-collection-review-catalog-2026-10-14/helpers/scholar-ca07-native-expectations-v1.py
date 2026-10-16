from pathlib import Path
import sqlite3
import json

repo = Path.cwd()
out = repo / '.tmp/scholar-ca07-native-v1'
definitions = {
    'default-page1': ('p.updated_at DESC,p.paper_id ASC', '', 0),
    'default-page2': ('p.updated_at DESC,p.paper_id ASC', '', 50),
    'default-back-page1': ('p.updated_at DESC,p.paper_id ASC', '', 0),
    'mixed-priority': ('(p.published_year IS NULL),p.published_year DESC,p.updated_at ASC,p.paper_id ASC', '', 0),
    'reversed-priority': ('p.updated_at ASC,(p.published_year IS NULL),p.published_year DESC,p.paper_id ASC', '', 0),
    'tied-page1': ('p.paper_id ASC', "AND p.published_year IS NULL AND p.authors_json='[]'", 0),
    'tied-page2': ('p.paper_id ASC', "AND p.published_year IS NULL AND p.authors_json='[]'", 50),
    'tied-back-page1': ('p.paper_id ASC', "AND p.published_year IS NULL AND p.authors_json='[]'", 0),
}
expected = {}
source = repo.parent / 'RSTV4/data/catalog.db'
with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as conn:
    for name,(order,condition,offset) in definitions.items():
        base = "FROM papers p WHERE NOT EXISTS (SELECT 1 FROM catalog_quarantine q WHERE q.paper_id=p.paper_id) " + condition
        expected[name] = {'ids':[r[0] for r in conn.execute('SELECT p.paper_id '+base+' ORDER BY '+order+' LIMIT 50 OFFSET ?',(offset,))],
                          'page':offset//50+1,'total':conn.execute('SELECT COUNT(*) '+base).fetchone()[0]}
with (out / 'independent-expectations.json').open('x',encoding='utf-8') as stream:
    json.dump(expected,stream,indent=2)
print('PASS_INDEPENDENT_EXISTING_DATA_EXPECTATIONS_NO_APP_QUERY_OR_WRITES')
