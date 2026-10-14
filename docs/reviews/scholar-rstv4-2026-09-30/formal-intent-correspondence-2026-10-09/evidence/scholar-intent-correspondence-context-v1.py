from pathlib import Path

root = Path.cwd()
findings_path = root / 'repomemory/findings.md'
findings = findings_path.read_text(encoding='utf-8')
entry = '''

2026-10-09 Intent correspondence discovery: attempted source names studio_document.py,
studio_sources.py and studio_chat.py do not exist. Preserve these read failures; rg --files
and actual Studio imports identify studio_context.py, studio_read_views.py and
studio_discussions.py. Read current inventory/imports before naming an unverified module.
Full findings were read before this context fix. Original Intent/group/context identity
cannot be satisfied by Thought-only relocation or whole-tree placement. The explicit
reference contract is in docs/reviews/scholar-rstv4-2026-09-30/intent-correspondence-contract-2026-10-09.md.
Source baseline/native r8 SQLite backup/206 parent sealed rehash retained in
.tmp/scholar-intent-correspondence-before-v1. No scientific approval or gate change.
'''
findings_path.write_text(findings + entry, encoding='utf-8')
rules_path = root / 'rules/scholar-native-acceptance.md'
rules = rules_path.read_text(encoding='utf-8')
rules_path.write_text(rules + entry, encoding='utf-8')
brief_path = root / 'stage-gates/03-execution-brief.md'
brief = brief_path.read_text(encoding='utf-8')
brief_path.write_text(brief + '''

2026-10-09 additive author Intent correspondence execution: use optional author_intent_ids
and author_context_paragraph_ids in the existing author JSON, retaining canonical author
structure/IDs/content and fixed template source. Explicit selection/preview/confirmation,
no guessed matching; one original Intent destination and one explicit paragraph-attachment
output position. Backend validation and reversible snapshots remain mandatory. Unmapped
content and unresolved attachment placement must still prevent Generate. No catalog schema,
approval, old generated version or mission gate change. See the complete new contract.
''', encoding='utf-8')
assert findings in findings_path.read_text(encoding='utf-8')
assert rules in rules_path.read_text(encoding='utf-8')
assert brief in brief_path.read_text(encoding='utf-8')
print('PASS: missing-module context recorded; complete previous findings/rules/brief preserved.')
