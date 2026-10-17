"""Independent terminal audit of actual G11 current-source reads and refusals."""
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('g11_runtime', REPO / '.tmp/scholar-all11-g11-runtime-v2.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
b, receipt = r.load_base()
r.guard(b, receipt)
evidence = {}
http = {}
for role in r.ROLES:
    folder = r.HERE / role
    plan = r.plan_guard(role, b, receipt)
    terminal = r.read(folder / 'owned-stop-terminal.json')
    assert terminal['status'] == 'EXACT_OWNED_ROLE_STOPPED_PORTS_FREE'
    assert terminal['all110_and_files_exact'] and terminal['all_owned_identities_absent']
    for value in terminal['identities'].values():
        assert r.absent(value)
    for port in plan['ports'].values():
        r.port_free(port)
    events = [r.read(p) for p in sorted(folder.glob('*-http-*.json'))]
    assert events and all(e['response_complete'] and 'exception_type' not in e for e in events)
    http[role] = {'count': len(events), 'intentional_cache_denials': [e['path'] for e in events if not e['allowed']],
                  'statuses': {str(s): sum(e.get('status') == s for e in events) for s in sorted({e['status'] for e in events})}}
    for p in sorted(folder.glob('*')):
        if p.is_file():
            evidence[str(p.relative_to(REPO))] = {'sha256': r.sha(p), 'bytes': p.stat().st_size}

def native(role, filename, required):
    text = (r.HERE / role / filename).read_text(encoding='utf-8')
    for value in required:
        assert value in text, (filename, value)

native('success', '02-original-model-call.dom.txt', [b.PARSE, b.PDF_SHA,
    'acquisition-call-57ed124b5066bed2f2fb9a4137f607d68ffc83b527a590ef12bf8f1f9b30175c',
    'gemini-3.5-flash-lite', '346'])
native('success', '03-old-skeleton-source.dom.txt', ['paper_version: 1',
    'parse_run_5de840df2a60a2b9d9705d6f92807413', 'skeleton_ad1dc385a70f2dd67e89eb1ebec075cd'])
native('success', '05-collection-progress.dom.txt', [b.COLLECTION, b.GPU, b.QUICK,
    '已尝试 6 次', '已尝试 1 次', '未解析 6', 'Collection / ACTIVE', 'Collection · PAUSED'])
native('identity', '01-paper-ready.dom.txt', ['QUICK_READ · READY', 'PARSE_PDF · SUCCEEDED'])
native('identity', '02-review-history.dom.txt', ['当前文件身份已验证', '停住 2 项相关任务',
    '文件已重新进入审核，原版本保留', '文件身份已批准', '2026年10月14日 15:03:17',
    '仅批准文件技术身份', '第 1 页无法显示', '第 2 页无法显示'])
native('upstream', '02-track-stale.dom.txt', [b.METHOD, *b.CLAIMS,
    'Method · SUPERSEDED', 'Claim · STALE', '需要科学复核', b.PLAN, '执行此计划一次" [disabled]'])
for _, (_, target) in b.ZERO.items():
    native('upstream', f'03-zero-{target}.dom.txt', ['还没有成文版本', f'Zero versions {target}'])
method = r.read(r.HERE / 'upstream/old-method-refusal.json')
assert method['status'] == 'PASS_ACTUAL_CURRENT_CORE_REFUSAL' and method['marker_absent']
zero = r.read(r.HERE / 'upstream/four-zero-refusals.json')
assert zero['status'] == 'PASS_FOUR_REAL_CURRENT_HTTP_REFUSALS' and len(zero['responses']) == 4
zero_events = [r.read(p) for p in (r.HERE / 'upstream').glob('studio-http-*.json')]
actual = [e for e in zero_events if e['zero_version_manuscript']]
assert len(actual) == 4 and {e['zero_version_manuscript'] for e in actual} == set(b.ZERO)
assert all(e['status'] == 422 and e['all110_and_files_exact_after_refusal'] for e in actual)
assert all('/pages/' in p and p.endswith('.png') for v in http.values() for p in v['intentional_cache_denials'])
assert sum(len(v['intentional_cache_denials']) for v in http.values()) == 2

report = '''# G11 当前源码综合验收

原文：真 Collection 运行可追踪；审核复检恢复；上游失效传播、旧方法拒绝运行、零版本不可进 Stage 3 / Publication。

PASS。沿用三份可追踪兼容副本，当前421完整源码清单、独立318后端/93前端产品清单与77构建文件均逐字节保持。这些清单范围不同，不能把318+93当作421。三副本全部110表、schema、非sidecar文件及四个受保护原根精确不变；所有本轮服务按实际身份退出，8875/8877/3000端口空闲。

原 Collection 页面显示四阶段已完成、GPU attempt6与QuickRead attempt1唯一成功、五次旧失败历史、原模型调用346tokens与新parse/PDF原文来源。Collection仍ACTIVE、六引用未解析、原继承Collection仍PAUSED；没有启动worker或重跑模型。旧Skeleton明确属于旧parse/paper-v1，不冒充新解析成果。QuickRead科学卡字段仍null。

身份副本原生复核页面保留原重新审核与批准说明、VERIFIED身份及两项恢复任务；QuickRead在此副本仍READY，与成功副本分开。原两次201操作引用原已封存G11及identity审计，不重放。此次只读边界明确禁止PNG派生缓存写入，所以页面两张图片显示无法显示、两次PNG请求403；这不是新PDF渲染成功，也不当成产品回归。PDF原件SHA/字节和旧原生完整PDF核验历史保持。

原生Track读取SUPERSEDED Method、两个STALE Claim及稿件需科学复核，保留旧批准历史和旧成功Run。旧计划UI因缺完整旧审阅清单而禁用，未声称点击成功；另对当前真实核心run_experiment单次调用得到精确RevisionConflictError，旧marker未创建、无Run/grant增量。

四份稿件各实际打开成文空态“还没有成文版本”。随后四次真实HTTP stage请求分别拒绝WHOLE_PAPER_REVIEW、FINALIZATION_SUBMISSION、REVISION、PUBLICATION，全部422且明确缺successful generated version，每次前后全部110表/文件精确。禁用UI与真实后台拒绝分别留证。

本结论组合原已封存业务执行与本轮当前程序读回/实际拒绝；未假称重做GPU、QuickRead、身份决定、上游批准或成功实验。未执行科学批准、深读、预算调整、投稿或Publication。用户原Studio与8891采集页未操作。G09和统一交付尚待完成；final11_complete/overall118_complete仍false。
'''
r.put(r.HERE / 'g11-audit-receipt.json', {'status': 'PASS_G11_CURRENT421_ORIGINAL_SOFTWARE_DEFINITION',
    'at_utc': datetime.now(timezone.utc).isoformat(), 'source421': receipt['source421'],
    'http': http, 'native_roles': list(r.ROLES), 'full110_schema_and_files_exact': True,
    'all_originals_exact': True, 'actual_current_core_refusals': 1, 'actual_current_http_422': 4,
    'model_gpu_quickread_success_replays': 0, 'all_owned_services_retired': True,
    'final11_complete': False, 'overall118_complete': False, 'evidence': evidence})
with (r.HERE / 'acceptance.md').open('x', encoding='utf-8') as f:
    f.write(report)
progress = r.read(REPO / '.tmp/scholar-all11-g10-current-v3/all11-progress-v3.json')
for item in progress['requirements']:
    assert r.sha(Path(item['original_scoped_report'])) == item['original_scoped_report_sha256']
    if item['id'] == 'G-11':
        item.update(current_composite_complete=True, current_source_files=421,
            current_native_audit={'path': str(r.HERE / 'g11-audit-receipt.json'),
                                  'sha256': r.sha(r.HERE / 'g11-audit-receipt.json')},
            next_actual_check='Original G11 software definition complete under current421; preserve original attempts and decisions without replay.')
progress['current_composite_completed_groups'] = [v['id'] for v in progress['requirements'] if v['current_composite_complete']]
progress['current_composite_remaining_groups'] = ['G-09']
progress['observed_at_utc'] = datetime.now(timezone.utc).isoformat()
progress['next_execution'] = 'Complete G09 fixed source/baseline/comment/change/reply native reads and fresh round4 delivery snapshot, then unified final11 evidence seal with original118 scope retained.'
r.put(r.HERE / 'all11-progress-v4.json', progress)
print('PASS_G11_CURRENT421; CURRENT_INTEGRATED_10_OF_11; G09_REMAINS')
