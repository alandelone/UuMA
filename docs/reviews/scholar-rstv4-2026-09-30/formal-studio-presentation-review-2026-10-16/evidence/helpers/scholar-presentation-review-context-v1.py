from pathlib import Path
repo=Path(__file__).resolve().parents[1]
context='''

2026-10-16 presentation reply contract: actual17 compiler/HTTP/negative cases,
component and TypeScript all passed. Ruff rejects same-name fixture import aliases
(PLC0414), even though they declare exports to the unused-import checker. Re-export
the two shared pytest fixtures in __all__, preserving all behavior assertions and
both failed lint logs. Do not regenerate the preserved v6/v7 or replay successful
native/GPU/QuickRead/package actions. New outcome PRESENTATION_MODIFIED requires
exact identical frozen prose plus verified layout-only evidence from both PDFs;
scientific MODIFIED retains its original changed-prose guard.
'''
for name in ['rules/testing-contracts.md','repomemory/findings.md']:
    with (repo/name).open('a',encoding='utf8') as handle:handle.write(context)
full=(repo/'.tmp/scholar-frozen-origin-full-v1.py').read_text(encoding='utf8')
full=full.replace('scholar-frozen-origin-full-v1','scholar-presentation-review-full-v1').replace('scui-frozen-origin-full-','scui-presentation-review-full-')
full=full.replace("'tests/test_studio_frozen_origins.py'","'tests/test_studio_frozen_origins.py','tests/test_studio_presentation_review.py','src/rstv4/studio_response_checks.py','src/rstv4/studio_api.py'")
(repo/'.tmp/scholar-presentation-review-full-v1.py').write_text(full,encoding='utf8')
build=(repo/'.tmp/scholar-frozen-origin-build-v1.py').read_text(encoding='utf8').replace('scholar-frozen-origin-build-v1','scholar-presentation-review-build-v1').replace('scui-frozen-origin-build-','scui-presentation-review-build-')
(repo/'.tmp/scholar-presentation-review-build-v1.py').write_text(build,encoding='utf8')
