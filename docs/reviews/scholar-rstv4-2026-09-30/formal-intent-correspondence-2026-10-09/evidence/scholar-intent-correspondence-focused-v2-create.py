from pathlib import Path

root = Path.cwd()
source = (root/'.tmp/scholar-intent-correspondence-focused-v1.py').read_text(encoding='utf-8')
successor = source.replace('focused-v1', 'focused-v2')
with (root/'.tmp/scholar-intent-correspondence-focused-v2.py').open('x', encoding='utf-8') as stream:
    stream.write(successor)
entry = '''

2026-10-09 Intent mapping focused-v1 retained:91 passed/1 failed; TSC and3 unit suites
passed, two checkbox label-association diagnostics. Actual flat template empty_sections
stores fixed source on Paragraph, while explicit outline templates also stamp Intent.
Read exact fixed source from Intent or its own Paragraph; never invent a source or rewrite
historical JSON. Existing source/identity rejection assertions remain. New references must
match actual ADOPT_TEMPLATE operation/instance history in the same manuscript, not merely
a client-supplied source label. Checkbox id/htmlFor corrected without suppressing checks.
'''
for relative in ['repomemory/findings.md', 'rules/scholar-native-acceptance.md']:
    path = root/relative
    previous = path.read_text(encoding='utf-8')
    path.write_text(previous + entry, encoding='utf-8')
    assert previous in path.read_text(encoding='utf-8')
skill = Path('C:/Users/Alandelone/.codex/plugins/cache/openai-bundled/computer-use/26.930.41038')
for name in ['guidance.md', 'confirmations.md']:
    print('COMPUTER_GUIDANCE', name)
    print((skill/'docs'/name).read_text(encoding='utf-8'))
