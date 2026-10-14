from pathlib import Path
import json
r=Path.cwd()
note='''

2026-10-09 native materials independent audit-v1 stops before PDF/ZIP audit because verifier
assumed Studio call status DONE. Exact owned call studio_model_call_5cae693a7b614e4c80c61637f4cafe01
is VALIDATED, paragraph_realization, no error, actual completed timestamp and declared
TEST_FIXTURE_MATERIALS_NATIVE. DONE is an unrelated scientific acquisition worker status;
do not merge status axes. Before verifier correction require exactly VALIDATED plus actual
contract/task/input/output/mapping provenance, one fixture call and zero remote models.
Retain audit-v1 source/failure and all109table/byte/author/ZIP/fullcells guards. No product
change, schema or scientific approval; real native GENERATE/PACKAGE both SUCCEEDED.
'''
for path in ['repomemory/findings.md','rules/testing-contracts.md','stage-gates/03-execution-brief.md','docs/reviews/scholar-rstv4-2026-09-30/generated-materials-contract-2026-10-09.md']:
    with (r/path).open('a',encoding='utf-8') as handle:handle.write(note)
source=(r/'.tmp/scholar-generated-assets-native-audit-v1.py').read_text(encoding='utf-8')
source=source.replace("out=r/'.tmp/scholar-generated-assets-native-audit-v1'","out=r/'.tmp/scholar-generated-assets-native-audit-v2'")
source=source.replace("assert len(calls)==1 and calls[0]['status']=='DONE'","assert len(calls)==1 and calls[0]['status']=='VALIDATED'\nassert calls[0]['error_json'] is None and calls[0]['completed_at'] and calls[0]['task']=='paragraph_realization'\nassert calls[0]['job_id']==gen_job['job_id'] and calls[0]['input_revision']==1\nassert json.loads(calls[0]['output_json'])['paragraph']==paragraph['text']\nassert json.loads(calls[0]['output_json'])['sentence_mappings']==paragraph['sentence_mappings']")
with (r/'.tmp/scholar-generated-assets-native-audit-v2.py').open('x',encoding='utf-8') as handle:handle.write(source)
print('Recorded exact VALIDATED context before verifier correction; all original guards retained.')
