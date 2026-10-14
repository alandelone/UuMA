import json
import sqlite3
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
info = json.loads((repo / '.tmp/scholar-template-native-fixture-v1.json').read_text(encoding='utf-8'))
with sqlite3.connect(f"{(Path(info['root']) / 'data/catalog.db').as_uri()}?mode=ro", uri=True) as conn:
    conn.row_factory = sqlite3.Row
    document = dict(conn.execute('SELECT * FROM studio_documents WHERE manuscript_id=?', (info['native_manuscript_id'],)).fetchone())
    operations = [dict(row) for row in conn.execute('SELECT operation_id,base_revision,resulting_revision,operation_kind FROM studio_operations WHERE manuscript_id=? ORDER BY resulting_revision', (info['native_manuscript_id'],))]
    print(json.dumps({'revision': document['revision'], 'original_document': json.loads(document['document_json']) == info['initial_document'], 'operations': operations[-9:]}, ensure_ascii=False))
