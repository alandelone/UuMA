from pathlib import Path
import hashlib
import json
import sqlite3
import sys

repo = Path.cwd()
sys.path.insert(0, str(repo.parent / "RSTV4/src"))
from rstv4.studio_api import create_app
from rstv4.studio_correspondence import realization_document
from rstv4.studio_realization import OUTPUT_SCHEMA, validate
from rstv4.studio_sources import model_source
from rstv4.studio_structure import paragraph_group

root = repo / ".tmp/scholar-g09-current-generation-native-v1"
out = root / "input-audited"
out.mkdir()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
info = read(root / "baseline.json")
db = Path(info["database"])
def tables():
    with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        return {r[0]:[dict(v) for v in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')]
                for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
before = tables()
digest = hashlib.sha256(db.read_bytes()).hexdigest()
old = read(root / "baseline-all-tables.json")
allowed = {"studio_documents", "studio_operations", "studio_changes", "studio_change_link_state", "comment_changes", "studio_sample_candidates", "sqlite_sequence"}
for name, rows in old.items():
    if name not in allowed:
        assert before[name] == rows, name
    elif name in {"studio_operations", "studio_changes", "studio_change_link_state", "comment_changes", "studio_sample_candidates"}:
        assert all(v in before[name] for v in rows), name
ms = info["manuscript_id"]
old_doc = json.loads(next(r for r in old["studio_documents"] if r["manuscript_id"] == ms)["document_json"])
row = next(r for r in before["studio_documents"] if r["manuscript_id"] == ms)
author = json.loads(row["document_json"])
assert all(r in before["studio_documents"] for r in old["studio_documents"] if r["manuscript_id"] != ms)
assert row["active_generated_version_id"] == "manuscript_version_2feb293fad7e4e6591d4217cd322d9d9" and row["last_generated_revision"] == 11
index = lambda d: {t["id"]:t for s in d["sections"] for p in s["paragraphs"] for i in p["intents"] for t in i["thoughts"]}
old_thoughts, thoughts = index(old_doc), index(author)
assert thoughts["thought_author_1"] == old_thoughts["thought_author_1"]
beta = dict(old_thoughts["thought_009a96629cb14586b44697b3ec73f2bc"])
beta["citation_mode"] = "SELECTED"
assert thoughts[beta["id"]] == beta
assert len(thoughts) == 12 and len(old_thoughts) == 2
assert {s["id"] for s in old_doc["sections"]} == {s["id"] for s in author["sections"]}
for prior in old_doc["sections"]:
    current = next(s for s in author["sections"] if s["id"] == prior["id"])
    assert current["title"] == prior["title"]
    assert not current.get("placement_status")
    if prior.get("placement_status") == "UNPLACED":
        assert current["parent_section_id"] == "section_869a4f8d019a4f778b69f7adfe2086db"
    assert {p["id"] for p in prior["paragraphs"]}.issubset({p["id"] for p in current["paragraphs"]})
app = create_app(read(repo / ".tmp/scholar-citation-source-native-v1.json")["root"])
service = app.state.studio
service._check_generate_ready(ms, author)
document = realization_document(author)
selected_ids = list(dict.fromkeys(c["evidence_id"] for s in document["sections"] for p in s["paragraphs"] for i in p["intents"] for t in i["thoughts"] for c in t["citations"] if c["selected"]))
evidence = {e["evidence_id"]:e for e in service._evidence_by_ids(selected_ids)}
contracts = []
for section in document["sections"]:
    for paragraph in section["paragraphs"]:
        ids = list(dict.fromkeys(c["evidence_id"] for i in paragraph["intents"] for t in i["thoughts"] for c in t["citations"] if c["selected"]))
        payload = {"section_title":section["title"], "section_role":section.get("role"),
                   "paragraph_purpose":paragraph.get("purpose"),"paradigm":paragraph.get("paradigm"),
                   "intents":paragraph["intents"],"selected_evidence":[model_source(evidence[e]) for e in ids],
                   "output_schema":OUTPUT_SCHEMA,"constraint":"Preserve every author thought; do not add scientific claims. Use only selected evidence ids in citations."}
        if section.get("parent_section_id"):
            from rstv4.studio_structure import section_titles
            payload["section_path"] = section_titles(document, section["id"])
        group = paragraph_group(section, paragraph["id"])
        if group:
            payload["paragraph_group"] = group
        ordered = [t for i in paragraph["intents"] for t in i["thoughts"]]
        sentences, mappings = [], []
        for thought in ordered:
            if thought["id"] == "thought_author_1":
                chunks = [f"First source [@evidence_6b169de2b78d452f919391b00916f2c8].", f"Next [@evidence_b5348fa59b3948ae9540b75a33ca9bd9].", f"Repeat [@evidence_6b169de2b78d452f919391b00916f2c8]."]
            elif thought["id"] == beta["id"]:
                chunks = ["Beta software paragraph cites original page 1 [@evidence_b5348fa59b3948ae9540b75a33ca9bd9] and additional source [@evidence_6b169de2b78d452f919391b00916f2c8]."]
            else:
                chunks = [thought["text"]]
            for sentence in chunks:
                mappings.append({"sentence":len(sentences), "thought_ids":[thought["id"]]})
                sentences.append(sentence)
        response = {"paragraph":" ".join(sentences),"sentences":sentences,"sentence_mappings":mappings,
                    "_contract":{"actual_model":"TEST_FIXTURE_G09_CURRENT_NATIVE", "task":"paragraph_realization", "software_only":True}}
        validate(response, {t["id"] for t in ordered}, set(ids))
        key = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",",":")).encode()).hexdigest()
        contracts.append({"paragraph_id":paragraph["id"], "payload":payload,"input_sha256":key,"response":response})
assert len(contracts) == 11
assert tables() == before and hashlib.sha256(db.read_bytes()).hexdigest() == digest
(out / "all-tables.json").write_text(json.dumps(before,ensure_ascii=False,indent=2),encoding="utf-8")
(out / "contracts.json").write_text(json.dumps(contracts,ensure_ascii=False,indent=2),encoding="utf-8")
receipt = {"status":"PASS_CURRENT_NATIVE_GENERATION_INPUT_READY", "manuscript_id":ms,"revision":row["revision"],
           "paragraphs":len(contracts),"thoughts":len(thoughts), "original_alpha_exact":True,
           "original_beta_text_and_three_candidates_exact":True,"beta_original_two_selected_explicit_decision":True,
           "all_old_sections_paragraphs_groups_retained":True,"all_original205_plus_A206_reply_exact":True,
           "model_calls":len(before["studio_model_calls"]),"jobs":len(before["studio_jobs"]),
           "database_sha256":digest,"overall11_complete":False}
(out / "receipt.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
print(json.dumps(receipt),flush=True)
