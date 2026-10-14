from pathlib import Path
repo=Path(__file__).resolve().parents[1]
context=repo/'.tmp/scholar-g11-parallel-v1/gpu-health-retry-context-v1'
import json
mission=json.loads((repo/'mission_status.json').read_text())
assert mission['stage']=='verification' and mission['gate']['status']=='pending_review'
note='''

2026-10-14 GPU attempt6 succeeded once; do not rerun it. Independent audit v1/v2
stopped on auditor contract mistakes, not parser failure. Current acquisition
publication intentionally stores parsed_path=manifest.structured_path (optional,
here null), and parsed_digest is canonical digest(manifest,blocks,references), not
a file SHA. The bridge's intermediate rstv4-parse-result is pre-normalization:
normalize_mineru_result re-reads authoritative content_list, splits DOI/body and
reference sections, and converts page_idx to physical one-based pages. The audit
must independently re-normalize those retained actual artifacts, preserve the
explicit correction action list, and verify canonical digest, normalized body
texts, all six references and every protected row. Never weaken assertions or
substitute raw pre-normalization blocks, replay GPU/model work or alter data.
Current gate remains verification/pending_review; v3 restarts this read-only audit
using the corrected execution/storage contract. All failed audit helpers retained.
'''
for name in ['rules/testing-contracts.md','repomemory/findings.md']:
    p=repo/name;(context/(p.name+'.prior-audit-context-v3.raw')).open('xb').write(p.read_bytes())
    with p.open('a',encoding='utf-8',newline='') as f:f.write(note)
code=Path(__file__).with_name('scholar-g11-gpu-success-audit-v2.py').read_text(encoding='utf-8')
# v2 builds v1's auditor in process. Inject corrected authoritative normalization.
needle="assert len(parsed['blocks'])==3\nassert [r['text'] for r in sorted(blocks,key=lambda r:r['sequence'])]==[r['text'] for r in parsed['blocks']]"
replacement="""sys.path.insert(0,str(repo.parent/'RSTV4/src'))
from rstv4.parser_quality import normalize_mineru_result
from rstv4.acquisition import digest as publication_digest
parsed['manifest']['requested_output_dir']=manifest['requested_output_dir']
parsed['manifest']['source_pdf_path']=str(source)
normalized=normalize_mineru_result(parsed,source_pdf_path=source)
normalized['manifest']['review_correction_action_ids']=manifest['review_correction_action_ids']
assert normalized['manifest']=={k:v for k,v in manifest.items() if k!='publication'}
assert publication_digest({'manifest':normalized['manifest'],'blocks':normalized['blocks'],'references':normalized['references']})==version['parsed_digest']
assert len(normalized['blocks'])==3 and len(normalized['references'])==6
assert [r['text'] for r in sorted(blocks,key=lambda r:r['sequence'])]==[r['text'] for r in normalized['blocks']]
parsed=normalized"""
assert code.count(needle)==1
code=code.replace(needle,replacement)
code=code.replace('actual-gpu-success-final-audit-v2.json','actual-gpu-success-final-audit-v3.json')
exec(compile(code,__file__,'exec'))
