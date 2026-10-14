import hashlib
import json
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
findings = (repo / 'repomemory/findings.md').read_text(encoding='utf-8')
brief = (repo / 'stage-gates/03-execution-brief.md').read_text(encoding='utf-8')
mission = json.loads((repo / 'mission_status.json').read_text(encoding='utf-8'))
gate = (repo / mission['gate']['current']).read_text(encoding='utf-8')
assert mission['stage'] == 'verification' and mission['gate']['status'] == 'pending_review'
contract = '\n\n### 2026-10-09 source hierarchy additive catalog contract\n\nWithin the user-authorized original G-08 source hierarchy requirement, Catalog schema 13 adds only `skeleton_source_outlines` (one immutable outline per new PaperSkeleton, bound to completed parse/file/source block identities and explicit parser levels). Existing 108 tables keep their rows; only the catalog schema version marker changes to 13. Backup before migration, verify every existing row and foreign key, and keep every legacy source context/digest byte-identical; do not annotate historical skeletons in place. No Hermes/UuMA/Wisdom schema changes, no new science approval or true model calls. Reinitializing a schema-13 fixture must preserve database bytes, and the recorded schema marker must equal the declared current `CATALOG_VERSION`. Keep old-version fixture migration tests and rejection/reversal tests. Numeric version 12 is an outdated assertion after this additive migration; preserving all existing history and stable reinitialization remains mandatory. This documents the current implementation contract and does not approve any gate transition or mark G-08/11-group acceptance complete.\n'
with (repo / 'stage-gates/03-execution-brief.md').open('a', encoding='utf-8') as f:
    f.write(contract)
with (repo / 'repomemory/findings.md').open('a', encoding='utf-8') as f:
    f.write('\n\n### 2026-10-09 source hierarchy full regression failure\n\nRetained full-v1 log SHA256 0c4dfd2fb4db28365f4d4c9d49044c6150a54092444f8fae9c64df09a96b825b: 1 failed, 1014 passed, 20 warnings, 435.93 seconds; all 22 prerequisite checks passed and sources unchanged. Incorrect obsolete numeric contract: FieldKG stable-reinitialization test expects schema 12 while additive outline migration declares 13. Read all findings/current gate/execution brief; correct execution brief before adapting only that numeric check to the declared CATALOG_VERSION. Byte equality, history preservation and no-new-approval/call requirements remain intact. No reset or gate transition.\n')
test = repo.parent / 'RSTV4/tests/test_fieldkg_semantics.py'
target = repo / '.tmp/scholar-source-hierarchy-before-v1/RSTV4/tests/test_fieldkg_semantics.py'
target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(test.read_bytes())
source = test.read_text(encoding='utf-8')
assert source.count("fetchone()[0]==12") == 1
source = source.replace('from rstv4.durable_model_delivery import', 'from rstv4.database import CATALOG_VERSION\nfrom rstv4.durable_model_delivery import', 1)
test.write_text(source.replace('fetchone()[0]==12', 'fetchone()[0]==CATALOG_VERSION'), encoding='utf-8')
print(json.dumps({'status': 'PASS_CONTRACT_CORRECTED_BEFORE_TEST', 'findings_characters': len(findings),
                  'brief_characters': len(brief), 'gate_characters': len(gate),
                  'preserved_test_sha256': hashlib.sha256(target.read_bytes()).hexdigest()}))
