from pathlib import Path
import hashlib
import json

repo = Path.cwd(); product = repo.parent
folder = repo / '.tmp/scholar-layout-applied-v1'
candidate = repo / '.tmp/scholar-layout-contract-proposal-v1/candidate'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text(encoding='utf8'))
patch = repo / '.tmp/scholar-layout-contract-proposal-v1.patch'
assert sha(patch) == 'cb73855c408aa4a7540910e737b1cc6ecff66c5fa589ebc46e465be9a320de23'
menu_patch = repo / '.tmp/scholar-block-menu-overlap-proposal-v1.patch'
assert sha(menu_patch) == '04a6a317a9a183090d8bec85bc99ab774a94257986340687749d313477c7221a'
names = [line[6:] for line in patch.read_text(encoding='utf8').splitlines() if line.startswith('+++ b/')]
menu_name = 'writing-studio/components/studio-workspace.tsx'
# Compose the five previously accepted menu hunks in memory. The first audit's git
# command ran beneath UuMA and silently skipped paths outside that repository prefix.
text = (candidate / menu_name).read_text(encoding='utf8')
menu_lines = menu_patch.read_text(encoding='utf8').splitlines(keepends=True)
active = False; hunks = []; old = []; new = []
for line in menu_lines:
    if line.startswith('--- '):
        if old or new: hunks.append((''.join(old), ''.join(new))); old=[]; new=[]
        active = False
    elif line.startswith('+++ '):
        active = line.strip() == '+++ b/' + menu_name
    elif active and line.startswith('@@ '):
        if old or new: hunks.append((''.join(old), ''.join(new))); old=[]; new=[]
    elif active:
        if line.startswith((' ', '-')): old.append(line[1:])
        if line.startswith((' ', '+')): new.append(line[1:])
if old or new: hunks.append((''.join(old), ''.join(new)))
assert len(hunks) == 5
for old, new in hunks:
    assert text.count(old) == 1
    text = text.replace(old, new, 1)
files = {}
for name in names:
    logical = text if name == menu_name else (candidate / name).read_text(encoding='utf8')
    expected = logical.replace('\n', '\r\n').encode('utf8')
    assert (product / name).read_bytes() == expected, name
    before = folder / 'before' / name
    files[name] = {'before_sha256': sha(before) if before.exists() else None,
                   'after_sha256': sha(product / name), 'exact_candidate_plus_accepted_menu_with_declared_LF_to_CRLF': True}
integration = 'RSTV4/tests/test_studio_layout_integration.py'
assert not (product / integration).exists()
(product / integration).write_bytes((repo / '.tmp/scholar-layout-async-review-v1/test_layout_async.py').read_bytes())
files[integration] = {'before_sha256': None, 'after_sha256': sha(product / integration)}
prior = read(repo / '.tmp/scholar-block-menu-native-v1/receipt.json')
changed = set(names + [integration])
for root, vector in [('RSTV4',prior['backend_source_vector']),('writing-studio',prior['frontend_product_vector'])]:
    actual_changed = {f'{root}/{name.replace(chr(92), "/")}' for name,h in vector.items() if sha(product / root / name) != h}
    assert actual_changed == {n for n in changed if n.startswith(root+'/') and (folder/'before'/n).exists()}, (root, actual_changed)
    for name,h in vector.items():
        if f'{root}/{name.replace(chr(92), "/")}' not in changed: assert sha(product / root / name) == h
assert sha(product / 'writing-studio/app/globals.css') == '71a987ed9a401130e4f6fccf6051868a5f2def4e42396ed1f1329cf627170a58'
receipt = {'status':'APPLIED_LAYOUT_CONTRACT_AND_SERVICE_INTEGRATION_TESTS_EXACT_AUDITED', 'files':files,
           'all_other_frozen_backend311_frontend91_exact':True,'accepted_menu_wrappers_and_css_preserved':True,
           'initial_apply_audit_failure_retained':True,'git_autocrlf_all_nine_files_exact':True,
           'nested_git_expected_copy_skipped_corrected_by_five_exact_unique_hunks':True,
           'patch_reapplied':False,'schema_changes':False,'native_acceptance':False,'final11_complete':False}
(folder/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
print(json.dumps(receipt,indent=2))
