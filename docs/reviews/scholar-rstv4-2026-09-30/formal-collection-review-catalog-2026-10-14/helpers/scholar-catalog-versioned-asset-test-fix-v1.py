from pathlib import Path
import hashlib
import json

repo = Path.cwd()
target = repo.parent / 'RSTV4/tests/test_catalog_web.py'
out = repo / '.tmp/scholar-catalog-versioned-asset-test-fix-v1'
out.mkdir()
raw = target.read_bytes()
(out / 'test_catalog_web.py.before.raw').write_bytes(raw)
old = b'''        assert '<script src="/catalog-collections.js"></script>' in page'''
new = b'''        asset_url = "/catalog-collections.js?v=bib-read-20261014"
        assert f'<script src="{asset_url}"></script>' in page
        script = client.get(asset_url)
        assert script.status_code == 200
        assert "createBibFileReader" in script.text'''
if b'\r\n' in raw:
    new = new.replace(b'\n', b'\r\n')
assert raw.count(old) == 1
updated = raw.replace(old, new)
target.write_bytes(updated)
assert target.read_bytes().replace(new, old) == raw
receipt = {'target': str(target), 'before_sha256': hashlib.sha256(raw).hexdigest(),
           'after_sha256': hashlib.sha256(updated).hexdigest(),
           'reason': 'Require the actual versioned script and successful current reader export; retain unversioned-route assertion.',
           'product_changed': False, 'failed_full_receipt': '.tmp/scholar-all11-current-regression-v1/receipt.json'}
(out / 'repair.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(receipt))
