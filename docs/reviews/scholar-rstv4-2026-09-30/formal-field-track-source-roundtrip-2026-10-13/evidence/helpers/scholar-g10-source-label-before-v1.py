from pathlib import Path
import hashlib
import json

repo=Path.cwd()
out=repo / ".tmp/scholar-g10-native-v1/source-label-before-v1"
out.mkdir()
p=repo.parent / "writing-studio/components/studio-source-context.tsx"
(out / "studio-source-context.tsx").write_bytes(p.read_bytes())
(out / "receipt.json").write_text(json.dumps({"status":"PRESERVED_NATIVE_PARSE_LABEL_DEFECT","source_sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"defect":"No parse_run_id but unconditional parsed-version-fixed label","required":"Known parse stays fixed; absent parse explicit unrecorded and unit text distinct","overall11_complete":False},indent=2),encoding="utf-8")
note='''

2026-10-13 G10 native explicit-unknown source label BEFORE repair: old semantic source
records have null parse_run_id/file_version_id/PDF digest. Backend correctly returns
precise Paper/Skeleton/unit plus no PDF; StudioSourceContext unconditionally displayed
解析版本已固定. Keep native original proof and source raw backup; render解析版本未记录
when exact parse identity absent. Full-text summary must distinguish known parse from
preserved original units. Do not invent versions/PDF, rewrite source records, infer
scientific approval or reduce completeness requirements. Known G09 parsed-source labels
remain the same. Native unknown/known checks and all frontend unit/type/lint/build required.
'''
for name in ["repomemory/findings.md","rules/testing-contracts.md"]:
    q=repo / name
    (out / (q.name+".prior.raw")).write_bytes(q.read_bytes())
    with q.open("a",encoding="utf-8",newline="") as f:f.write(note)
print("SOURCE_LABEL_NATIVE_DEFECT_PRESERVED")
