"""Exact byte reversal of the declared BibTeX race repair, preserving v6 guards."""
from pathlib import Path

_base=Path(__file__).with_name('runtime_copy_and_serve_v6.py').read_text(encoding='utf-8')
_helper='''
def restore_bib_bytes(path):
    contract=read_json(REPO/'.tmp/scholar-bib-read-recovery-v1/source-repair-v1.json')
    relative=path.relative_to(RSTV4).as_posix()
    change=next(item for item in contract['changes'] if item['relative']==relative)
    raw=path.read_bytes()
    assert digest(path)==change['after_sha256'], 'Undeclared extra BibTeX source change'
    text=raw.decode('utf-8').replace('\\r\\n','\\n')
    for item in reversed(change['replacements']):
        assert text.count(item['new'])==1
        text=text.replace(item['new'],item['old'])
    restored=text.replace('\\n','\\r\\n').encode('utf-8') if change['crlf'] else text.encode('utf-8')
    assert hashlib.sha256(restored).hexdigest()==change['before_sha256']
    assert restored==(REPO/'.tmp/scholar-bib-read-recovery-v1'/(path.name+'.before.raw')).read_bytes()
    return restored

'''
assert _base.count('def product_guard():')==1
_base=_base.replace('def product_guard():',_helper+'def product_guard():')
_needle="        elif p.relative_to(RSTV4).as_posix()=='src/rstv4/catalog_web.html':"
assert _base.count(_needle)==1
_base=_base.replace(_needle,"        elif p.relative_to(RSTV4).as_posix()=='src/rstv4/catalog_collections.js':\n            assert hashlib.sha256(restore_bib_bytes(p)).hexdigest()==before_sha\n"+_needle)
_old="            assert actual==receipt['after_sha256'] and receipt['related_tests']['passed']==15\n            raw=p.read_bytes()\n            lines=raw.splitlines(keepends=True)"
_new="            raw=restore_bib_bytes(p)\n            assert hashlib.sha256(raw).hexdigest()==receipt['after_sha256'] and receipt['related_tests']['passed']==15\n            lines=raw.splitlines(keepends=True)"
assert _base.count(_old)==1
_base=_base.replace(_old,_new)
exec(compile(_base,__file__,'exec'))
