from pathlib import Path
import json
import hashlib

repo = Path.cwd()
root = repo / ".tmp/scholar-g09-native-v2"
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
base = read(root / "round2-created/all-tables.json")
now = read(root / "post-association-audited/all-tables.json")
opinion = read(root / "opinion-source-audited/all-tables.json")
a01 = "comment_f7969d2589c14c6a9e3d1c923bd1b381"
a02 = "comment_49f64aa1ab3f4bdca2c74fd0aa84c8a1"
a206 = "comment_8ecd722c5ea041858723009b72fc4cce"
beta = "change_ee83003b4ee34353abed917e48f9d338"
alpha = "change_b4d65900fbe541aeb4d597de70681d46"
allowed = {"review_comments", "comment_changes", "studio_change_link_events", "studio_change_link_state"}
for name, rows in base.items():
    if name not in allowed:
        assert now[name] == rows, name
assert now["review_comments"] == opinion["review_comments"]
assert len(now["review_comments"]) == 206
assert all(row in now["review_comments"] for row in base["review_comments"])
comment = next(r for r in now["review_comments"] if r["comment_id"] == a206)
metadata = json.loads(comment["import_metadata_json"])
assert metadata["original_text"] == comment["original_text"] == metadata["raw_import_text"]
assert metadata["original_index"] == 0 and metadata["comment_number"] == 206
assert metadata["import_batch_id"] == "comment_import_3c39a6fab1d7498a92deba6e55d2fb28"
assert comment["edited_text"] == comment["original_text"] + "\nG09 author preview note: this second-round opinion is a software fixture, not an external review."
assert comment["review_round_id"] == "review_round_b51564f0224e499081e58f341103b336"
assert comment["status"] == "PENDING" and comment["reviewer"] is None
assert comment["author_decision"] is None and comment["response_text"] is None
assert now["comment_changes"] == base["comment_changes"] + [
    {"comment_id": a02, "change_id": beta}, {"comment_id": a206, "change_id": alpha}]
expected = [(beta, [], sorted([a01, a02]), 0, 1),
            (beta, sorted([a01, a02]), [], 1, 2),
            (beta, [], [a02], 2, 3), (alpha, [], [a206], 0, 1)]
events = now["studio_change_link_events"]
assert base["studio_change_link_events"] == [] and len(events) == 4
assert len({e["request_id"] for e in events}) == 4
for event, (change, before, after, oldrev, newrev) in zip(events, expected):
    assert event["change_id"] == change
    assert json.loads(event["before_comment_ids_json"]) == before
    assert json.loads(event["after_comment_ids_json"]) == after
    assert event["base_link_revision"] == oldrev and event["resulting_link_revision"] == newrev
    request = json.loads(event["request_json"])
    assert request["change_id"] == change and request["comment_ids"] == after
    assert request["expected_link_revision"] == oldrev
    assert request["manuscript_id"] == "manuscript_56652adf9d054cb6ab3819efacf3475c"
assert events[1]["reverses_event_id"] == events[0]["event_id"]
assert all(e["reverses_event_id"] is None for i,e in enumerate(events) if i != 1)
for old, current in zip(base["studio_change_link_state"], now["studio_change_link_state"]):
    expected_row = dict(old)
    if old["change_id"] in [alpha, beta]:
        assert old["initial_comment_ids_json"] == "[]" and old["initial_origin"] == "recorded_at_save"
        expected_row["link_revision"] = 1 if old["change_id"] == alpha else 3
    assert current == expected_row
assert len(now["studio_change_link_state"]) == len(base["studio_change_link_state"])
out = root / "independent-provenance-and-links-v1"
out.mkdir()
receipt = {"status": "PASS_G09_NATIVE_PROVENANCE_POSTLINK_REVERSAL_SUBCASES",
           "all109_tables_audited": True, "all_original205_comments_exact": True,
           "new_opinion_original_edited_raw_batch_order_separate": True,
           "original_author_documents_operations_changes_models_jobs_versions_artifacts_exact": True,
           "two_fixed_round_baselines_exact": True, "new_link_events": events,
           "beta_initial_context_still_empty": True, "alpha_initial_context_still_empty": True,
           "g09_complete": False, "overall11_complete": False}
(out / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k:v for k,v in receipt.items() if k != "new_link_events"}))
