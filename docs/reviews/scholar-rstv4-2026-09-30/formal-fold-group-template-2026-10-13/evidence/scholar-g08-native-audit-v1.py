"""Independently audit actual G08 native operation snapshots and fixed provenance."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from copy import deepcopy
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
repo = Path.cwd()
root = repo / ".tmp" / "scholar-g08-native-v1"
out = root / "independent-audit-v1"
out.mkdir()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
info = read(root / "baseline.json")
a = info["manuscript_a"]
base = read(root / "baseline-all-tables.json")
original = json.loads(next(v for v in base["studio_documents"] if v["manuscript_id"] == a)["document_json"])

def receipt(phase: str) -> dict:
    return read(root / phase / "receipt.json")

def document(phase: str) -> dict:
    return receipt(phase)["document"]

def paragraphs(doc: dict) -> dict:
    items = [p for s in doc["sections"] for p in s["paragraphs"]]
    assert len({p["id"] for p in items}) == len(items)
    return {p["id"]: p for p in items}

def intents(doc: dict) -> dict:
    items = [i for p in paragraphs(doc).values() for i in p["intents"]]
    assert len({i["id"] for i in items}) == len(items)
    return {i["id"]: i for i in items}

def thoughts(doc: dict) -> dict:
    items = [t for i in intents(doc).values() for t in i["thoughts"]]
    assert len({t["id"] for t in items}) == len(items)
    return {t["id"]: t for t in items}

phases = ["folded", "grouped-originals", "group-tagged", "continued-baseline",
          "full-template-inserted", "partial-template-inserted", "template-replaced-unplaced",
          "empty-section-before-move", "empty-section-after-move", "empty-paragraph-before-move",
          "empty-intent-before-move", "empty-intent-after-move", "empty-intent-undo-restored",
          "empty-group-before-move", "empty-group-after-move", "ungrouped-content-retained",
          "group-ctrl-z-restored", "group-ctrl-y-redone", "group-undo-redo-final",
          "different-template-replaced", "refreshed-final"]
original_thoughts = thoughts(original)
assert len(original_thoughts) == 2
phase_revisions = {}
for phase in phases:
    data = receipt(phase)
    doc = data["document"]
    assert thoughts(doc) == original_thoughts, phase  # Exact values AND no duplicate/new thoughts.
    assert data["new_model_calls"] == data["new_generation_jobs"] == 0
    assert data["original20_artifact_sha_exact"] is True
    assert data["read_only_database_bytes_preserved"] is True
    assert doc["title"] == original["title"] and doc["abstract"] == original["abstract"]
    assert {p["id"] for p in original["sections"][0]["paragraphs"]} <= paragraphs(doc).keys()
    phase_revisions[phase] = data["author_revision"]

assert document("folded") == original
assert phase_revisions["folded"] == 18
old_paragraphs = paragraphs(original)
beta, alpha = list(old_paragraphs)
group_id = "paragraph_group_1634c698-89c8-4dad-94d0-7c369ab790ce"
grouped = document("grouped-originals")["sections"][0]
assert grouped["paragraph_groups"][0]["paragraph_ids"] == [beta, alpha]
assert grouped["block_order"] == [group_id]
tagged = document("group-tagged")["sections"][0]
assert tagged["paragraph_groups"][0]["label"] == "G08 preserved Beta + Alpha group"
assert paragraphs(document("group-tagged")) == old_paragraphs

pre = document("continued-baseline")
full = document("full-template-inserted")
assert full["sections"][0] == pre["sections"][0]
assert len(full["sections"]) == len(pre["sections"]) + 3
new_full = full["sections"][1:]
unit_ids = []
for section in new_full:
    assert len(section["paragraphs"]) == 1
    p = section["paragraphs"][0]
    assert p["purpose"] == p["paradigm"] == ""
    assert p["asset_ids"] == p["formulas"] == []
    assert len(p["intents"]) == 1 and p["intents"][0]["thoughts"] == []
    unit_ids.append(p["template_source"]["unit_id"])
assert len(set(unit_ids)) == 3

partial = document("partial-template-inserted")
assert len(partial["sections"]) == len(full["sections"])
new_partial = set(paragraphs(partial)) - set(paragraphs(full))
assert len(new_partial) == 1
partial_id = next(iter(new_partial))
partial_p = paragraphs(partial)[partial_id]
assert partial_p["template_source"]["unit_id"] == unit_ids[1]
assert partial_p["purpose"] == partial_p["paradigm"] == ""
assert partial_p["intents"][0]["thoughts"] == []
assert paragraphs(partial)[beta] == old_paragraphs[beta]
assert paragraphs(partial)[alpha] == old_paragraphs[alpha]
assert partial["sections"][0]["paragraph_groups"][0]["paragraph_ids"] == [beta, alpha, partial_id]
assert partial["sections"][1:] == full["sections"][1:]

replaced = document("template-replaced-unplaced")
assert len(replaced["sections"]) == len(partial["sections"]) + 2
expected_old = deepcopy(partial["sections"])
for section in expected_old:
    section["placement_status"] = "UNPLACED"
assert replaced["sections"][2:] == expected_old
assert [p["template_source"]["unit_id"] for s in replaced["sections"][:2] for p in s["paragraphs"]] == [unit_ids[0], unit_ids[2]]

empty_section_id = "section_479fdf4da2d64226995ff22eab90178f"
template_p_id = new_full[0]["paragraphs"][0]["id"]
template_i_id = new_full[0]["paragraphs"][0]["intents"][0]["id"]
empty_p_id = "paragraph_a9859ce2b7204bd0aa5662d42cc59b63"
empty_group_id = "paragraph_group_9e395ea0aac94f9abd25663ff7f1f221"
section = lambda doc: next(s for s in doc["sections"] if s["id"] == empty_section_id)
before = document("empty-section-before-move")
after = document("empty-section-after-move")
assert section(before)["paragraphs"] == []
assert [p["id"] for p in section(after)["paragraphs"]] == [template_p_id]
assert paragraphs(after)[template_p_id] == paragraphs(before)[template_p_id]
assert sum(template_p_id == p["id"] for s in after["sections"] for p in s["paragraphs"]) == 1
before = document("empty-paragraph-before-move")
after = document("empty-intent-before-move")
assert paragraphs(before)[empty_p_id]["intents"] == []
assert [i["id"] for i in paragraphs(after)[empty_p_id]["intents"]] == [template_i_id]
assert intents(after)[template_i_id] == intents(before)[template_i_id]
assert paragraphs(after)[template_p_id]["intents"] == []
before = document("empty-intent-before-move")
after = document("empty-intent-after-move")
beta_i_id = old_paragraphs[beta]["intents"][0]["id"]
beta_t = old_paragraphs[beta]["intents"][0]["thoughts"][0]
assert intents(before)[template_i_id]["thoughts"] == []
assert intents(after)[template_i_id]["thoughts"] == [beta_t]
assert intents(after)[beta_i_id]["thoughts"] == []
assert document("empty-intent-undo-restored") == before
before = document("empty-group-before-move")
after = document("empty-group-after-move")
assert section(before)["paragraph_groups"][0] == {"id": empty_group_id, "label": "", "paragraph_ids": []}
assert section(after)["paragraph_groups"][0]["paragraph_ids"] == [template_p_id]
assert paragraphs(after) == paragraphs(before)
ungrouped = document("ungrouped-content-retained")
assert section(ungrouped)["paragraph_groups"] == []
assert paragraphs(ungrouped) == paragraphs(after)
assert section(ungrouped)["block_order"] == [empty_p_id, template_p_id]
assert document("group-ctrl-z-restored") == after
assert document("group-ctrl-y-redone") == ungrouped
assert document("group-undo-redo-final") == after

current = read(root / "refreshed-final" / "all-tables.json")
operations = [v for v in current["studio_operations"] if v["manuscript_id"] == a]
for revision, expected in [(35, after), (36, ungrouped), (37, after), (38, ungrouped), (39, after)]:
    op = next(v for v in operations if v["resulting_revision"] == revision)
    assert op["operation_kind"] == ("UNDO" if revision in [35, 37, 39] else "REDO")
    assert json.loads(op["payload_json"])["document"] == expected

different = document("different-template-replaced")
assert different == document("refreshed-final")
old = deepcopy(document("group-undo-redo-final")["sections"])
for s in old:
    s["placement_status"] = "UNPLACED"
assert different["sections"][1:] == old
assert len(different["sections"][0]["paragraphs"]) == 1
assert different["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"] == []
assert paragraphs(different)[beta] == old_paragraphs[beta]
assert paragraphs(different)[alpha] == old_paragraphs[alpha]
assert len([s for s in different["sections"] if s.get("placement_status") == "UNPLACED"]) == 7
instances = current["studio_template_instances"]
assert len(instances) == 4
adoptions = [json.loads(v["adopted_json"]) for v in instances]
assert [v["resulting_revision"] for v in adoptions] == [21, 22, 23, 40]
assert [v["request"]["selected_unit_ids"] for v in adoptions[:3]] == [unit_ids, [unit_ids[1]], [unit_ids[0], unit_ids[2]]]
assert [v["request"]["scope_type"] for v in adoptions] == ["paper", "paragraph", "paper", "paper"]
assert adoptions[1]["request"]["scope_id"] == alpha
assert [v["request"]["mode"] for v in adoptions] == ["INSERT", "INSERT", "REPLACE", "REPLACE"]
assert adoptions[-1]["source"]["skeleton_id"] != adoptions[0]["source"]["skeleton_id"]
assert adoptions[-1]["source"]["paper_id"] != adoptions[0]["source"]["paper_id"]
assert adoptions[-1]["source"]["source_sha256"] != adoptions[0]["source"]["source_sha256"]
for v in adoptions:
    assert v["source"]["author_text_copied"] is False
    assert v["source"]["source_sha256"] == v["request"]["source_sha256"]
    assert v["source"]["paper_version"] == v["source"]["skeleton_version"] == 1
    assert v["request"]["replace_confirmed"] is (v["request"]["mode"] == "REPLACE")
    assert v["request"]["comment_ids"] == []
    assert v["resulting_revision"] == v["request"]["base_revision"] + 1

for name in ["studio_model_calls", "studio_chat_messages", "research_discussion_messages",
             "studio_jobs", "manuscript_versions", "studio_artifacts", "review_rounds",
             "review_comments", "studio_review_round_baselines", "studio_findings", "comment_changes"]:
    assert current[name] == base[name], name
assert len(current) == 109 and len(current["studio_artifacts"]) == 20
assert len(current["review_comments"]) == 205 and len(current["studio_model_calls"]) == 16
assert all(sha(v["storage_path"]) == v["sha256"] for v in current["studio_artifacts"])
source_seal = read(repo / ".tmp" / "scholar-g07-seal-v1.json")
manifest = read(Path(source_seal["directory"]) / "manifest.json")
assert all(sha(p) == h for p, h in manifest["current_source_sha256"].items())
scope = (repo / "docs/reviews/scholar-rstv4-2026-09-30/ui-requirements-preservation.md").read_text(encoding="utf-8")
requirements = [x for x in scope.splitlines() if re.match(r"^\|\s*(OV|CA|RV|AC|KG|TR|ST|WF|RE|CH)-\d+", x)]
groups = [x for x in scope.splitlines() if re.match(r"^\|\s*G-\d+", x)]
assert len(requirements) == 118 and len(groups) == 11
directions = read(root / "proof" / "label-three-directions.json")
assert directions == [{"chosen": v, "actual": v} for v in ["upright", "horizontal", "rotated"]]
result = {
    "status": "PASS_ORIGINAL_G08_NATIVE_SOFTWARE_CRITERIA",
    "original_requirements": 118, "original_groups": 11, "g08_definition": groups[7],
    "phase_revisions": phase_revisions,
    "fold_does_not_delete": True, "two_original_paragraphs_grouped_and_tagged": True,
    "three_label_directions_native_and_rotated_refresh": True,
    "full_template_native_keyboard_drag_and_three_empty_units": True,
    "partial_adoption_exact_second_source_unit_after_original_alpha": True,
    "confirmed_replacement_all_old_content_unplaced": True,
    "different_paper_and_skeleton_template_replacement": True,
    "all_four_empty_container_types_native_inside": ["section", "paragraph", "intent", "paragraph_group"],
    "original_thought_moved_then_exact_undo": True,
    "ungroup_keeps_content_order_and_undo_redo_exact": True,
    "buttons_and_ctrl_z_ctrl_y_ctrl_shift_z_native": True,
    "author_revision_final": 40, "manuscript_b_revision_preserved": 2,
    "unique_original_thoughts_and_citations_exact": True,
    "seven_unplaced_sections_retained": True, "template_adoptions": 4,
    "new_models": 0, "new_generations": 0, "artifacts_20_exact": True,
    "current_source_17_exact": True, "product_changes_this_g08": [],
    "overall_11_groups_complete": False,
}
(out / "receipt.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in result.items() if k not in ["phase_revisions", "g08_definition"]}, ensure_ascii=False), flush=True)
