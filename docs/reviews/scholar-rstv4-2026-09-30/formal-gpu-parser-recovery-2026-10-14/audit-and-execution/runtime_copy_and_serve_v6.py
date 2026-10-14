"""Explicit byte-preserving current-source contract; v1-v4 remain retained."""
import hashlib
from pathlib import Path
import runtime_copy_and_serve as original
from runtime_copy_and_serve import HERE,RECEIPT,REPO,RSTV4,check_sources,exclusive_json,read_json,snapshot,digest



def restore_bridge_bytes(raw):
    start=raw.index(b'def install_checkpoint_memory_compatibility()')
    end=raw.index(b'def main()',start)
    result=raw[:start]+raw[end:]
    for token in [b'import os',b'import zipfile',b'install_checkpoint_memory_compatibility()']:
        lines=[line for line in result.splitlines(keepends=True) if line.strip()==token]
        assert len(lines)==1
        result=result.replace(lines[0],b'',1)
    return result

def restore_current_bridge(p):
    receipt=read_json(HERE/'checkpoint-memory-fix-v1/receipt-after.json')
    assert digest(p)==receipt['after_sha256'] and receipt['exact_restoration']
    raw=restore_bridge_bytes(p.read_bytes())
    assert raw==(HERE/'checkpoint-memory-fix-v1/mineru_bridge.py.before.raw').read_bytes()
    return hashlib.sha256(raw).hexdigest()


def product_guard():
    declared=read_json(HERE/'preparation-receipt.json')['source_vectors']
    expected={item['path']:item['sha256'] for item in declared if Path(item['path']).is_relative_to(RSTV4)}
    expected.update(read_json(HERE/'runtime-source-vector.json'))
    endpoint_changes=read_json(REPO/'.tmp/scholar-g10-native-v1/concurrent-source-change-v1.json')
    for name,before_sha in expected.items():
        p=Path(name);actual=digest(p)
        if actual==before_sha:continue
        relative=str(p.relative_to(RSTV4))
        if relative in endpoint_changes:
            item=endpoint_changes[relative];raw=p.read_bytes()
            assert item['expected']==before_sha and item['actual']==actual
            assert raw.count(b'https://api.95963210.xyz/v1')==1
            assert hashlib.sha256(raw.replace(b'https://api.95963210.xyz/v1',b'http://127.0.0.1:8080/v1')).hexdigest()==before_sha
        elif p.relative_to(RSTV4).as_posix()=='src/rstv4/catalog_web.html':
            receipt=read_json(HERE/'review-count-fix-v1/receipt-after.json')
            before=(HERE/'review-count-fix-v1/catalog_web.html.before.raw').read_bytes()
            assert hashlib.sha256(before).hexdigest()==before_sha==receipt['before_sha256']
            assert actual==receipt['after_sha256'] and receipt['related_tests']['passed']==15
            raw=p.read_bytes()
            lines=raw.splitlines(keepends=True)
            extra=[line for line in lines if b"$('pdf-review-stat').textContent=`PDF" in line and b'cases.filter' in line or b"$('parser-review-stat').textContent=`" in line and b'cases.filter' in line]
            assert len(extra)==2
            restored=raw
            for line in extra:restored=restored.replace(line,b'',1)
            assert restored==before
        elif p.relative_to(RSTV4).as_posix()=='scripts/mineru_bridge.py':
            receipt=read_json(HERE/'mineru-cpu-fix-v1/receipt-after.json')
            before=(HERE/'mineru-cpu-fix-v1/mineru_bridge.py.before.raw').read_bytes()
            assert hashlib.sha256(before).hexdigest()==before_sha==receipt['before_sha256']
            assert restore_current_bridge(p)==receipt['after_sha256'] and receipt['existing_parser_quality_tests_passed']==12
            raw=restore_bridge_bytes(p.read_bytes());start=raw.index(b'def install_ocr_device_compatibility()');end=raw.index(b'def main()',start)
            restored=raw[:start]+raw[end:]
            calls=[line for line in restored.splitlines(keepends=True) if line.strip()==b'install_ocr_device_compatibility()']
            assert len(calls)==1
            assert restored.replace(calls[0],b'',1)==before
        else:raise AssertionError('Undeclared prepared product source changed: '+name)
        expected[name]=actual
    return expected


original.product_guard=product_guard
if __name__=='__main__':original.main()
