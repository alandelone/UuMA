from pathlib import Path
import sys
from uuma.session import main
root=Path.cwd()
path=root/"active-session"/"HANDOFF.md"
raw=path.read_bytes()
old=path.read_text(encoding="utf-8")
backup_dir=root/".uuma-local"/"forge-diagrams-20261017-231008"
backup_dir.mkdir(parents=True,exist_ok=True)
backup=backup_dir/"HANDOFF.before.md"
if not backup.exists():
    backup.write_bytes(raw)
assert backup.read_bytes()==raw
summary="Generated a source-backed five-diagram Forge-Lab-Bot atlas pinned to HEAD 0e273c8dce5f846dd1ffebd78e0d9e60ce8d3319: architecture, laboratory workflow, Observatory read/display sequence, dataflow, and core class/code relationships. Deliverables are .archify/architecture-forge-lab-bot-20261017-231008/index.html and the five per-mode standalone HTML/candidate files, verification.json, passing receipt files, and forge-lab-bot-diagrams.zip. The navigation page includes Observatory startup/data-path instructions, card/full view/inspector/document interactions, other UI scope, and source links. All five Archify finalize runs ultimately passed validate, deliver, strict check and automated real-browser checks. No per-diagram perceptual visual review was requested or claimed; dataflow has one resolved crossover and class has two routing detours, documented in the navigation page. Artifact hashes and package were verified before final handoff. Product sources, business databases, Notion, external services and mission status/gates were not changed. Existing dirty session documentation is preserved. CodeGraph reports no usable project index and was not initialized. External labbot-commerce and eSchematic source directories referenced by this slice were absent locally; the separate UI implementations were not claimed inspected. Browser preview of the navigation page was requested through open_in_codex and returned queued. Entire previous handoff preserved verbatim below."+"\n\n"+old
sys.argv=["uuma.session","handoff","--summary",summary,"--dead-ends","Initial lifecycle start reported an unfinished session; resume succeeded. A bounded-source inspection mistakenly streamed a large verification report; targeted reads recovered the authoring references. One search named a nonexistent lab_service.py and returned 1 without changes. A quoted read-only browser-process query failed, then the corrected exact-profile query succeeded with no matching process. Initial workflow mainPath geometry and a class label-clearance check failed and were repaired without dropping nodes, edges or source meaning. The first Architecture browser gate retained a temporary Chrome profile because Chrome did not exit; the exact-profile process check found no remaining process, and a fresh serial finalize passed. No workspace reset or process termination was performed.","--next-step","Deliver the navigation-page link and optional ZIP to the user. Preserve verification/pending_review mission state. Further runtime/UI implementation, external repository inspection, deployment or live business operations require their own user-requested scope."]
main()
assert old in path.read_text(encoding="utf-8"), "Previous logical handoff must be fully preserved"
sys.argv=["uuma.session","check"]
main()
sys.argv=["uuma.session","close"]
main()
print("Fresh handoff, complete previous-context preservation, check and close passed.",flush=True)
