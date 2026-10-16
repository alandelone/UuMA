from pathlib import Path
repo = Path(__file__).resolve().parents[1]
context = '''

2026-10-16 frozen Thought/Intent and citation attribution first focused run:
44 backend checks passed; two genuine new classification failures showed a space
left before punctuation when removing citation markers. Strip only horizontal space
attached to that marker, preserving prose word boundaries and punctuation. Keep
negative different-prose tests. The real-PDF added fixture stopped before round
creation because create_review_round requires venue; supply the declared software
venue. The controlled JSX text helper ignored numeric children, hiding actual v/r
digits from its assertion; render numbers as text and retain exact v2/r2 assertion.
Keep all failed logs. No successful native/model/job/check or package is replayed.
Legacy stored contexts are never backfilled from the current author editor.
'''
for name in ['rules/testing-contracts.md', 'repomemory/findings.md']:
    with (repo/name).open('a', encoding='utf8') as handle:
        handle.write(context)
source = (repo/'.tmp/scholar-frozen-origin-focused-v1.py').read_text(encoding='utf8')
source = source.replace("f'focused-{i}.log'", "f'focused-v2-{i}.log'").replace("'focused-receipt.json'", "'focused-v2-receipt.json'")
(repo/'.tmp/scholar-frozen-origin-focused-v2.py').write_text(source,encoding='utf8')
build = (repo/'.tmp/scholar-template-build-v3.py').read_text(encoding='utf8')
build = build.replace('scholar-template-build-v3','scholar-frozen-origin-build-v1').replace('scui-template-build-','scui-frozen-origin-build-')
build = build.replace('--max-old-space-size=1536','--max-old-space-size=512').replace("RAYON_NUM_THREADS='2', UV_THREADPOOL_SIZE='2'","RAYON_NUM_THREADS='1', UV_THREADPOOL_SIZE='1'")
(repo/'.tmp/scholar-frozen-origin-build-v1.py').write_text(build, encoding='utf8')
full = (repo/'.tmp/scholar-layout-full-v1.py').read_text(encoding='utf8')
full = full.replace('scholar-layout-full-v1','scholar-frozen-origin-full-v1').replace('scui-layout-full-','scui-frozen-origin-full-')
full = full.replace("'tests/test_studio_layout_integration.py'", "'tests/test_studio_layout_integration.py','tests/test_studio_frozen_origins.py'")
(repo/'.tmp/scholar-frozen-origin-full-v1.py').write_text(full,encoding='utf8')
