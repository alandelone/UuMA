from pathlib import Path
p = Path.cwd().parent / "writing-studio/components/studio-response-review.tsx"
text = p.read_text(encoding="utf-8")
needle = "row.changed_text ||"
assert text.count(needle) == 2
p.write_text(text.replace(needle, "(row.display_changed_text ?? row.changed_text) ||"), encoding="utf-8")
print("READABLE_EVIDENCE_LABELS_APPLIED_WITH_RAW_ROW_IDS_UNCHANGED")
