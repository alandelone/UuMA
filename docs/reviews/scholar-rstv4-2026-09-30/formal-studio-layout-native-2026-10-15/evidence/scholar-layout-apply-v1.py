from pathlib import Path
import hashlib
import json
import shutil
import subprocess

repo = Path.cwd()
product = repo.parent
folder = repo / '.tmp/scholar-layout-applied-v1'
folder.mkdir(exist_ok=False)
candidate = repo / '.tmp/scholar-layout-contract-proposal-v1/candidate'
patch = repo / '.tmp/scholar-layout-contract-proposal-v1.patch'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text(encoding='utf8'))
assert sha(patch) == 'cb73855c408aa4a7540910e737b1cc6ecff66c5fa589ebc46e465be9a320de23'
prior = read(repo / '.tmp/scholar-block-menu-native-v1/receipt.json')
vectors = {'RSTV4': prior['backend_source_vector'], 'writing-studio': prior['frontend_product_vector']}
for root, vector in vectors.items():
    assert all(sha(product / root / n) == h for n, h in vector.items()), root
checks = [read(p) for p in (repo / '.tmp/scholar-layout-async-review-v1').glob('receipt-*.json')]
assert any(r['exit_code'] == 0 and '10 passed' in Path(r['log']).read_text(encoding='utf8') for r in checks)
assert any(r['exit_code'] == 0 and '2 passed' in Path(r['log']).read_text(encoding='utf8') for r in checks)
names = [line[6:] for line in patch.read_text(encoding='utf8').splitlines() if line.startswith('+++ b/')]
assert len(names) == 9
expected_root = folder / 'expected'
before = {}
for name in names:
    path = product / name
    before[name] = sha(path) if path.exists() else None
    if path.exists():
        backup = folder / 'before' / name
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(path.read_bytes())
    target = expected_root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((candidate / name).read_bytes())
menu_patch = repo / '.tmp/scholar-block-menu-overlap-proposal-v1.patch'
# Keep the already accepted menu wrappers when composing the independent layout patch.
# Menu CSS is unchanged by layout and is checked separately against its accepted hash.
result = subprocess.run(['git', 'apply', '--include=writing-studio/components/studio-workspace.tsx', str(menu_patch)],
                        cwd=expected_root, capture_output=True, text=True)
assert result.returncode == 0, result.stderr
dry = subprocess.run(['git', 'apply', '--check', str(patch)], cwd=product, capture_output=True, text=True)
assert dry.returncode == 0, dry.stderr
result = subprocess.run(['git', 'apply', str(patch)], cwd=product, capture_output=True, text=True)
assert result.returncode == 0, result.stderr
files = {}
for name in names:
    raw = (expected_root / name).read_bytes().replace(b'\r\n', b'\n')
    original = folder / 'before' / name
    if original.exists() and b'\r\n' in original.read_bytes():
        raw = raw.replace(b'\n', b'\r\n')
    assert (product / name).read_bytes() == raw, name
    files[name] = {'before_sha256': before[name], 'after_sha256': sha(product / name), 'exact_candidate_plus_menu_with_original_line_endings': True}
integration = 'RSTV4/tests/test_studio_layout_integration.py'
assert not (product / integration).exists()
test_source = repo / '.tmp/scholar-layout-async-review-v1/test_layout_async.py'
(product / integration).write_bytes(test_source.read_bytes())
files[integration] = {'before_sha256': None, 'after_sha256': sha(product / integration)}
changed = set(names + [integration])
for root, vector in vectors.items():
    for name, h in vector.items():
        if f'{root}/{name.replace(chr(92), "/")}' not in changed:
            assert sha(product / root / name) == h, (root, name)
assert sha(product / 'writing-studio/app/globals.css') == '71a987ed9a401130e4f6fccf6051868a5f2def4e42396ed1f1329cf627170a58'
receipt = {'status': 'APPLIED_LAYOUT_CONTRACT_AND_SERVICE_INTEGRATION_TESTS', 'files': files,
           'all_other_frozen_backend311_frontend91_exact': True, 'accepted_menu_wrappers_and_css_preserved': True,
           'patch_applied_once': True, 'schema_changes': False, 'native_acceptance': False, 'final11_complete': False}
(folder / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf8')
print(json.dumps(receipt, indent=2))
