from pathlib import Path
import sys
from uuma.session import main
ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
file=ROOT/'active-session/HANDOFF.md'
previous_bytes=file.read_bytes()
previous=file.read_text(encoding='utf-8')
backup=ROOT/'.uuma-local/scholar-diagrams-handoff-20261017-214800.bin'
with backup.open('xb') as handle: handle.write(previous_bytes)
assert backup.read_bytes()==previous_bytes
marker='Previous handoff preserved in full for Scholar diagrams task:\n\n'
summary=('Generated five interactive Archify diagrams for Scholar: architecture, documented scientific workflow, Observatory GET/SSE display sequence, dataflow, and actual UuMA class relationships. Overview/UI guide and portable ZIP are at .archify/scholar-20261017-214800/index.html and scholar-diagrams.zip. All five final artifacts passed validate, deliver, strict check and real-browser check; package content hashes and ZIP integrity passed. No perceptual review claimed. Repository pinned to 0e273c8dce5f846dd1ffebd78e0d9e60ce8d3319. RSTV4 external source is absent here, so internal scientific pipeline and Catalog/Studio are labelled documented contracts. Guide also includes optional Phoenix and explicit demo/hardcoded Observatory values, stale default Catalog path, and SSE card-refresh limits. Product source, service deployment, model/GPU/experiment/acquisition jobs and mission verification/pending_review unchanged. Initial dirty HANDOFF/progress changes preserved. '+marker+previous)
dead='CodeGraph reports no usable project index; direct source inspection used without indexing. Initial workflow mainPath marking rejected backward layout and was corrected without changing logical edges. One architecture placement trial exceeded readable width; restored original passing layout under skill contract. Architecture/dataflow retain advisory route crossings; no visual-quality claim. Two revised diagrams first hit Chrome temp-profile cleanup failures; read-only ownership inspection confirmed no retained-profile Chrome process remained, so frozen candidates were finalized again with separate evidence folders. No process was stopped or profile directory deleted. External RSTV4 source and service runtime unverified.'
next_step='Open the overview and use its five tabs or independent diagram links. Catalog/Studio runtime internals require the separate RSTV4 checkout for a code-level extension; no product change or gate transition is authorized by this diagram delivery.'
sys.argv=['uuma.session','--root',str(ROOT),'handoff','--summary',summary,'--dead-ends',dead,'--next-step',next_step]
main()
actual=file.read_text(encoding='utf-8')
assert actual.split(marker,1)[1][:len(previous)]==previous
sys.argv=['uuma.session','--root',str(ROOT),'check']
main()
sys.argv=['uuma.session','--root',str(ROOT),'close']
main()
print('Official handoff/check/close passed; prior handoff preserved exactly.')
