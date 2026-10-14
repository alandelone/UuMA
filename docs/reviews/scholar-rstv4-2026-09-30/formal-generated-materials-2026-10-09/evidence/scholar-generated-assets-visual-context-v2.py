from pathlib import Path
import hashlib
import json
import shutil
r=Path.cwd()
out=r/'.tmp/scholar-generated-assets-visual-before-v2'
out.mkdir()
files=['src/rstv4/studio_materials.py','tests/test_studio_generated_assets.py']
for file in files:
    target=out/Path(file).name
    shutil.copy2(r.parent/'RSTV4'/file,target)
note='''

2026-10-09 native downloaded PDF visual QA-v2: inspected all3real pages, SHA
c5c4aa8679b430aa3bab7b61e71da71704e1aefacf679502e9b36f15af04b060.
All30original table rows/secondSheet/3images are present, but compact table title lacks
trailing paragraph break: title shares the table baseline, pushing table to the right;
third-page Markdown extends beyond physical page edge. Fixed .9linewidth widths also
omit cell padding/rule budget. Preserve this immutable v1/native25file ZIP and all3renders.
BEFORE repair require original title above table, columns budget actual linewidth minus
padding/rules, original complete ordered cells unchanged. Add independent Poppler word
geometry to real-PDF integration test (all words within page margins and each table title
above first row). Do not bless visible clipping from a text-only PASS, rewrite old version,
truncate/reorder cells or weaken prior source/byte/schema/permission guards. Run narrow,
full regression and native new immutable generation/download/independent compile/visual QA.
'''
for file in ['repomemory/findings.md','rules/testing-contracts.md','stage-gates/03-execution-brief.md','docs/reviews/scholar-rstv4-2026-09-30/generated-materials-contract-2026-10-09.md']:
    with (r/file).open('a',encoding='utf-8') as handle:handle.write(note)
(out/'context.json').write_text(json.dumps({'pdf_sha256':'c5c4aa8679b430aa3bab7b61e71da71704e1aefacf679502e9b36f15af04b060','visual_result':'FAIL_TABLE_RIGHT_EDGE','sources':{file:hashlib.sha256((r.parent/'RSTV4'/file).read_bytes()).hexdigest() for file in files},'all11_complete':False},indent=2),encoding='utf-8')
print('Preserved actual failed native PDF/ZIP/3renders and current sources; recorded contract before repair.')
