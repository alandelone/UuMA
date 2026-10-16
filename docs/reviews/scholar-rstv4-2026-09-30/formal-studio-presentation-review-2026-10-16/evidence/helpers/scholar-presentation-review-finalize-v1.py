from pathlib import Path
from contextlib import closing
import hashlib,json,sqlite3,sys,time
repo=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text(encoding='utf8'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
seal=read(repo/'.tmp/scholar-presentation-review-seal-v1.json');report=Path(seal['directory'])
assert sha(report/'acceptance.md')==seal['acceptance_sha256'] and sha(report/'manifest.json')==seal['manifest_sha256']
assert all(sha(report/n)==v['sha256'] and (report/n).stat().st_size==v['bytes'] for n,v in read(report/'manifest.json').items())
base=repo/'docs/reviews/scholar-rstv4-2026-09-30/formal-original118-evidence-matrix-2026-10-15';matrix=read(base/'matrix.json')
assert matrix['schema_version']==12 and len(matrix['requirements'])==118 and len(matrix['groups'])==11
assert not matrix['overall118_complete'] and not matrix['final_all11_integrated_complete']
assert all(sha(base/n)==h for n,h in read(base/'manifest.json')['files'].items())
refs=read(base/'verified-references.json');assert len(refs)==52 and all(sha(Path(p))==h for p,h in refs.items())
full=read(repo/'.tmp/scholar-presentation-review-full-v1/receipt.json');assert full['status']=='PASS' and not full['changed_during_run']
assert all(sha(Path(p))==h for p,h in read(Path(full['source_before'])).items())
audit=read(repo/'.tmp/scholar-presentation-review-native-v1/final-audit.json');assert audit['all_other108_tables_and_old_checks_exact'] and audit['all_owned_services_stopped']
mission_path=repo/'mission_status.json';mission_sha=sha(mission_path);mission=read(mission_path)
assert mission['stage']=='verification' and mission['gate']['status']=='pending_review' and mission['gate']['blocked_by'] is None
old_digest=read(repo/'.tmp/scholar-frozen-origin-finalize-v1.json')['handoff_sha256']
with closing(sqlite3.connect((repo/'.uuma-local/uuma.db').resolve().as_uri()+'?mode=ro',uri=True)) as conn:
    row=conn.execute("SELECT payload FROM repo_session_events WHERE kind='handoff' AND json_extract(payload,'$.digest')=? ORDER BY id DESC LIMIT 1",(old_digest,)).fetchone()
assert row is not None
previous=json.loads(row[0])['content']
previous_path=repo/'.tmp/scholar-presentation-review-previous-verified-handoff-v1.md'
with previous_path.open('x',encoding='utf8') as handle:handle.write(previous)
assert sha(previous_path)==old_digest
live=repo/'active-session/HANDOFF.md';fresh=live.read_text(encoding='utf8');backup=repo/f'.tmp/scholar-presentation-review-fresh-entire-handoff-{time.time_ns()}.raw.md';backup.write_bytes(live.read_bytes())
current=f'''2026-10-16 Scholar original all11 goal remains ACTIVE/INCOMPLETE. Previous goal turn classified PROGRESS: frozen original Thought/Intent reverse views plus real citation-only guard and sealed1190 evidence. Current turn is PROGRESS: real independent pure-layout reply acknowledgement, actual native A215 confirmation, full1207 regression and evidence/matrixv12.

APPLIED: RSTV4 studio_api.py and studio_response_checks.py add PRESENTATION_MODIFIED without a schema migration; writing-studio response component/types add explicit third outcome and distinct history label. Exact baseline/target raw prose digest equality and empty diff, baseline present, real LAYOUT_ONLY/PRESENTATION evidence, scientific-support false, empty changed_text, both PDFs different hashes and moved actual boxes, correct fixed IDs/current PDF SHA, saved reply/decision/exact UTF16/unique evidence/full acknowledgement all required. Scientific MODIFIED guard unchanged. Switching UI outcomes clears claims and acknowledgement; unknown history outcomes not falsely shown as no-change. Old canonical request_id matching and raw stored historical context stay exact. New test_studio_presentation_review.py17 cases and actual component tests.

NATIVE ONCE: preserved scui-complex-native-qjbemsgz r86/v7, round4 baselinev6. A215 original saved decision/reply bytes unchanged; statementUTF16[24,126]. Scientific mode layout checkbox and confirmation remain disabled, switching to presentation clears assertions, then explicit typed selection/full reply ack. Exactly one actual POST200 created {audit['new_check_id']}; A215 RESOLVED/CURRENT outcomePRESENTATION_MODIFIED. Native independent history clearly says only presentation, finalPDF page1/visibleline4. Not EXPLAINED_NO_CHANGE or scientific approval. No generation/recompile/model/job/package/GPU/QuickRead/deepread/budget/IDM replay.

DATA/RESOURCES: complete110 onlyreview_comments + studio_response_checks changed: A215 status and updated_at only, unique new check; other108 tables and all old check context/request rows byteexact; all non-database files exact. All model/job/version/material/source/package state unchanged. Old21-file package intentionally remains the prior immutable snapshot and does NOT include this new acknowledgement. Final combined package is still due after remaining complex changes, do not falsely claim it is updated. Owned backend37240/8877 frontend40692/56581 console42552 retired by exact birth/cmd/cwd; no other processes stopped. Browser oldtab5 missing; reused existing complexBrowser and created tab6, now complexTab points6. Retired56581, do not reload dead URL or touch user8891/originalStudio. Old menuCdp points missingtab5: do not use without documented new-tab binding.

VERIFICATION: full current1207PASS/20 existing warnings,24JS suites,Ruff, source{full['source_count']} unchanged during full run and final seal. Backend316/frontend91/dist76. Focused17 compiler/HTTP/negative and component/TypeScript pass; full suite includes final fixture import correction. Production build5.06s at C:/Users/Alandelone/AppData/Local/Temp/scui-presentation-review-build-3cb8b9iz/writing-studio; originalsource/dist unchanged. Fixture __all__ exports needed for Ruff, and Ruff must run cwdRSTV4, not UuMA config. Auditorv1 wrongly compared stored historical request to body only; unchanged record adds exact manuscript/comment owners. Correctedv2 requires full owner+body exact, successful native check NOT replayed. Keep all lint/audit failures. Independent layout_candidate_review read-only review found no substantial typed-guard/idempotency/history defect; scope and legacy design file see agent state before relying on completion.

NEW SEALED REPORT: {report.as_posix()}, {seal['payload_files']} payloads, reportSHA {seal['acceptance_sha256']}, manifestSHA {seal['manifest_sha256']}. Never append to sealed directories. Matrix nowv12, original formal-original118-evidence-matrix-2026-10-15 directory;52 report digests verified, onlyRE09/RE12/RE13 changed, other115 exact; all118 original text/order/source_line and11 definitions exact. Matrix receipt .tmp/scholar-original118-presentation-v12/seal-receipt.json; priorv11 exact5files .tmp/scholar-original118-presentation-v12/prior-v11-formal. Both overall flagsfalse; missionverification/pending_review unchanged. New runtime final snapshot .tmp/scholar-presentation-review-native-v1/backend-terminal.json is authoritative root state; frozen-origins prior snapshot predates the new A215 check.

NEXT REAL WORK: legacy recorded checks missing origins need optional, verified, read-only supplemental origins from exact old generated_version/input_revision; never modify old context_json/request_json or use mutable current author. Existing agent design under .tmp/scholar-legacy-origin-design-v1 if written. Then positive structure/citation/material full type attribution and corresponding response acknowledgements, remaining original118 named gaps and final same-source all11 integrated run/combined delivery. Pure layout independent acknowledgement is now done; do not keep listing it as missing. Native initial parallel Failed to fetch and earlier inline-history-close observation remain unresolved; backend200 alone not proof. No scientific validity or external review approval inferred. GPU/QuickRead original successful handles never rerun; original30min budget event not repeated.

SHARED CONTEXT: complete fresh live handoff preserved below. Also preserve exact prior Scholar handoff from one named digest journal event if another shared writer changed the live file. No reset/clean or unrelated mission changes. Current full objective unchanged and incomplete.
'''
summary=current+'\n\nFULL FRESH SHARED HANDOFF (PRESERVED):\n\n'+fresh
if previous not in fresh:summary+='\n\nFULL PREVIOUS VERIFIED SCHOLAR HANDOFF (PRESERVED):\n\n'+previous
from uuma.session import main
for args in [['handoff','--summary',summary,'--dead-ends','Retained fixture import/Ruff cwd and owner-wrapper audit context failures; source assertions retained and no successful native action replayed. First-load native fetch and old inline-history click-close remain unresolved. No destructive cleanup or scientific approval.','--next-step','Continue full original all11 objective with verified legacy frozen-source supplemental read, then full complex structure/source/material attribution and native workflow. Preserve current r86/v7 and unique A215 check; final combined delivery still due. Use actual current matrixv12 and frozen source proof; keep all original scope and review boundaries.'],['check'],['close']]:
    sys.argv=['uuma.session',*args];main()
saved=live.read_text(encoding='utf8');assert fresh in saved and previous in saved and current in saved and sha(mission_path)==mission_sha
result={'status':'PASS_HANDOFF_CHECK_CLOSE','entire_fresh_handoff_preserved':True,'entire_prior_verified_handoff_preserved':True,
 'fresh_raw_backup':str(backup),'handoff_sha256':sha(live),'handoff_characters':len(saved),'matrix_schema':12,
 'verified_reports':52,'goal':'active','overall118_complete':False,'final11_complete':False}
with (repo/'.tmp/scholar-presentation-review-finalize-v1.json').open('x',encoding='utf8') as handle:json.dump(result,handle,indent=2)
print(json.dumps(result,indent=2))
