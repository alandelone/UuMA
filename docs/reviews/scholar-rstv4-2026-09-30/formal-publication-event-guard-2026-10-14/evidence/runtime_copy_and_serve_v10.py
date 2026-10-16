"""Retain every v9 guard, accepting only the sealed two-block publication fix."""
from pathlib import Path
import hashlib

import runtime_copy_and_serve_v9 as prior
from runtime_copy_and_serve_v9 import *


def product_guard():
    contract = read_json(REPO / '.tmp/scholar-publication-source-contract-v1/repair.json')
    path = RSTV4 / 'src/rstv4/studio.py'
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == contract['after_sha256']
    restored = raw
    for part in reversed(contract['replacements']):
        new, old = part['after'].encode(), part['before'].encode()
        assert restored.count(new) == 1
        restored = restored.replace(new, old, 1)
    assert restored == (REPO / '.tmp/scholar-publication-source-contract-v1/studio.py.before.raw').read_bytes()
    assert hashlib.sha256(restored).hexdigest() == contract['before_sha256']
    namespace = prior.product_guard.__globals__
    original_digest = namespace['digest']

    def digest_with_exact_declared_studio_reversal(candidate):
        if Path(candidate).resolve() == path.resolve():
            assert Path(candidate).read_bytes() == raw
            return contract['before_sha256']
        return original_digest(candidate)

    namespace['digest'] = digest_with_exact_declared_studio_reversal
    try:
        vector = prior.product_guard()
    finally:
        namespace['digest'] = original_digest
    keys = [key for key in vector if Path(key).resolve() == path.resolve()]
    assert len(keys) == 1 and vector[keys[0]] == contract['before_sha256']
    vector[keys[0]] = contract['after_sha256']
    full = REPO / '.tmp/scholar-publication-full-v1'
    assert read_json(full / 'receipt.json')['status'] == 'PASS'
    for name, digest in read_json(full / 'source-before.json').items():
        assert hashlib.sha256((RSTV4 / name).read_bytes()).hexdigest() == digest
    return vector
