from pathlib import Path
from datetime import datetime, UTC
import hashlib
import importlib.util
import json
import shutil
import socket
import sys
import zipfile

REPO = Path(__file__).resolve().parents[1]
V9 = REPO / '.tmp/scholar-studio-current-native-restart-v9'
V10 = REPO / '.tmp/scholar-studio-current-native-restart-v10'
REL = REPO / '.tmp/scholar-studio-artifact-relocation-v1'
UI = REPO / '.tmp/scholar-nochange-native-v9'
AUD = REPO / '.tmp/scholar-studio-nochange-audit-v1'
OUT = REPO / 'docs/reviews/scholar-rstv4-2026-09-30/formal-studio-nochange-2026-10-15'
CID = 'comment_7702027e5fd44006a5a11fba9c369462'
A206 = 'comment_8ecd722c5ea041858723009b72fc4cce'
CHECK = 'response_check_8ce98ccc433647feb69bd3aefaf6eb52'
REQUEST = '97b9eddc-fe14-42e9-8ab4-2d859776c884'
MS = 'manuscript_56652adf9d054cb6ab3819efacf3475c'
ROUND = 'review_round_e4845ca796d74594b33b86fb529b4404'
VERSION = 'manuscript_version_de30b95a2d6843059d3c8b420627bf58'


