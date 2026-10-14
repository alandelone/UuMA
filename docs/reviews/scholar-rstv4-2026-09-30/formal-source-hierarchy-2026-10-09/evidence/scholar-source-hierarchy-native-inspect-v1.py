import json
import sqlite3
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
info = json.loads((repo / '.tmp/scholar-source-hierarchy-fixture-v1.json').read_text(encoding='utf-8'))
with sqlite3.connect(f"file:{Path(info['database']).as_posix()}?mode=ro", uri=True) as conn:
    conn.row_factory = sqlite3.Row
    operations = [dict(r) for r in conn.execute('SELECT * FROM studio_operations WHERE manuscript_id=? ORDER BY resulting_revision', (info['manuscript_id'],))]
    templates = [dict(r) for r in conn.execute('SELECT * FROM studio_template_instances WHERE manuscript_id=? ORDER BY rowid', (info['manuscript_id'],))]
    documents = [dict(r) for r in conn.execute('SELECT * FROM studio_documents WHERE manuscript_id=?', (info['manuscript_id'],))]
record = {'operations': operations, 'templates': templates, 'documents': documents}
(repo / '.tmp/scholar-source-hierarchy-native-inspect-v1.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'operations': [{k: row[k] for k in ['operation_id', 'operation_kind', 'base_revision', 'resulting_revision'] if k in row} for row in operations],
                  'templates': [{k: row[k] for k in ['operation_id', 'mode', 'scope_type', 'scope_id', 'resulting_revision'] if k in row} for row in templates],
                  'document_columns': list(documents[0]) if documents else []}, ensure_ascii=False))
