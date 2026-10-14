import json
import sqlite3
from pathlib import Path
from rstv4.studio import StudioService

result_path = Path(__file__).parent / "scholar-acceptance-results.json"
result = json.loads(result_path.read_text(encoding="utf-8"))
fixture = result["isolated_fixture"]
service = StudioService(fixture["root"])
workspace = service.create_manuscript(fixture["track_id"], "阶段门验收测试 · 独立测试库")
manuscript_id = workspace["manuscript"]["manuscript_id"]
stages = []
for stage in ("DRAFTING", "WHOLE_PAPER_REVIEW", "FINALIZATION_SUBMISSION", "PUBLICATION"):
    workspace = service.set_stage(manuscript_id, stage,
        expected_revision=workspace["manuscript"]["revision"], reason="Isolated acceptance probe only")
    stages.append(workspace["manuscript"]["workflow_stage"])
with sqlite3.connect(service.db_path) as conn:
    version_count = conn.execute("SELECT COUNT(*) FROM manuscript_versions WHERE manuscript_id=?", (manuscript_id,)).fetchone()[0]
probe = {"accepted_stages": stages, "generated_versions": version_count,
    "expected": "WHOLE_PAPER_REVIEW requires a successful immutable generated version"}
result["stage_gate_probe"] = probe
result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(probe, ensure_ascii=False, indent=2))
