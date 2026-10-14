import os
import shutil
import subprocess
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
os.environ.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
with (repo / 'repomemory/findings.md').open('a', encoding='utf-8') as handle:
    handle.write('\n\n## 2026-10-05 Scholar actual shared adapter VM execution context\n\n'
                 'Missing context/dependency after two read-only acceptance helper failures. '
                 'v1 guessed canonical API prefix by dropping /api, producing actual HTTP404 Not Found; '
                 'the shipped sharedDiscussionRequest maps /api/catalog/discussion to /research/discussion. '
                 'v2 loaded the actual adapter but omitted Headers (and required FormData) in its isolatedVM, '
                 'so choose failed with Headers is not defined before context HTTP. '
                 'Both helpers/logs retained; no new message/annotation/model request or data edit. '
                 'Read full findings/testing contract; durable context in rules/scholar-ui-verification.md. '
                 'Supply real Node Headers/FormData/fetch and exact isolated API base; keep original '
                 'context, owner, version, quote and zero-write assertions. Canonical parser adds default '
                 'target fields: compare complete frozen source before/after viewHistory, not a sparse '
                 'request target to its normalized result. This strengthens unchanged-source proof and '
                 'does not alter product/test behavior contracts. Backend155 and finalfrontend39/6/17 '
                 'already passed, product source unchanged during VM dependency repair.\n')
source = (repo / '.tmp/scholar-studio-history-native-view-v2.mjs').read_text(encoding='utf-8')
assert source.count('const sdk={exports:{},process:') == 1
source = source.replace('const sdk={exports:{},process:', 'const sdk={exports:{},Headers,FormData,process:')
source = source.replace('scholar-studio-history-native-view-v2.json', 'scholar-studio-history-native-view-v3.json')
target = repo / '.tmp/scholar-studio-history-native-view-v3.mjs'
with target.open('x', encoding='utf-8') as handle:
    handle.write(source)
output = repo / '.tmp/scholar-studio-history-native-final-v2.log'
with output.open('x', encoding='utf-8') as log:
    for command in [[shutil.which('node'), str(target)],
                    [str(repo.parent / 'RSTV4/.venv/Scripts/python.exe'), '-X', 'utf8', str(repo / '.tmp/scholar-studio-history-final-v1.py')]]:
        log.write(f'CHECK {Path(command[-1]).name}\n'); log.flush()
        result = subprocess.run(command, cwd=repo, stdout=log, stderr=subprocess.STDOUT)
        log.write(f'Exit: {result.returncode}\n'); log.flush()
        if result.returncode:
            print(output.read_text(encoding='utf-8')[-7500:]); raise SystemExit(result.returncode)
print(output.read_text(encoding='utf-8')[-7500:])
