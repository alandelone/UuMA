from pathlib import Path
repo=Path.cwd()
old=repo / ".tmp/scholar-g09-generated-v5-audit-v1.py"
context=repo / ".tmp/scholar-g09-current-generation-native-v1/generated-v5-audited/context-v1"
context.mkdir()
(context / "original-auditor.py").write_bytes(old.read_bytes())
note='''

2026-10-13 v5 generation auditor v1 reached manuscript identity check after exact11calls,
newversion/5artifacts/fullbyte checks. Fresh RO diagnostic: actual successful generation
publication advances A manuscript revision5->6 and updated_at; WHOLE_PAPER_REVIEW,
INTERNAL_REVIEW and all otherfields/othermanuscript exact. V2 requires exactly+1 for
the single independently SUCCEEDED generation, distinct authorrevision remains62.
Do not hold the manuscript CAS axis fixed through actual publication or merge axes;
retain all originalcalls/history/version/artifact/baseline guards. Preserve failedhelper.
'''
for name in ['repomemory/findings.md','rules/testing-contracts.md']:
    p=repo / name
    (context / (p.name+'.prior.raw')).write_bytes(p.read_bytes())
    with p.open('a',encoding='utf-8',newline='') as f:f.write(note)
code=old.read_text(encoding='utf-8').replace('root / "generated-v5-audited"','root / "generated-v5-audited-v2"')
code=code.replace('expected["updated_at"]=current["updated_at"]','expected["updated_at"]=current["updated_at"]\n        expected["revision"]=old["revision"]+1')
exec(compile(code,__file__,'exec'))