def read(p):
    return json.loads(p.read_text(encoding='utf8'))


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write(p, value):
    with p.open('x', encoding='utf8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def records(state, table):
    t = state['tables'][table]
    return [dict(zip(t['columns'], row)) for row in t['rows']]


def keyed(state, table, field):
    rows = records(state, table)
    values = {r[field]: r for r in rows}
    assert len(values) == len(rows)
    return values


def delta(before, after):
    assert before['schema'] == after['schema']
    assert set(before['tables']) == set(after['tables'])
    return [t for t in before['tables'] if before['tables'][t] != after['tables'][t]]


def exact_other_rows(before, after, table, field, excluded):
    a, b = keyed(before, table, field), keyed(after, table, field)
    assert {k: v for k, v in a.items() if k not in excluded} == {
        k: v for k, v in b.items() if k not in excluded
    }, table
    return a, b


def load_runner():
    spec = importlib.util.spec_from_file_location('nochange_original_guard', REPO / '.tmp/scholar-studio-current-native-restart-v10.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def audit():
    AUD.mkdir(exist_ok=False)
    before = read(V9 / 'before110-all-tables.json')
    imported = read(V9 / 'backend-terminal.json')['copy_final_all_tables']
    assert len(before['tables']) == len(imported['tables']) == 110
    assert delta(before, imported) == ['review_comments', 'studio_comment_response_state']
    old_comments, new_comments = exact_other_rows(before, imported, 'review_comments', 'comment_id', {CID})
    assert len(old_comments) == 210 and len(new_comments) == 211 and CID not in old_comments
    assert new_comments[CID]['review_round_id'] == ROUND
    assert new_comments[CID]['author_decision'] == ''
    assert new_comments[CID]['response_text'].startswith('SOFTWARE_FIXTURE reply:')
    states_a, states_b = exact_other_rows(before, imported, 'studio_comment_response_state', 'comment_id', {CID})
    assert len(states_b) == len(states_a) + 1 and CID not in states_a
    v9_requests = [read(p) for p in sorted(V9.glob('action-*-request.json'))]
    assert len(v9_requests) == 5
    assert sum(r['method'] == 'POST' and r['path'] == '/api/review-rounds/' + ROUND + '/comments' for r in v9_requests) == 1
    assert read(V9 / 'action-004-response.json')['status_code'] == 201
    assert not any(r['path'].endswith('/response-checks') for r in v9_requests)
    assert imported == read(REL / 'before110-all-tables.json')

    relocated = read(REL / 'after110-all-tables.json')
    assert delta(imported, relocated) == ['studio_artifacts']
    a = keyed(imported, 'studio_artifacts', 'artifact_id')
    b = keyed(relocated, 'studio_artifacts', 'artifact_id')
    plan = read(REL / 'exact-relocation-plan.json')
    assert len(a) == len(b) == len(plan) == 25
    assert set(a) == set(b) == {p['artifact_id'] for p in plan}
    root = Path(read(V10 / 'receipt.json')['root']).resolve()
    for p in plan:
        aid = p['artifact_id']
        assert a[aid]['storage_path'] == p['from'] and b[aid]['storage_path'] == p['to']
        assert {k: v for k, v in a[aid].items() if k != 'storage_path'} == {k: v for k, v in b[aid].items() if k != 'storage_path'}
        assert Path(p['to']).resolve().is_relative_to(root)
        assert not Path(p['from']).resolve().is_relative_to(root)
        assert sha(Path(p['from'])) == sha(Path(p['to'])) == p['sha256'] == a[aid]['sha256']
        assert Path(p['from']).stat().st_size == Path(p['to']).stat().st_size == p['size_bytes'] == a[aid]['size_bytes']
    assert relocated == read(V10 / 'before110-all-tables.json')

    final = read(V10 / 'action-002-all-tables.json')
    assert delta(relocated, final) == ['review_comments', 'studio_comment_response_state', 'studio_response_checks']
    comments_a, comments_b = exact_other_rows(relocated, final, 'review_comments', 'comment_id', {CID})
    assert len(comments_a) == len(comments_b) == 211
    assert comments_b[A206] == old_comments[A206]
    state_a, state_b = exact_other_rows(relocated, final, 'studio_comment_response_state', 'comment_id', {CID})
    check_a, check_b = exact_other_rows(relocated, final, 'studio_response_checks', 'check_id', {CHECK})
    assert CHECK not in check_a and len(check_a) == 2 and len(check_b) == 3
    assert len([v for v in check_b.values() if v['comment_id'] == A206]) == 2
    assert len(records(before, 'studio_change_link_events')) == 4
    saved = check_b[CHECK]
    req = read(V10 / 'action-002-request.json')
    payload = json.loads(req['body_utf8'])
    resp = read(V10 / 'action-002-response.json')
    assert resp['status_code'] == 200 and resp['body']['idempotent_replay'] is False
    assert req['method'] == 'POST' and req['path'] == f'/api/manuscripts/{MS}/comments/{CID}/response-checks'
    assert saved['request_id'] == payload['request_id'] == REQUEST
    assert saved['outcome'] == payload['outcome'] == 'EXPLAINED_NO_CHANGE'
    assert payload['claims'] == [] and payload['acknowledged_all_assertions'] is True
    assert saved['generated_version_id'] == VERSION
    assert saved['context_sha256'] == payload['context_sha256']
    assert json.loads(saved['request_json'])['claims'] == []
    ctx = json.loads(saved['context_json'])
    assert ctx['baseline_version_number'] == 5
    assert ctx['baseline_to_target_diff'] == ctx['baseline_to_target_display_diff'] == ''
    assert ctx['automatic_response_approval'] is False
    returned = resp['body']['comment']
    assert returned['status'] == 'RESOLVED'
    assert returned['response_verification']['status'] == 'CURRENT'
    assert returned['response_verification']['scientific_acceptance'] is False
    assert returned['response_verification']['check_id'] == CHECK
    assert returned['author_decision'].startswith('SOFTWARE_FIXTURE decision:')
    assert returned['response_text'] == new_comments[CID]['response_text']
    assert comments_b[CID]['status'] == 'RESOLVED'
    v10_requests = [read(p) for p in sorted(V10.glob('action-*-request.json'))]
    assert len(v10_requests) >= 2
    checks = [r for r in v10_requests if r['path'].endswith('/response-checks')]
    assert len(checks) == 1 and checks[0] == req
    doc = next(r for r in records(final, 'studio_documents') if r['manuscript_id'] == MS)
    manuscript = next(r for r in records(final, 'manuscripts') if r['manuscript_id'] == MS)
    assert doc['revision'] == doc['last_generated_revision'] == 62
    assert doc['active_generated_version_id'] == VERSION and manuscript['revision'] == 6

    ui = read(UI / 'native-ui-log.json')
    assert len(ui) >= 18
    ui = ui[:18]
    assert ui[17]['label'] == 'a211-saved-check-history-read-only'
    confirm = '作者确认并保存核对记录'
    for step, ack, disabled in [(10, 0, True), (11, 1, True), (14, 0, True), (15, 1, False)]:
        state = ui[step - 1]['state']
        lines = state.splitlines()
        button = next(x for x in lines if 'button' in x and confirm in x)
        assert ('(disabled)' in button) is disabled
        checkbox = next(x for x in lines if 'checkbox Description:' in x)
        assert f'Value: {ack}' in checkbox
    assert 'original generated artifact is unavailable' in ui[6]['state']
    assert '作者确认不修改及理由' in ui[17]['state']
    write(AUD / 'native-ui-log-first18.json', ui)

    runner = load_runner()
    receipt = read(V10 / 'receipt.json')
    runner.guard(receipt)
    assert len(receipt['backend_source_vector']) == 311
    assert len(receipt['frontend_product_vector']) == 91 and len(receipt['frontend_dist_vector']) == 76
    original = read(REPO / '.tmp/scholar-studio-current-native-v2/original-all-tables.json')
    assert len(original['tables']) == 109
    assert len(receipt['protected_external_artifacts']) == 25
    old_files, relocated_files = read(REL / 'before-all-files.json'), read(REL / 'after-all-files.json')
    non_db = lambda d: {k: v for k, v in d.items() if not k.startswith('data/catalog.db')}
    assert all(relocated_files[k] == v for k, v in non_db(old_files).items())
    declared = {Path(p['to']).relative_to(root).as_posix(): p['sha256'] for p in plan}
    assert {k: v for k, v in relocated_files.items() if k not in old_files} == {k: v for k, v in declared.items() if k not in old_files}
    assert non_db(read(V10 / 'before110-all-files.json')) == non_db(relocated_files)
    current_files = runner.filemap(root)
    assert non_db(current_files) == non_db(relocated_files)
    regression = read(REPO / '.tmp/scholar-rv-prompt-full-v1/receipt.json')
    assert regression['status'] == 'PASS' and '1130 passed, 20 warnings in 501.61s' in regression['summary']
    report = {
        'status': 'PASS_A211_NATIVE_EXPLAINED_NO_CHANGE_BOUNDED_AUDIT_INTERIM',
        'observed_at_utc': datetime.now(UTC).isoformat(),
        'comment_id': CID, 'request_id': REQUEST, 'check_id': CHECK,
        'native_ui_observations': 18,
        'v9_changed_tables': delta(before, imported), 'old210_comments_exact': True,
        'v9_single_import201': True, 'v9_response_check_submissions': 0,
        'relocation_changed_table': 'studio_artifacts', 'relocation_only_field': 'storage_path',
        'relocation_paths': 25, 'relocation_original_and_copied_bytes_exact': True,
        'relocation_other109_tables_exact': True, 'relocation_no_product_guard_bypass': True,
        'v10_changed_tables_at_check': delta(relocated, final), 'v10_other107_tables_exact': True,
        'a206_original_comment_response_state_two_checks_four_change_link_events_exact': True,
        'single_response_check_post200_idempotent_replay_false': True,
        'outcome': 'EXPLAINED_NO_CHANGE', 'claims': [], 'status_current': True,
        'scientific_acceptance': False, 'author_revision': 62, 'workflow_revision': 6,
        'generated_version_number': 5, 'generated_version_id': VERSION,
        'round_count_unchanged': len(records(final, 'review_rounds')),
        'empty_reason_even_ack_disabled_native': True,
        'reason_without_ack_disabled_native': True, 'reason_plus_ack_enabled_native': True,
        'original_unavailable_failure_preserved': True,
        'source311_frontend91_dist76_original109_tables_all_original_files_external25_exact': True,
        'new_generated_output': False, 'new_model_gpu_worker_execution': False,
        'prior1130_pass20_warnings_retained_not_rerun': True,
        'terminal_retirement_audit_pending': True,
        'overall118_complete': False, 'final_all11_integrated_complete': False,
    }
    inputs = [V9 / 'before110-all-tables.json', V9 / 'backend-terminal.json',
              REL / 'before110-all-tables.json', REL / 'after110-all-tables.json',
              REL / 'exact-relocation-plan.json', REL / 'receipt.json',
              V10 / 'before110-all-tables.json', V10 / 'action-002-all-tables.json',
              V10 / 'action-002-request.json', V10 / 'action-002-response.json',
              AUD / 'native-ui-log-first18.json', REPO / '.tmp/scholar-rv-prompt-full-v1/receipt.json']
    report['input_sha256'] = {str(p.relative_to(REPO)).replace('\\', '/'): sha(p) for p in inputs}
    write(AUD / 'audit-interim.json', report)
    write(AUD / 'packaging-plan.json', {
        'destination': str(OUT), 'seal_after_v10_owned_retirement': True,
        'scope': 'A211 native no-change and separately declared 25-path fixture relocation only',
        'copy': ['audit', 'native first18 log and all screenshots including failure',
                 'v9 requests/responses/retirement', 'v10 requests/responses/retirement',
                 'relocation full plan/receipts/filemaps and original DB backup',
                 'source311/frontend91/dist76 original protection vectors',
                 'prior retained regression receipt', 'all110 exact checkpoint ZIP with member hashes',
                 'audit and execution-context helper source'],
        'payload_manifest': 'Every report payload SHA-256, excluding manifest itself; manifest SHA in external seal receipt',
        'no_old_seal_edits': True, 'no_mission_gate_matrix_session_lifecycle_actions': True,
    })
    print(json.dumps(report, ensure_ascii=True))


def seal():
    import psutil

    interim = read(AUD / 'audit-interim.json')
    assert interim['status'] == 'PASS_A211_NATIVE_EXPLAINED_NO_CHANGE_BOUNDED_AUDIT_INTERIM'
    for name, expected in interim['input_sha256'].items():
        assert sha(REPO / name) == expected, name
    terminal = read(V10 / 'backend-terminal.json')
    assert terminal['server_stopped'] is True and terminal['originals_exact'] is True
    assert terminal['models_allowed'] == terminal['workers_started'] == 0
    assert read(V10 / 'owned-stop-terminal.json')['status'] == 'EXACT_OWNED_FRONTEND_AND_BACKEND_STOPPED_PORTS_FREE'
    owner = read(V10 / 'ownership.json')
    for saved in [owner['backend'], owner['frontend'], owner['backend_launcher'], *owner['frontend_windows_console_children']]:
        try:
            process = psutil.Process(saved['pid'])
        except psutil.NoSuchProcess:
            continue
        assert process.create_time() != saved['create_time'], 'Owned process remains alive'
    for port in owner['ports']:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', port))
    runner = load_runner()
    receipt = read(V10 / 'receipt.json')
    runner.guard(receipt)
    root = Path(receipt['root'])
    final = terminal['copy_final_all_tables']
    assert runner.snap(root / 'data/catalog.db') == final
    latest_checkpoint = sorted(V10.glob('action-*-all-tables.json'))[-1]
    assert read(latest_checkpoint) == final
    nochange = read(V10 / 'action-002-all-tables.json')
    later_delta = delta(nochange, final)
    # If other authorized work followed, bound this report to the original A211 checkpoint.
    for table, field in [('review_comments', 'comment_id'), ('studio_comment_response_state', 'comment_id')]:
        assert keyed(nochange, table, field)[CID] == keyed(final, table, field)[CID]
    assert keyed(nochange, 'studio_response_checks', 'check_id')[CHECK] == keyed(final, 'studio_response_checks', 'check_id')[CHECK]
    no_db = lambda d: {k: v for k, v in d.items() if not k.startswith('data/catalog.db')}
    baseline_files = read(V10 / 'before110-all-files.json')
    current_files = runner.filemap(root)
    file_delta = sorted(k for k in set(current_files) | set(baseline_files) if no_db(current_files).get(k) != no_db(baseline_files).get(k))
    if later_delta:
        assert not any(t in later_delta for t in ['review_comments', 'studio_comment_response_state', 'studio_response_checks']), 'A211 terminal needs a separate later-mutation audit'
    else:
        assert not file_delta
    terminal_audit = {
        'status': 'PASS_A211_TERMINAL_RETAINED_OWNED_IDENTITIES_RETIRED',
        'observed_at_utc': datetime.now(UTC).isoformat(),
        'owned_v10_identities_absent': True, 'ports_free': owner['ports'],
        'root_retained': str(root), 'all110_terminal_exact_latest_action': latest_checkpoint.name,
        'a211_comment_state_and_check_exact_saved_result': True,
        'post_nochange_other_changed_tables': later_delta,
        'post_nochange_non_catalog_file_differences': file_delta,
        'later_work_outside_this_bounded_report': bool(later_delta or file_delta),
        'original109_source311_frontend91_dist76_external25_exact': True,
        'model_gpu_generation_workers_executed_by_this_studio_preview': False,
        'overall118_complete': False, 'final_all11_integrated_complete': False,
    }
    write(AUD / 'terminal-audit.json', terminal_audit)
    OUT.mkdir(exist_ok=False)

    def copy(source, name):
        dest = OUT / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        assert sha(source) == sha(dest)

    for p in sorted(AUD.iterdir()):
        if p.is_file():
            copy(p, 'audit/' + p.name)
    for p in sorted(UI.iterdir()):
        if p.is_file() and p.name != 'native-ui-log.json':
            copy(p, 'native/' + p.name)
    copy(AUD / 'native-ui-log-first18.json', 'native/native-ui-log.json')
    copy(UI / 'native-ui-log.json', 'native/full-observed-ui-log.json')
    for directory, prefix in [(V9, 'v9'), (V10, 'v10')]:
        for p in sorted(directory.iterdir()):
            if p.is_file() and not p.name.endswith('all-tables.json') and p.name != 'backend-terminal.json':
                # Later work is preserved, but is expressly outside the A211 acceptance claim.
                copy(p, prefix + '/' + p.name)
    for p in sorted(REL.iterdir()):
        if p.is_file() and not p.name.endswith('all-tables.json'):
            copy(p, 'relocation/' + p.name)
    copy(REPO / '.tmp/scholar-rv-prompt-full-v1/receipt.json', 'retained-regression/receipt.json')
    for name in ['scholar-studio-nochange-audit-v1.py', 'scholar-studio-artifact-relocate-v1.py', 'scholar-studio-current-native-restart-v9.py', 'scholar-studio-current-native-restart-v9-stop-owned.py', 'scholar-studio-current-native-restart-v10.py', 'scholar-studio-current-native-restart-v10-stop-owned.py']:
        copy(REPO / '.tmp' / name, 'audit-tools/' + name)
    checkpoints = {
        'v9-before-import.json': V9 / 'before110-all-tables.json',
        'v9-import201.json': V9 / 'action-004-all-tables.json',
        'v9-reply-save200.json': V9 / 'action-005-all-tables.json',
        'v9-terminal.json': V9 / 'backend-terminal.json',
        'relocation-before.json': REL / 'before110-all-tables.json',
        'relocation-after.json': REL / 'after110-all-tables.json',
        'v10-before.json': V10 / 'before110-all-tables.json',
        'v10-reason-save200.json': V10 / 'action-001-all-tables.json',
        'v10-single-check200.json': V10 / 'action-002-all-tables.json',
        'v10-terminal.json': V10 / 'backend-terminal.json',
    }
    for p in sorted(V10.glob('action-*-all-tables.json')):
        if p.name not in ['action-001-all-tables.json', 'action-002-all-tables.json']:
            checkpoints['later-outside-a211/' + p.name] = p
    members = {name: sha(p) for name, p in checkpoints.items()}
    with zipfile.ZipFile(OUT / 'all110-checkpoints.zip', 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for name, p in checkpoints.items():
            z.write(p, name)
    with zipfile.ZipFile(OUT / 'all110-checkpoints.zip') as z:
        assert set(z.namelist()) == set(members)
        for name, expected in members.items():
            h = hashlib.sha256()
            with z.open(name) as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b''):
                    h.update(chunk)
            assert h.hexdigest() == expected, name
    write(OUT / 'checkpoint-member-sha256.json', members)
    text = '''# A211 原生“不修改并说明理由”验收

本报告通过的是 RE-11 的明确不修改分支，以及 RE-13 中“回复、理由、完整声明与固定版本绑定”的有限分支。原始 118 项及同源 11 组整体验收仍未完成。此处为明确标注 SOFTWARE_FIXTURE 的软件验收，不代表科学内容获批、外部审稿通过、真实投稿或项目 gate 审批。

## 实际原生操作与结果

官方内置浏览器在同一份当前前端与后端上完成 18 次观察。选择既有第三轮及固定生成 v5，预览并仅导入一条意见 A211，服务返回 201；保存明确表示保留原稿的回复，先将理由留空。选择“不修改”时确认按钮不可用；即使勾选已检查完整回复，空理由仍使确认按钮不可用。随后保存明确的不修改理由，再次打开核对页，有理由但未勾选完整回复声明时仍不可确认；勾选后才可确认。

作者确认只提交一次。实际 POST /response-checks 返回 200，idempotent_replay=false，request_id 为 97b9eddc-fe14-42e9-8ab4-2d859776c884，check_id 为 response_check_8ce98ccc433647feb69bd3aefaf6eb52。结果为 EXPLAINED_NO_CHANGE，claims 为空数组，完整回复声明为 true。服务将 A211 标为 RESOLVED，核对状态 CURRENT，并明确 scientific_acceptance=false。随后真实打开 A211 核对历史，看到同一条保存记录、完整原理由与原回复，没有再次提交。截图及完整原生观察保留在 native。

本次没有声称已执行未发生的正文修改。审计确认作者结构 revision 62、工作流 revision 6、当前生成 v5、既有 3 个审稿轮次均保持原值；第三轮基准与目标同为 v5，保存上下文中的两种版本差异文本均为空。

## 先前失败及执行上下文修复

首次打开核对页实际失败，提示 The original generated artifact is unavailable，原生观察及截图完整保留。原因是验收副本中 25 个 studio_artifacts.storage_path 仍指向原始目录外部，原始产物的大小及 SHA 正确，但产品的目录归属检查正确拒绝了它们。

先精确停止上一轮自有预览进程，备份完整数据库并冻结 110 表与全部文件摘要。然后把这 25 份原始字节放到本次自有副本的对应 generated 目录，仅更新副本 studio_artifacts 中的 25 个 storage_path 单元格。逐一验证原文件与副本文件的大小及 SHA 一致，所有产物 ID、hash、size、时间及其他字段精确保持，另外 109 表精确一致。原始目录与原数据库保持不变。没有修改产品代码、测试、目录边界断言或产物校验，没有重新生成论文，也没有把原始目录设为产品存储根来绕过检查。修复后使用同一副本及同一既有构建重新启动，核对页实际读出原 v5。

## 数据保护和测试范围

- v9 导入并保存回复后，只有 review_comments 和 studio_comment_response_state 两表新增 A211 对应内容。原 210 条意见逐字段精确保持。
- 路径修复是独立声明的 25 路径元数据变化，不能混同为原生业务操作或产品修复。
- v10 保存理由并提交核对后，只有 A211 意见、对应 response_state 及单个新 studio_response_checks 记录变化，另外 107 表精确保持。A206 原意见、原状态、两条核对历史以及四条关联事件均精确保持。
- 当前 311 份后端源码、91 份前端产品文件、76 份既有构建文件、原始数据库 109 表及全部原始文件、25 个外部原始产物再次核对通过。本 Studio 预览拒绝模型调用，未运行生成、GPU、模型或 worker。
- 保留同源既有回归结果：1130 passed、20 warnings、501.61 秒。本次没有再次运行该套回归，也没有把回归通过算作最终 11 组原生串通。

## 退出与证据封印

退出时精确验证本轮所记录的后端、前端、启动器及控制台子进程身份均已消失，端口可再次绑定，自有目录保留。退出后的完整 110 表与最后实际操作快照一致，A211 的意见、状态与该核对记录仍精确保持。退出审计如列出 A211 之后的其他表变化，则属于后续单独验收，不在本报告完成范围内。

audit 保存逐项断言及证据输入摘要；native 保存 18 次真实观察、正负分支截图及原始失败；v9/v10 保存实际请求、响应、源产物保护向量和退出凭证；relocation 保存完整路径计划、前后文件摘要和修复前原数据库备份；all110-checkpoints.zip 保存完整各阶段 110 表，成员 SHA 逐一复算；retained-regression 保存原回归凭证；audit-tools 保存审计和启动/退出上下文工具。manifest 为每个证据载荷给出 SHA-256。旧封印报告、matrix、mission 和 gate 均未修改。

仍需继续完成其余复杂回复归因、固定版本与提交状态组合、后续交付质量及最终同源 11 组完整串通。本报告不把这一条软件分支扩大为这些要求已完成。
'''
    (OUT / 'acceptance.md').write_text(text, encoding='utf8')
    manifest = {p.relative_to(OUT).as_posix(): sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()}
    write(OUT / 'manifest.json', manifest)
    assert all(sha(OUT / name) == expected for name, expected in manifest.items())
    seal_receipt = {
        'status': 'PASS_FORMAL_A211_NATIVE_NO_CHANGE_WITH_DECLARED_FIXTURE_RELOCATION_SEALED',
        'observed_at_utc': datetime.now(UTC).isoformat(),
        'report': str(OUT / 'acceptance.md'), 'report_sha256': sha(OUT / 'acceptance.md'),
        'manifest': str(OUT / 'manifest.json'), 'manifest_sha256': sha(OUT / 'manifest.json'),
        'payloads': len(manifest), 'check_id': CHECK, 'native_observations': 18,
        'single_check_post200': True, 'claims': [], 'scientific_acceptance': False,
        'all118_complete': False, 'final_all11_integrated_complete': False,
        'post_nochange_other_changes_outside_this_report': later_delta,
    }
    write(REPO / '.tmp/scholar-studio-nochange-seal-v1.json', seal_receipt)
    print(json.dumps(seal_receipt, ensure_ascii=True))


if __name__ == '__main__':
    {'audit': audit, 'seal': seal}[sys.argv[1]]()
