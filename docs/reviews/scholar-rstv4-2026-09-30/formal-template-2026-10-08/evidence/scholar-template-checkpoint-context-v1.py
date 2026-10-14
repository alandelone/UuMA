from pathlib import Path

repo = Path(__file__).resolve().parents[1]
note = '''

## 2026-10-08 Template native request observation

Checkpoint v1 retained its failure: the first offline attempt contains a CORS OPTIONS
preflight and one POST, so counting every URL match as one mutation is incorrect. Count
the exact POST separately, retain and report OPTIONS, and match loadingFailed by requestId.
Do not weaken exact request identity/base revision/zero model and database checks. Hook
changes during HMR reset the client to its original r1 props; the preserved r1 request was
recovered then correctly rejected against server r7. Refresh after code changes before the
successor r7 offline test, preserve the failed request, and never relabel the r1 test as success.
'''
for name in ['repomemory/findings.md', 'rules/scholar-native-acceptance.md']:
    with (repo / name).open('a', encoding='utf-8') as handle:
        handle.write(note)
source = (repo / '.tmp/scholar-template-native-checkpoint-v1.py').read_text(encoding='utf-8')
source = source.replace('scholar-template-native-checkpoint-v1.json', 'scholar-template-native-checkpoint-v2.json')
source = source.replace("and event['params']['request']['url'].endswith('/template-adoption')]",
    "and event['params']['request']['url'].endswith('/template-adoption')\n            and event['params']['request']['method'] == 'POST']")
source = source.replace("'error': failed[0]['params']['errorText']}",
    "'error': failed[0]['params']['errorText'], 'preflight_count': sum(e['method'] == 'Network.requestWillBeSent' and e['params']['request']['method'] == 'OPTIONS' for e in network['events'])}")
with (repo / '.tmp/scholar-template-native-checkpoint-v2.py').open('x', encoding='utf-8') as handle:
    handle.write(source)
