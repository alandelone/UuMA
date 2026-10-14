from pathlib import Path
import json
root=Path.cwd()
diagnostic=json.loads((root/'.tmp/scholar-generated-assets-short-path-diagnostic-v1.json').read_text(encoding='utf-8'))
assert diagnostic['short_compile_exit']==0 and diagnostic['all_input_bytes_same'] and diagnostic['original_files_unchanged']
entry='''

2026-10-09 actual material focused-v1 generation fails because XeTeX image IO cannot find
280-character original fixture path. Independent short-path probe kept every staged input byte
and original artifact untouched, same XeTeX args/no-shell-escape,120-character paths compile0.
This proves runtime path context, not invalid images or missing dependency. BEFORE compiler
repair: when Windows complete input paths exceed240characters, compile in a newly owned short
temporary directory with exact same input files; preserve compiler log/PDF and all five fixed
output registrations at original immutable job location. No Windows security/path-policy
change, fixture/assertion reduction, deletion/reset of user work, or substitution of content.
Same original long-path test must pass, then full affected and complete suites and native QA.
'''
for name in ['repomemory/findings.md','rules/testing-contracts.md','stage-gates/03-execution-brief.md',
             'docs/reviews/scholar-rstv4-2026-09-30/generated-materials-contract-2026-10-09.md']:
    with (root/name).open('a',encoding='utf-8') as handle: handle.write(entry)
print('PASS actual byte-identical Windows short-path context recorded before compiler repair')
