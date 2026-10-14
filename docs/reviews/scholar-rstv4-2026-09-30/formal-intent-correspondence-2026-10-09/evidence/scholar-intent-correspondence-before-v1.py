from pathlib import Path
import hashlib
import json
import shutil
import sqlite3
import subprocess

root = Path.cwd()
out = root / '.tmp/scholar-intent-correspondence-before-v1'
out.mkdir(exist_ok=False)
parent = root / 'docs/reviews/scholar-rstv4-2026-09-30/formal-source-hierarchy-2026-10-09'
manifest = json.loads((parent / 'manifest.json').read_text(encoding='utf-8'))
for relative, digest in manifest['copied_file_sha256'].items():
    assert hashlib.sha256((parent / relative).read_bytes()).hexdigest() == digest, relative
for relative, digest in manifest['final_source_sha256'].items():
    assert hashlib.sha256((root.parent / relative).read_bytes()).hexdigest() == digest, relative
source_names = [
    'RSTV4/src/rstv4/studio.py', 'RSTV4/src/rstv4/studio_context.py',
    'RSTV4/src/rstv4/studio_structure.py', 'RSTV4/src/rstv4/studio_templates.py',
    'writing-studio/components/studio-workspace.tsx',
    'writing-studio/components/studio-original-placement.tsx',
    'writing-studio/components/studio-block-controls.tsx',
    'writing-studio/lib/studio-types.ts', 'writing-studio/lib/studio-blocks.ts',
]
hashes = {}
for relative in source_names:
    source = root.parent / relative
    target = out / 'source' / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    hashes[relative] = hashlib.sha256(source.read_bytes()).hexdigest()
statuses = {}
for name in ['UuMA', 'RSTV4', 'writing-studio']:
    result = subprocess.run(['git', 'status', '--short'], cwd=root.parent/name,
                            capture_output=True, text=True, encoding='utf-8', check=True)
    (out / f'{name}-status.txt').write_text(result.stdout, encoding='utf-8')
    statuses[name] = len(result.stdout.splitlines())
native = Path('C:/Users/Alandelone/AppData/Local/Temp/scui-source-hierarchy-native-vrh2ab3g/data/catalog.db')
conn = sqlite3.connect(native.as_uri() + '?mode=ro', uri=True)
with sqlite3.connect(out / 'native-before.db') as backup:
    conn.backup(backup)
row = conn.execute('SELECT revision,document_json FROM studio_documents WHERE manuscript_id=?',
                   ('manuscript_98c35f5b5557453583cb20df8d52810d',)).fetchone()
assert row[0] == 8
conn.close()
findings = (root / 'repomemory/findings.md').read_text(encoding='utf-8')
handoff = (root / 'active-session/HANDOFF.md').read_text(encoding='utf-8')
gate = (root / 'stage-gates/04-verification-report.md').read_text(encoding='utf-8')
result = {'status': 'PASS_BEFORE_EDIT', 'parent_files': len(manifest['copied_file_sha256']),
          'source_sha256': hashes, 'git_status_lines': statuses, 'native_revision': row[0],
          'native_document': json.loads(row[1]), 'findings_chars': len(findings),
          'handoff_chars': len(handoff), 'gate_chars': len(gate)}
(out / 'baseline.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k != 'native_document'}, ensure_ascii=False))
