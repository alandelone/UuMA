from pathlib import Path
import hashlib
import json
import sys
from uuma.session import main

root=Path.cwd()
folder=root/'docs/reviews/scholar-rstv4-2026-09-30/formal-download-retry-2026-10-09'
manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
assert manifest['download_testing_paused'] is False and manifest['overall_complete'] is False
for name,digest in manifest['files'].items():
    assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest,name
mission=json.loads((root/'mission_status.json').read_text(encoding='utf-8'))
assert mission['stage']=='verification' and mission['gate']['status']=='pending_review'
previous=(root/'active-session/HANDOFF.md').read_text(encoding='utf-8')
raw=(root/'active-session/HANDOFF.md').read_bytes()
with (root/'.tmp/scholar-download-retry-prior-handoff-20261009-v1.md').open('xb') as handle: handle.write(raw)
summary=f'''2026-10-09 concrete progress: user changed their IDM setting and expressly authorized
ZIP/PDF native download retries. Download testing is NOW RESUMED, superseding older paused
instructions for downloading ONLY. No file upload/extension/security/science authorization.
Formal native delivery report {folder}/acceptance.md, manifest {len(manifest['files'])} files.
Actual browser clicks saved C:/Users/Alandelone/Downloads/manuscript.pdf13498bytes exact
SHAfa294a1fe284baeb7fc3c52a434d4476204e95b9b80067bfcb0f7549fea2f1cb;
submission_package_462feff00b234357a635a3e63254aff4 (1).zip20724bytes,16entries CRC+old
package sizes/hash/fixed MS/generatedv3/round2/baseline verified; independentclean-manuscript.pdf
8144bytes exactlysame as ZIP. Prior0Bzip preserved. No IDM modal needed pressing this retry.
Plugin download-event observer timedout but actualnativeChrome popup showsPDFdone and
actualfiles/hashes prove successful downloads. No terminal HTTP downloads substituted.
Observed incidental user Chrome/NewTab/music; do not control their unrelated windows.
No product code change, actual model call, new generation, scienceapproval, settings/permission
changes, upload or deletion. Parent872sealedfiles+15current sources freshly verified unchanged.
Native newzip tab1479454721 port3004 owns existing softwarefixture MSbd756... r3/round2;
existingfour native pages remain, including unsyncedcopies at1479454178. BrowserChrome3;
re-mark necessary pages next turn. @oai/sky ComputerUse supported native observations and
bounded popup screenshot saved, taskonly; CUA listWindows method unavailable.
Keep original118/G01..G11 goal ACTIVE/all11INCOMPLETE/G09notclosed. Mission verification/
pending_review, no gate advanced. Preserve every unrelated scientific/Honc/DSPy worker and
original12DONEcalls. Next continue remaining all118/wholeworkflow and scientificallyqualified
content; download obstacle positive paths are now verified, do not keep reporting them paused.

Complete preceding handoff follows unabridged; historical paused statements are superseded
only by the current user's explicit download-retry authorization:

{previous}'''
dead_ends='''Prior download0Bzip persists; currentnew(1)ZIP is separate valid20KBfile. Keep no-match
guessed ZIP control and observer timeout as failures of observation/context, not fabricated
download success. Actual nativeUI plus realfile roundtrip supersede observer for this case.
CUA native listWindows absent; used installed computer-use skill's sky observations, no bypass
or manualsecurity/nativehiddenprotocol. One session command child succeeded but progresswrite
Errno22 occurred afterwards; same unfinished session resumed through unchangedCLI, gate intact.
No need to rerun full1042suite for unchanged product source and native download settings.
All previous science/source/WAL/context deadends retained; never reset/clean or weaken guards.'''
next_step='''Continue actual118-row/all11 acceptance, using newlyverified download evidence.
Do not reintroduce paused-download status. Preserve browser and unsynceddraft handoffs.
Input/upload permission remains ungranted, no scientific review authorization implied.
If further downloads are needed, act only on observed allowed controls and realfixedbytes;
verify actualfiles instead of repeating a failed event observation blindly. Preserve failed0Bfile.
Do not interact with unrelated user Chrome/media/Explorer/settings. Reverify liveownedruntimes
and pending scientific worker status before any maintenance, never rerun12DONEcalls.
Read fullsharedhandoff/currentmission/gate and freshsource, use CodeGraph first for indexed
UuMA code, sessionwrapserialcommands, then preserveentireprevioushandoff and handoff/check/close.'''
receipt={'status':'PASS_DOWNLOAD_HANDOFF_FULL_CONTEXT','manifest_files':len(manifest['files']),
         'previous_logical_characters':len(previous),'previous_raw_sha256':hashlib.sha256(raw).hexdigest(),
         'report':str(folder/'acceptance.md'),'report_sha256':manifest['files']['acceptance.md'],
         'download_testing_resumed':True,'goal_remains_active':True,'all11_complete':False}
(root/'.tmp/scholar-download-retry-handoff-20261009-v1.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
def cli(*arguments):
    sys.argv=['uuma.session',*arguments]
    main()
cli('handoff','--summary',summary,'--dead-ends',dead_ends,'--next-step',next_step)
assert previous in (root/'active-session/HANDOFF.md').read_text(encoding='utf-8')
cli('check')
print(json.dumps(receipt,ensure_ascii=False),flush=True)
cli('close')
