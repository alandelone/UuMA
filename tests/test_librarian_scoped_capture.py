from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from uuma.librarian_scoped_capture import capture_scopes


def _public():
    return rsa.generate_private_key(public_exponent=65537, key_size=3072).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def test_independent_scopes_report_failure_and_never_claim_parent_coverage(tmp_path, monkeypatch):
    valid = tmp_path / 'app'
    valid.mkdir()
    (valid / 'history').write_text('history')
    sent = []

    def deliver(root, batch_id, **kwargs):
        sent.append((batch_id, kwargs['use_sessions']))
        return {'sha256': 'a' * 64}

    monkeypatch.setattr('uuma.librarian_scoped_capture.deliver_queued_batch', deliver)
    events = []
    results = capture_scopes(
        [{'source_id': 'app', 'path': str(valid)},
         {'source_id': 'missing', 'path': str(tmp_path / 'missing')}],
        queue=tmp_path / 'queue', public_pem=_public(), device='pc1', day='2026-10-30',
        host='fixture', ssh_identity=tmp_path / 'key', on_result=events.append,
    )
    assert results[0]['coverage'] == 'COMPLETE' and results[0]['server_intake'] == 'DELIVERED'
    assert results[0]['entries'] == 1 and results[0]['nas_publication'] == 'NOT_CHECKED'
    assert results[1]['status'] == 'FAILED' and results[1]['error_type'] == 'FileNotFoundError'
    assert events == results and sent == [('librarian:pc1:app:2026-10-30', True)]


def test_delivery_failure_keeps_encrypted_scope_pending(tmp_path, monkeypatch):
    valid = tmp_path / 'app'
    valid.mkdir()
    (valid / 'history').write_text('history')

    def offline(*args, **kwargs):
        raise OSError('offline')

    monkeypatch.setattr('uuma.librarian_scoped_capture.deliver_queued_batch', offline)
    result = capture_scopes([{'source_id': 'app', 'path': str(valid)}], queue=tmp_path / 'queue',
                            public_pem=_public(), device='pc1', day='2026-10-30',
                            host='fixture', ssh_identity=tmp_path / 'key')[0]
    assert result['coverage'] == 'COMPLETE' and result['server_intake'] == 'PENDING'
    assert result['delivery_error_type'] == 'OSError'
