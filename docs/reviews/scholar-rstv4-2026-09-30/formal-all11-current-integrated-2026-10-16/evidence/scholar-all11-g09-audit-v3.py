"""Audit actual G09 native readback and one completed fixed round4 delivery job."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
import zipfile

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('g09', REPO / '.tmp/scholar-all11-g09-current-v2.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
receipt, root, context = m.guard()
folder = m.HERE
assert m.read(folder / 'owned-stop-terminal.json')['all_owned_services_retired']
for port in [3000, 8877, 8875]: m.rt.port_free(port)
before = m.read(folder / 'before110.json')
after = m.b.snapshot(root / 'data/catalog.db')
assert after == m.read(folder / 'final110.json') and before['schema'] == after['schema']
assert {k for k, v in after['tables'].items() if v != before['tables'][k]} == {'studio_jobs', 'studio_submission_packages'}
inspection = m.read(folder / 'package-readonly-inspection.json')
job, package = inspection['new_job'], inspection['new_package']
for table, key, new in [('studio_jobs', 'job_id', job), ('studio_submission_packages', 'package_id', package)]:
    a = {x[key]: x for x in m.b.records(before, table)}
    z = {x[key]: x for x in m.b.records(after, table)}
    assert z.keys() == a.keys() | {new[key]}
    assert all(z[k] == v for k, v in a.items()) and z[new[key]] == new
assert job['status'] == 'SUCCEEDED' and job['job_kind'] == 'SUBMISSION_PACKAGE' and job['input_revision'] == 86
assert json.loads(job['request_json']) == {'review_round_id': m.ROUND}
manifest = json.loads(package['manifest_json'])
assert len(manifest['files']) == 21 and manifest['generated_version_id'] == m.VERSION
assert manifest['review_round_id'] == m.ROUND and manifest['unresolved_comment_ids'] == []
assert manifest['location_summary']['layout_only_rows'] == 1
assert not manifest['location_summary']['semantic_or_response_claims_approved']
directory = Path(json.loads(job['result_json'])['directory'])
history = m.read(directory / 'response-review-history.json')
assert not history['scientific_acceptance'] and not history['automatic_response_approval']
assert len(history['comments']) == 1 and history['comments'][0]['comment_id'] == m.COMMENT
hc = history['comments'][0]
assert hc['verification']['status'] == 'CURRENT' and hc['verification']['check_id'] == m.CHECK
assert hc['verification']['outcome'] == 'PRESENTATION_MODIFIED' and len(hc['checks']) == 1
record = m.b.one(after, 'studio_response_checks', 'check_id', m.CHECK)
assert hc['checks'][0]['context'] == json.loads(record['context_json'])
assert hc['checks'][0]['request'] == json.loads(record['request_json'])
assert hc['checks'][0]['context_sha256'] == record['context_sha256']
calls = m.read(directory / 'generation-model-calls.json')
assert calls['calls'] == []  # v7 layout replay has no new model calls; preserve stated provenance.

sys.path.insert(0, str(m.b.RST / 'src'))
from rstv4.studio_delivery import package_content
from rstv4 import studio_response_checks as checks
with closing(sqlite3.connect((root / 'data/catalog.db').resolve().as_uri()+'?mode=ro', uri=True)) as conn:
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    row = conn.execute('SELECT * FROM review_comments WHERE comment_id=?', (m.COMMENT,)).fetchone()
    assert checks.status(conn, m.MS, row) == hc['verification']
    assert checks.history(conn, m.COMMENT) == hc['checks']
    pending = [dict(conn.execute('SELECT * FROM review_comments WHERE comment_id=?', (identifier,)).fetchone())
               for identifier in ['comment_0acc6bedbeeb4b8191786b5d1e59f3f5', 'comment_342fc9f8af994f599623410886be6877']]
    assert all(row['status'] == 'PENDING' for row in pending)
packages = []
for row in m.b.records(after, 'studio_submission_packages'):
    expected = json.loads(row['manifest_json'])
    origin = 'CURRENT_COPY_PRODUCT_DELIVERY'
    if row['package_id'] == 'submission_package_9ed351f308a34c08909b5933c99c9c24':
        sealed = REPO / 'docs/reviews/scholar-rstv4-2026-09-30/formal-source-round-reply-2026-10-13'
        relative = 'evidence/native/response-package-audited-v1/actual-response-package.zip'
        sealed_manifest = m.read(sealed / 'manifest.json')
        recorded_sha = sealed_manifest['files'][relative.replace('/', chr(92))]
        raw = (sealed / relative).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == recorded_sha == '42cca3508fdba2b6bd39527bbc4820514b2bd4c73415cd677a8a76f39634484c'
        filename, mime = row['package_id']+'.zip', 'application/zip'
        origin = 'ORIGINAL_SEALED_ROUND2_ZIP_CURRENT_COPY_PAYLOAD_UNAVAILABLE'
    else:
        raw, filename, mime = package_content(root / 'data/catalog.db', root / 'data/writing-studio', m.MS, row['package_id'])
    expected = json.loads(row['manifest_json'])
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert z.testzip() is None and sorted(z.namelist()) == sorted(expected['files'])
        assert len(z.namelist()) == len(set(z.namelist()))
        for member in z.namelist():
            content = z.read(member)
            if member == 'manifest.json': assert json.loads(content) == expected
            else:
                item = expected['file_integrity'][member]
                assert len(content) == item['size_bytes'] and hashlib.sha256(content).hexdigest() == item['sha256']
    target = folder / ('delivery-' + filename)
    if target.exists():
        assert target.read_bytes() == raw, 'Retained prior audit ZIP differs'
    else:
        with target.open('xb') as f: f.write(raw)
    digest = hashlib.sha256(raw).hexdigest()
    if row['package_id'] == 'submission_package_04b7b4c8d0fa4e25b5009089c5a863c8':
        assert digest == '4dd985ae36c51afd8100dce6e86b005663d36427b70afe1bcc1319ce18fc8810'
    packages.append({'origin': origin, 'package_id': row['package_id'], 'review_round_id': row['review_round_id'],
        'generated_version_id': expected['generated_version_id'], 'files': len(expected['files']),
        'zip_path': str(target), 'sha256': digest, 'bytes': len(raw),
        'unresolved_comment_ids': expected['unresolved_comment_ids']})
assert m.b.snapshot(root / 'data/catalog.db') == after
files = m.b.filemap(root)
assert files == m.read(folder / 'final-files.json')
old = m.read(folder / 'before-files.json')
assert {k for k in old if old[k] != files[k]} == {'data/catalog.db'}
prefix = directory.relative_to(root).as_posix() + '/'
assert set(files)-set(old) == {prefix + filename for filename in manifest['files']}
assert len(set(files)-set(old)) == 21

def native(filename, strings):
    text = (folder / filename).read_text(encoding='utf-8')
    for string in strings: assert string in text, (filename, string)
native('02-third-source-fixed.dom.txt', ['固定于成文 v7', 'New original software source body.',
    'parse_run_ad5cc39cd5c467e18a00215fd9b5a86c', 'software-native-other-file',
    'skeleton_dacb7912eb37f640e511be09e374aacf', 'unit_aa3c1d64881f03b52cc0af2c6b4d8f52'])
native('05-round1-fixed.dom.txt', ['固定被审稿 v4 / 作者结构 r11'])
native('06-round2-A206.dom.txt', ['固定被审稿 v3 / 作者结构 r10', '需要重新核对'])
native('07-A206-original-import.dom.txt', ['comment_import_3c39a6fab1d7498a92deba6e55d2fb28', '原始顺序：第 1 条'])
native('08-A206-fixed-history.dom.txt', ['成文 v5', '1:02 PM', '1:05 PM', '可见文本第 8 行'])
native('09-A206-original-thought-expanded.dom.txt', ['成文 v5 / 原稿 r62', 'thought_5f3edebed89d482cb0b2d9d42c4930d8'])
native('10-original-link-reversal-history.dom.txt', ['作者修订 r16 → r17', '保存时的原意见上下文：未关联意见', '撤销关联决定', '修改前', '修改后'])
native('11-unlinked-filter.dom.txt', ['未关联意见" [selected]'])
native('12-round3-unresolved.dom.txt', ['固定被审稿 v5 / 作者结构 r62', '意见状态 A213', '意见状态 A214', '回复尚未核对'])
native('13-A212-history-final.dom.txt', ['成文 v6', '可见文本第 16 行', '可见文本第 18 行', '可见文本第 19 行', '可见文本第 21 行'])
native('14-A212-origin.dom.txt', ['成文 v6 / 原稿 r79', 'thought_author_1'])
native('04-A215-current-history.dom.txt', ['作者确认仅排版修改', '成文 v7', '正文、引用与素材未变'])
native('16-new-package-files.dom.txt', manifest['files'])
events = [m.read(p) for p in sorted(folder.glob('http-*.json'))]
assert all(e.get('complete') and e.get('status') in {200, 202} and e['allowed'] and 'exception_type' not in e for e in events)
writes = [e for e in events if e['method'] not in {'GET', 'HEAD', 'OPTIONS'} and e['path'].endswith('/jobs')]
assert len(writes) == 1 and writes[0]['status'] == 202
m.guard()
proof = {'status': 'PASS_G09_CURRENT421_ORIGINAL_SOFTWARE_DEFINITION',
    'at_utc': datetime.now(timezone.utc).isoformat(), 'new_job': job['job_id'], 'new_package': package['package_id'],
    'new_package_manifest': manifest, 'preserved_and_new_packages': packages,
    'schema_and_other108_tables_exact': True, 'old_jobs_packages_all_rows_exact': True,
    'models_generations_checks_approvals_author_mutations': 0, 'new_package_jobs': 1,
    'old_payload_files_exact': True, 'new_package_files': 21, 'all_owned_services_retired': True,
    'round3_pending_ids': [row['comment_id'] for row in pending], 'native_http_requests': len(events),
    'old_round2_current_copy_payload_available': False, 'old_round2_sealed_zip_verified': True, 'native_IDM_download_retested': False, 'overall118_complete': False,
    'evidence': {p.name: {'sha256': m.sha(p), 'bytes': p.stat().st_size} for p in sorted(folder.iterdir()) if p.is_file()}}
m.put(folder / 'g09-audit-receipt.json', proof)
report = '''# G09 当前源码综合验收

PASS。当前程序实际读回第三来源的原文、页段、Paper/parse/file/Skeleton/unit版本；来源1/2及旧版本读回同时绑定已通过G05/G02的同源证据。第一轮固定v4/r11、第二轮独立v3/r10、第三轮v5/r62、第四轮v6/r79，原基线及生成历史均未修改。

A206原意见、编辑版本、原顺序/批次与完整原文可查；两次原v5确认及页1/行8保留，当时r62作者思想通过只读入口补查，当前旧确认明确STALE。原r16→17未关联修改的实际前后对照、后补A01+A02、撤销、再仅A02三条记录均可读，未关联筛选真实可用。没有重复旧关联/撤销/核对。

A212原v6/r79五条共享/独立句页行记录及原思想可查；不把旧确认冒充当前。A213/A214继续PENDING，无未经证实的完成声明。A215原唯一PRESENTATION_MODIFIED确认仍CURRENT，保存完整回复、原版本和真实排版页行；未新增确认。

从受保护A86/v7 checkpoint建立专属副本，仅重定位37项原材料storage_path，其他行字段及文件字节保持。原可变A103/B4综合操作分支及受保护A86根均未变。原生界面单次提交新round4 SUBMISSION_PACKAGE，成功新增一个job和一个package，其他108表/schema精确，无cache/作者/模型/生成/确认/阶段增量。

新21文件包包含A215原CURRENT确认与完整context/request，clean/baseline PDF及CSV/SVG/render均按manifest逐字节校验。调用产品只读交付函数得到本轮新包和旧round4包ZIP；旧round2在当前副本的payload目录缺失，实际拒绝原样保留，因此读取已封存且SHA精确一致的原round2 ZIP。三份ZIP，逐成员核对CRC、成员集合、大小和SHA；旧21文件包仍精确SHA 4dd985ae…8810，新包作为新快照保存。没有重新测试浏览器或IDM下载，也没有修改旧包。

round4未解决清单为空只代表该轮A215；第三轮待处理及第一轮旧意见明确保留。旧round2的16文件包、旧round4包、新round4包与各轮当前读取证据将统一纳入最终验收材料。v7为旧模型结果的排版重放，generation-model-calls空记录保持原义，不伪造新模型调用。此为软件验收，未对外投稿，不代表科学批准或原118全部完成。

本轮实际服务均退出，端口空闲，用户原Studio与8891页未操作。11组各自软件范围已有当前组合证据；统一封存与原始要求逐项最后核对后才可声明final11完成。
'''
with (folder / 'acceptance.md').open('x', encoding='utf-8') as f: f.write(report)
print('PASS_G09_CURRENT421_ONE_NEW_PACKAGE_21_MEMBERS_OLD_RECORDS_EXACT')
