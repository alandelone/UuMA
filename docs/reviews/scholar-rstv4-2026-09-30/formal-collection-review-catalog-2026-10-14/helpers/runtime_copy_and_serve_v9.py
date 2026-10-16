"""Retain every v8 guard and exactly reverse only the declared popover placement fix."""
from pathlib import Path
import hashlib
import runtime_copy_and_serve_v8 as prior
from runtime_copy_and_serve_v8 import *

_before_restore = prior.restore_bib_bytes
_repair = read_json(REPO / '.tmp/scholar-catalog-popover-fix-v1/repair.json')

class PriorPopoverBytes:
    def __init__(self, path):
        self.path = path
    def relative_to(self, other):
        return self.path.relative_to(other)
    @property
    def name(self):
        return self.path.name
    def read_bytes(self):
        raw = self.path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == _repair['after_sha256']
        ending = '\r\n' if _repair['crlf'] else '\n'
        old = _repair['old'].replace('\n',ending).encode('utf-8')
        new = _repair['new'].replace('\n',ending).encode('utf-8')
        assert raw.count(new) == 1
        restored = raw.replace(new,old)
        assert hashlib.sha256(restored).hexdigest() == _repair['before_sha256']
        assert restored == (REPO / '.tmp/scholar-catalog-popover-fix-v1/catalog_web.html.before.raw').read_bytes()
        return restored

def restore_bib_bytes(path):
    return _before_restore(PriorPopoverBytes(path) if path.relative_to(RSTV4).as_posix()=='src/rstv4/catalog_web.html' else path)

prior.restore_bib_bytes = restore_bib_bytes
product_guard = prior.product_guard

def fixture_vector_unchanged_except_declared_popover(before):
    current = product_guard()
    expected = dict(before)
    html = next(key for key in expected if Path(key).resolve() == (RSTV4 / 'src/rstv4/catalog_web.html').resolve())
    assert expected[html] == _repair['before_sha256']
    expected[html] = _repair['after_sha256']
    assert current == expected
    return current
