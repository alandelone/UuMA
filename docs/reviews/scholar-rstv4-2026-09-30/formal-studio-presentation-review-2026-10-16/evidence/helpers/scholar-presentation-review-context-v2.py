from pathlib import Path
repo=Path(__file__).resolve().parents[1]
context='''

2026-10-16 presentation audit execution context: stored historical request_json
includes manuscript_id and comment_id in addition to the exact HTTP body, as the
unchanged record() canonical request wrapper declares. Require both exact owners
and every original request field, not a body-only dictionary comparison. Runtime
terminal audit already proved the complete wrapper exact. Preserve the first
readonly auditor failure and do not replay successful A215 confirmation.
Run Ruff with cwd RSTV4 so its own configuration classifies test fixtures correctly;
running it from UuMA selects different first-party grouping rules. Retain both
failed lint observations; explicit __all__ exposes shared pytest fixtures without
same-name aliases or broad lint suppression.
'''
for name in ['rules/testing-contracts.md','repomemory/findings.md']:
    with (repo/name).open('a',encoding='utf8') as f:f.write(context)
source=(repo/'.tmp/scholar-presentation-review-audit-v1.py').read_text(encoding='utf8')
source=source.replace("check['request']==body", "check['request']=={'manuscript_id':ctx['state']['manuscript_id'],'comment_id':result['comment']['comment_id'],**body}")
(repo/'.tmp/scholar-presentation-review-audit-v2.py').write_text(source,encoding='utf8')
