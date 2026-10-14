from pathlib import Path
import hashlib
import json

repo = Path.cwd()
out = repo / ".tmp/scholar-g09-readable-diff-v1"
out.mkdir()
paths = ["RSTV4/src/rstv4/studio.py", "RSTV4/tests/test_studio_source_context.py",
         "writing-studio/components/studio-response-review.tsx",
         "writing-studio/components/studio-workspace.tsx", "writing-studio/lib/studio-types.ts"]
hashes = {}
for name in paths:
    raw = (repo.parent / name).read_bytes()
    p = out / "before" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(raw)
    hashes[name] = hashlib.sha256(raw).hexdigest()
(out / "before-sha256.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
note = '''

2026-10-13 G09 readable reply-diff contract BEFORE repair: current native review dialog
renders raw [@evidence_ID] markers. Keep authoritative raw baseline_to_target_diff, actual
change rows, evidence IDs, PDF locations and all assertion validation unchanged. Add a
separate numeric display diff from EACH verified version's own references, plus separate
baseline/target citation source labels (exact original source page/unit/version). Identical
numeric printed text can still have changed citation identity: explicitly retain raw diff
and show both fixed source lists, never report no changes merely because display diff is
empty. Evidence display text may be numbered separately but must not change raw evidence
digest or accepted assertion identities. Missing citation titles use local candidate ordinals
instead of internal IDs, without guessing bibliographic identity or editing author records.
Preserve old reports and failed raw display proofs. Full reply/current-generation workflow
and original118/all11 scope still required; formatting is not completion evidence.
'''
for name in ["repomemory/findings.md", "rules/testing-contracts.md"]:
    p = repo / name
    (out / (p.name + ".prior.raw")).write_bytes(p.read_bytes())
    with p.open("a", encoding="utf-8", newline="") as f:
        f.write(note)
print("PASS_READABLE_DIFF_BASELINE_AND_CONTRACT_PRESERVED")
