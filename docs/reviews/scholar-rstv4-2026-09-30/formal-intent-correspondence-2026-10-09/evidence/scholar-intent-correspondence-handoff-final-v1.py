from pathlib import Path
import hashlib
import json
import sys

from uuma.session import main

repo=Path.cwd()
folder=repo/'docs/reviews/scholar-rstv4-2026-09-30/formal-intent-correspondence-2026-10-09'
manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
assert manifest['overall_complete'] is False and manifest['g08_complete'] is False
for name,digest in manifest['files'].items():
    assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest,name
for name,digest in manifest['source_sha256'].items():
    assert hashlib.sha256((repo.parent/name).read_bytes()).hexdigest()==digest,name
mission=json.loads((repo/'mission_status.json').read_text(encoding='utf-8'))
assert mission['stage']=='verification' and mission['gate']['status']=='pending_review'
gate=(repo/mission['gate']['current']).read_text(encoding='utf-8')
previous=(repo/'active-session/HANDOFF.md').read_text(encoding='utf-8')
raw=(repo/'active-session/HANDOFF.md').read_bytes()
backup=repo/'.tmp/scholar-intent-correspondence-prior-handoff-final-v1.md'
with backup.open('xb') as handle: handle.write(raw)
fixture=json.loads((repo/'.tmp/scholar-intent-correspondence-native-v1.json').read_text(encoding='utf-8'))
runtime=json.loads((repo/'.tmp/scholar-intent-correspondence-runtime-refresh-v1.json').read_text(encoding='utf-8'))
summary=f'''2026-10-09 explicit author Intent correspondence batch sealed at {folder}.
Final27 focused correspondence tests and full1042 Python tests/20existing warnings PASS;
23backend workflow/static checks and15frontend checks PASS, final source hashes stable.
Formal manifest {len(manifest['files'])} files and15current sources freshly rehashed.
Native Chrome tab1479454458, port3006/8879, isolated root {fixture['root']};
new backend rootPID {runtime['new_backend_root_pid']}, frontend rootPID {fixture['processes']['frontend']}.
Only this owned8879backend refreshed to final guard; old3004/8877 and3005/8878 and three
previous native tabs intact, including unsynced revision copies. Re-mark them on next turn.
Native11new savedops r8→19: partialtwo-same-label-sourceREPLACE, crossmap2authorIntents,
Undo/Redo, explicitunmap+Undo, target edit+Undo/Redo/Undo. All exact payload/inverse,
originaltree/group/formulas/assets/citations/fullL2endpoints+conditions preserved.
Independent109table audit preserves all unrelated records. One declaredsoftware GENERATE,
two TEST_FIXTURE_AUTHOR_CORRESPONDENCE calls, five realcompiler artifacts, refreshed immutable
v1 readable. No actualrealmodel, science approval or download success claimed.
Mapped generated read now projects exact frozenauthorrevision and verifies originalbank,
context/formulas/assets/fullL2conditions alongside all old validated model-call/output/hash guards.
Complete report and native screenshot generated-two-paragraphs.png retained and sealed.
Keep original118requirements/G01..G11 full objective ACTIVE; no group or overall complete.
G08stillrequires actualqualifiedsource/content and fullbroader workflows. ZIP/PDF/native
downloads/filepopups paused by explicit user steering; user manuallyclosed popup.
No extension/browserpermission changes, upload grant, scienceapproval or workerrestart implied.
Mission remains verification/pending_review; no gate advanced. Preserve DSPyALL/Honc/controlguard
and all original12DONEactualmodelcalls, scientific workers and concurrent full handoff authority.

Entire preceding handoff follows without truncation or editorial replacement:

{previous}'''
dead_ends='''Retain all failed evidence: legacy flat provenance fallback; WAL135992→0 file-only
rollback baseline corrected by PRE-FREEZE checkpoint with everyrecord unchanged and original
fullbyte assertion retained; no freelist cause. OptionalDBSTAT unavailable. Generated original
read emptytemplate mismatch fixed; guessed unit/schema fields corrected before assertion update.
Response-review loader missing real pureURLmodule fixed without downloading. FinalL2tamper
with recomputed requesthash previouslyaccepted; exact originalcontextguard nowrejects.
One checkbox click didnotchange state, visiblelabel worked; cancellation/read after reload
transient waits notsuccess until verified; one pre-readyUndo click produced noop and was
retried only after stateinspection. FullpageScreenshot timedout; actualnativeviewport screenshot
saved. Allfailedlogs preserved. Prior scientific deadends retain their separate authority.
Never reset/clean, reduce guards, fake source/qualification, rerun oldDONEcalls, weaken scientific
contracts, edit session engine, accept downloadpermissions or claim11groupsdone from softwarefixture.'''
next_step='''Read current full handoff/mission/gate and continue original118-row/all11 acceptance
matrix. This batch is concrete software progress, not total completion. Inspect actual current
runtime/documents before continuing; nativefixture r19fixedgeneratedv1, all refs/contexts complete.
Prior3native pages and4thnew page are unfinishedworkflow handoffs. Browser instructions reload
documentation, selectedChrome3; keep downloads/filechooser/permissions paused. No messages to
other threads without human authorization. Preserve all unrelated workers and their scientific
authority; new mapped source audit does not approve science. Continue missing fullobjectChat,
actualsource/content, review/comment/invalidation, revision/publication and wholeworkflow items.
Freshly rehash sealed report/manifests, use CodeGraph first for indexed UuMA code, sessionwrap
commands, one writer, preserve fullpriorcontext, then handoff/check/close at next turn boundary.'''
receipt={'report':str(folder/'acceptance.md'),'report_sha256':manifest['files']['acceptance.md'],
         'manifest_files':len(manifest['files']),'current_sources':len(manifest['source_sha256']),
         'prior_logical_characters':len(previous),'prior_raw_sha256':hashlib.sha256(raw).hexdigest(),
         'gate_characters':len(gate),'all118_all11_complete':False,'goal_remains_active':True}
(repo/'.tmp/scholar-intent-correspondence-handoff-final-v1.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
def cli(*arguments):
    sys.argv=['uuma.session',*arguments]
    main()
cli('handoff','--summary',summary,'--dead-ends',dead_ends,'--next-step',next_step)
current=(repo/'active-session/HANDOFF.md').read_text(encoding='utf-8')
assert previous in current and summary in current
cli('check')
print(json.dumps({**receipt,'status':'PASS_FULL_CONTEXT_HANDOFF_AND_CHECK'},ensure_ascii=False),flush=True)
cli('close')
