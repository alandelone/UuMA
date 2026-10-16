from pathlib import Path
import hashlib
import json
import sys
import urllib.request

REPO = Path(__file__).resolve().parents[1]
CODE = (REPO / '.tmp/scholar-re10-native-v1.py').read_text(encoding='utf-8')
CODE = CODE.replace('scholar-re10-native-v1', 'scholar-re10-api-v1')
CODE = CODE.replace('scui-re10-native-', 'scui-re10-api-')
CODE = CODE.replace('PASS_EXACT_COPY_NATIVE_NOT_EXECUTED', 'PASS_EXACT_COPY_HTTP_NOT_EXECUTED')
CODE = CODE.replace('PASS_RE10_NATIVE_ARCHIVE_RESTORE', 'PASS_RE10_HTTP_ARCHIVE_RESTORE')
CODE = CODE[:CODE.index("if __name__=='__main__':")]
exec(compile(CODE, __file__, 'exec'), globals())
HERE.mkdir(exist_ok=True)


def request(method, path, label):
    receipt = read_json(HERE / 'copy-receipt.json')
    url = f"http://127.0.0.1:{receipt['backend_port']}{path}"
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read()
        record = {'method': method, 'path': path, 'status': response.status,
                  'body_sha256': hashlib.sha256(raw).hexdigest(),
                  'body': json.loads(raw)}
    exclusive_json(HERE / f'http-{label}.json', record)
    assert record['status'] == 200
    return record['body']


def capture(label, archived, verification):
    manuscript = PLAN['manuscript_id']
    base = f'/api/manuscripts/{manuscript}'
    active = request('GET', base + '/comments', label + '-active')
    all_comments = request('GET', base + '/comments?include_archived=true', label + '-all')
    history = request('GET', base + f'/comments/{COMMENT}/response-checks', label + '-history')
    rounds = request('GET', base + '/review-rounds', label + '-rounds')
    target = [c for c in all_comments if c['comment_id'] == COMMENT]
    assert len(target) == 1
    target = target[0]
    assert bool(target['archived_at']) == archived
    assert (COMMENT in {c['comment_id'] for c in active}) == (not archived)
    assert target['response_text'] == PLAN['original_comment']['response_text']
    assert target['status'] == PLAN['original_comment']['status'] == 'RESOLVED'
    assert target['review_round_id'] == PLAN['round']['review_round_id']
    assert target['round_number'] == 2
    assert target['response_verification']['status'] == verification
    assert len(history['history']) == 2
    assert len(target['changes']) == 4
    if label != 'before':
        prior = read_json(HERE / 'http-before-history.json')['body']
        assert history == prior, 'The complete two original check histories must remain exact'
        first = read_json(HERE / 'http-before-all.json')['body']
        original = next(c for c in first if c['comment_id'] == COMMENT)
        assert target['changes'] == original['changes']
        assert target['display_label'] == original['display_label'] == 'A206'
        assert target['import_metadata'] == original['import_metadata']
        assert rounds == read_json(HERE / 'http-before-rounds.json')['body']
        assert {c['comment_id']: c for c in all_comments if c['comment_id'] != COMMENT} == {
            c['comment_id']: c for c in first if c['comment_id'] != COMMENT}
    return target


def flow():
    receipt = read_json(HERE / 'copy-receipt.json')
    guard(receipt)
    assert not (HERE / 'http-before-active.json').exists(), 'Never replay uncertain mutations'
    assert snap(Path(receipt['root']) / 'data/catalog.db') == read_json(HERE / 'before-all-tables.json')
    capture('before', False, 'CURRENT')
    # This proof exercises shipped HTTP endpoints, not Windows/browser interaction.
    request('DELETE', f'/api/comments/{COMMENT}', 'archive')
    capture('archived', True, 'STALE')
    request('POST', f'/api/comments/{COMMENT}/restore', 'restore')
    capture('restored', False, 'STALE')
    capture('fresh-readback', False, 'STALE')
    audit()
    exclusive_json(HERE / 'scope.json', {
        'status': 'PASS_HTTP_ARCHIVE_RESTORE_WITH_NONEMPTY_REPLY_AND_ORIGINAL_HISTORY',
        'native_browser_executed': False,
        'native_browser_required': True,
        'actions': ['DELETE archive once', 'POST restore once'],
        'read_only_receipts': 16,
        'source_exact': True,
        'schema_exact': True,
        'unchanged_tables': 107,
        'declared_changed_tables': ['review_comments', 'studio_comment_response_state'],
        'response_revisions': [6, 7, 8],
        'history_preserved': 2,
        'changes_preserved': 4,
        'all11_complete': False,
    })


if __name__ == '__main__':
    {'prepare': prepare, 'serve': serve, 'flow': flow, 'audit': audit}[sys.argv[1]]()
