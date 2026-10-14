from pathlib import Path

repo = Path.cwd()
old_helper = repo / ".tmp/scholar-g09-generation-input-audit-v1.py"
context = repo / ".tmp/scholar-g09-current-generation-native-v1/input-audited/context-v1"
context.mkdir()
(context / "original-auditor.py").write_bytes(old_helper.read_bytes())
note = '''

2026-10-13 current-generation input auditor v1 failed on manuscripts before model/readiness
execution. Exact RO diagnostic proves ONLY original A updated_at advanced during native
author saves; manuscript revision5, stageWHOLE_PAPER_REVIEW, writingINTERNAL_REVIEW, original
track/title/scope/science/blocker fields and all other manuscripts exact. Authorrevision is
separate axis. V2 permits only that timestamp for actualA; retain every other manuscript
field exact, all other109 table guards and source/author/old artifact invariants. Preserve
v1 helper/exclusive directory. No native action replay or product guard change.
'''
for name in ["repomemory/findings.md", "rules/testing-contracts.md"]:
    p = repo / name
    (context / (p.name + ".prior.raw")).write_bytes(p.read_bytes())
    with p.open("a",encoding="utf-8",newline="") as file:
        file.write(note)
code = old_helper.read_text(encoding="utf-8").replace('root / "input-audited"', 'root / "input-audited-v2"')
code = code.replace('allowed = {"studio_documents",', 'allowed = {"manuscripts", "studio_documents",')
needle = 'ms = info["manuscript_id"]'
code = code.replace(needle, needle + '\nfor prior,current in zip(old["manuscripts"],before["manuscripts"]):\n    expected = dict(prior)\n    if prior["manuscript_id"] == ms:\n        expected["updated_at"] = current["updated_at"]\n    assert current == expected\nassert len(old["manuscripts"]) == len(before["manuscripts"])')
exec(compile(code,__file__,"exec"))
