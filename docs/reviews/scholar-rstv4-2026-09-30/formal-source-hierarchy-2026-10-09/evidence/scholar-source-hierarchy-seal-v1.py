import hashlib
import json
import re
import shutil
import sqlite3
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
base = repo / 'docs/reviews/scholar-rstv4-2026-09-30'
parent_folder = base / 'formal-template-mapping-2026-10-09'
parent = json.loads((parent_folder / 'manifest-v2.json').read_text(encoding='utf-8'))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(parent_folder / 'acceptance-v2.md') == parent['report_sha256']
for relative, expected in parent['copied_file_sha256'].items():
    assert sha(parent_folder / relative) == expected, relative
audit = json.loads((repo / '.tmp/scholar-source-hierarchy-audit-v1.json').read_text(encoding='utf-8'))
fixture = json.loads((repo / '.tmp/scholar-source-hierarchy-fixture-v1.json').read_text(encoding='utf-8'))
build = json.loads((repo / '.tmp/scholar-source-hierarchy-build-v2.json').read_text(encoding='utf-8'))
runtime = json.loads((repo / '.tmp/scholar-source-hierarchy-modal-runtime-v2.json').read_text(encoding='utf-8'))
mission = json.loads((repo / 'mission_status.json').read_text(encoding='utf-8'))
requirements_path = base / 'ui-requirements-preservation.md'
pipeline_path = base / 'full-pipeline-and-ui-acceptance.md'
requirements = requirements_path.read_text(encoding='utf-8')
pipeline = pipeline_path.read_text(encoding='utf-8')
gate_path = repo / mission['gate']['current']
gate = gate_path.read_text(encoding='utf-8')
assert mission['stage'] == 'verification' and mission['gate']['status'] == 'pending_review'
assert set(re.findall(r'\b(?:AC|CA|CH|KG|OV|RE|RV|ST|TR|WF)-\d{2}\b', requirements)) == set(parent['requirements'])
assert len(parent['requirements']) == 118 and len(parent['groups']) == 11
folder = base / 'formal-source-hierarchy-2026-10-09'
folder.mkdir(exist_ok=False)
shutil.copytree(repo / '.tmp/scholar-source-hierarchy-before-v1', folder / 'source-before')
for relative, expected in audit['final_source_sha256'].items():
    source = repo.parent / relative
    assert sha(source) == expected
    target = folder / 'source-after' / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
evidence = folder / 'evidence'
evidence.mkdir()
for path in (repo / '.tmp').glob('scholar-source-hierarchy*'):
    if path.is_file() and 'runtime-before' not in path.name:
        shutil.copy2(path, evidence / path.name)
for filename, content in [('requirements-before-this-seal.md', requirements),
                          ('pipeline-before-this-seal.md', pipeline), ('gate-before-this-seal.md', gate)]:
    (folder / filename).write_text(content, encoding='utf-8')
for relative, expected in build['dist_files'].items():
    source = Path(build['root']) / relative
    assert sha(source) == expected
    target = folder / 'production-build' / Path(relative).relative_to('dist')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
with sqlite3.connect(f"file:{Path(fixture['database']).as_posix()}?mode=ro", uri=True) as conn:
    with sqlite3.connect(folder / 'native-final-catalog.db') as output:
        conn.backup(output)
report = '''# 2026-10-09 来源明确层级与原稿保留续批验收

原 118 条要求、G-01 至 G-11 整体验收仍未完成。本批仅补齐并实跑 G-08 的明确来源层级软件链及弹窗可操作性，不批准科学内容、科研节点、生产发布或 gate。

## 修复和来源契约

- 保留 MinerU 内容列表给出的 `text_level` 及页码、bbox、内容索引。根据同一完成解析中的明确层级和块身份建立父子关系；不用标题编号、L1–L4 或同名标题猜关系。
- Catalog 12→13 仅新增 `skeleton_source_outlines`。在新隔离副本内迁移，原运行副本仍为原结构。旧 108 表原记录、原来源上下文与 golden 数据库 SHA 保持；迁移备份和历史保留。
- 新 Skeleton 身份包含来源层级。来源块、阅读顺序、页码或文字不匹配、层级跳跃、缺少父级、篡改 outline/parse 时拒绝发布或新采用。旧平面来源不追加字段、不改摘要或历史。
- 全模板预览显示章节路径和原文页码。部分采用保留所选单元的祖先空章节；相同标题的不同章节使用不同来源身份。章节、段落与 Intent 保留固定来源出处，不复制来源正文到作者思想。
- 在作者子章节处插入，只把新增根章节接到目标所属父级，保留模板内部父子关系。替换仍保留作者原内容到待安置，原内容未安置则阻止生成。
- 原生 1366×607 窗口曾裁切弹窗。最后仅调整弹窗最大高度、滚动与内部列表高度；类型检查、静态检查、隔离构建及修复后原生替换通过。

## 实跑与持久记录

新软件稿件 `manuscript_98c35f5b5557453583cb20df8d52810d`，原作者初始化 r1；新增 7 次实际保存，最终 r8 与 r1 完整文档相同。来源是明确标注的合成软件数据，不是合格学术来源或科学批准。

| 保存版本 | 实际操作和结果 |
|---|---|
| r2 | 仅采用第三层的一项单元，同时创建其完整三级祖先路径 |
| r3 | 刷新后撤销，完整恢复 r1 |
| r4 | 重做，完整恢复 r2 |
| r5 | 在既有子章节目标采用完整 5 章节／10 单元，新增根接到正确父级、内部三级关系保留 |
| r6 | 快速连续两次 UI 撤销合并为一次持久 UNDO，恢复 r1；中间 UI 画面不是独立保存版本 |
| r7 | 修复弹窗后明确确认整篇替换，原作者章节进入待安置；原生 Generate 检查拒绝空思想和待安置内容，未创建任务或模型调用 |
| r8 | 刷新后撤销整篇替换，完整恢复 r1 |

每个保存版本的前后文档、逆向记录、固定来源及采用记录已独立核对。原作者 2 思想、2 选中引用、2 公式、同一 CSV 的 2 关联、原段落组和完整 L2 边／条件保持。CSV 字节和 SHA、原运行副本全部 108 表、旧来源以及 golden DB 字节均保持。新增真实模型调用、生成任务、科学批准均为 0。

## 检查结果和保留失败

针对性 65 项通过；版本契约修正后的最窄检查 24 项通过。完整回归 1,015 项通过、20 条原有警告，23 项流程检查全通过，运行中源码摘要不变。最新完整日志 SHA256 `82e30366c32968fd5c5025f60ec5e43c96aa2744a3aeb07adab2b34aaa7ddb2d`，pytest 424.72 秒；全流程 427.75 秒。

完整回归后唯一产品差异是模板弹窗的两个显示类，原文差异已严格核对；最后类型／静态／diff 检查与构建通过，后台及测试代码保持该完整回归时的字节。最终 build v2 5.132 秒。

失败全部保留：首轮页码读取转换错误（9 失败／56 通过）；新测试误用不存在的物理模型调用表（1 失败／64 通过）；旧 schema12 数值断言（1 失败／1014 通过），先记录执行契约再适配声明版本，字节与历史断言保持；两次裁切弹窗的原生替换未产生操作，不记通过，修复后 r7 才记成功；PowerShell 元数据 GBK 解码失败发生在进程维护之前，显式 UTF-8 后复用成功构建、严格所有权校验；文件清单子命令完成，但会话日志写入冲突，保留错误并改为等运行句柄终止后再启动下一个日志命令。没有修改会话引擎或弱化断言。

## 原 11 组仍待完整验收

| 组 | 当前界限／后续实跑 |
|---|---|
| G-01 | 固定对象各层的完整纵向链与全部交互继续 |
| G-02 | 多来源、完整与部分建议全场景继续 |
| G-03 | 多工作台、离线、草稿、原本地副本及失效恢复继续 |
| G-04 | Done 完整链和所有对象继续 |
| G-05 | 实际学术引用、完整阅读上下文及固定来源继续 |
| G-06 | 完整评论关联链与稳定对象身份继续 |
| G-07 | 四格式原生文件输入尚未通过；既有权限问题和错误 TXT 路径记录保留 |
| G-08 | 明确来源层级软件链已通过；实际合格学术来源层级、原作者内容到任意 Intent 空槽的明确对应、复杂多边论证和完整分层生成仍待验收 |
| G-09 | ZIP/PDF 原生下载按用户要求暂停；其余 Revision 完整链继续 |
| G-10 | 真实七类科学内容、来源质量和真实用户批准继续；软件夹具不代替科学验收 |
| G-11 | Collection→审核→Experiment→生成→Revision→Publication 与失效恢复的完整 118 条逐项验收仍未完成 |

用户说“it's pop out , dont test this download thing first”并手动关闭弹窗。下载保持暂停，不打开下载页／文件弹窗，不改变浏览器或扩展权限。原 12 个 DONE 来源调用不重复；原本地副本、DSPy/Honc/control-guard 工作保持。

最终来源预览留在 Chrome 3 的 tab 1479454355，整篇 INSERT 默认、10 单元待核对，未提交；原稿 r8 保持。原两页 tab1479454207/1479454178 及未提交草稿保留。当前新预览 3005/8878 与原预览 3004/8877 分离。

![最终来源层级预览](evidence/scholar-source-hierarchy-native-handoff-preview-native-v1.png)
'''
(folder / 'acceptance.md').write_text(report, encoding='utf-8')
report_sha = sha(folder / 'acceptance.md')
note = f'\n\n## 2026-10-09 明确来源层级与原生替换续批\n\n明确解析层级／来源位置／部分祖先结构／嵌套目标内部层级已修复，并在新隔离副本实跑 7 次持久操作至 r8，撤销后原作者文档、引用、组、公式、CSV、L2 完整保持。原 108 表／来源摘要／golden 字节保持，schema13 仅在新副本新增一张来源 outline 表。1015 完整测试、23 流程检查通过；修复弹窗后原生整篇替换、待安置生成阻止及刷新撤销通过。真实科学来源与任意 Intent 空槽对应等仍待验收；下载按用户要求暂停。原118／全部11不关闭，verification/pending_review 保持。\n[本批证据]({folder.as_posix()}/acceptance.md) · SHA256 `{report_sha}`。\n'
for path in [requirements_path, pipeline_path, gate_path, repo / 'repomemory/findings.md']:
    with path.open('a', encoding='utf-8') as f:
        f.write(note)
assert requirements_path.read_text(encoding='utf-8').startswith(requirements)
assert pipeline_path.read_text(encoding='utf-8').startswith(pipeline)
assert gate_path.read_text(encoding='utf-8').startswith(gate)
assert set(re.findall(r'\b(?:AC|CA|CH|KG|OV|RE|RV|ST|TR|WF)-\d{2}\b', requirements_path.read_text(encoding='utf-8'))) == set(parent['requirements'])
manifest = {'status': 'SCOPED_SOURCE_HIERARCHY_NATIVE_COMPLETE_OVERALL_INCOMPLETE',
            'overall_complete': False, 'g08_complete': False, 'requirements': parent['requirements'],
            'groups': parent['groups'], 'full_tests_passed': 1015, 'warnings': 20,
            'native_revision': 8, 'native_persisted_operations_added': 7, 'native_models_added': 0,
            'native_jobs_added': 0, 'scientific_approval': False, 'old_runtime_rows_exact': True,
            'legacy_source_contexts_exact': True, 'golden_database_sha256': audit['golden_database_sha256'],
            'schema_version_new_clone': 13, 'new_table_count': 109, 'old_runtime_table_count': 108,
            'mission_stage': mission['stage'], 'gate_status': mission['gate']['status'],
            'user_paused_download_testing': True, 'browser_file_upload_verified': False,
            'browser_zip_pdf_download_verified': False, 'parent_report_sha256': parent['report_sha256'],
            'parent_files_reverified': len(parent['copied_file_sha256']),
            'post_full_frontend_display_only_delta': audit['post_full_delta'],
            'final_source_sha256': audit['final_source_sha256'], 'runtime': runtime,
            'report_file': 'acceptance.md', 'report_sha256': report_sha,
            'copied_file_sha256': {str(p.relative_to(folder)): sha(p) for p in folder.rglob('*') if p.is_file()}}
(folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
for relative, expected in manifest['copied_file_sha256'].items():
    assert sha(folder / relative) == expected
print(json.dumps({'status': manifest['status'], 'report': str(folder / 'acceptance.md'),
                  'report_sha256': report_sha, 'sealed_files': len(manifest['copied_file_sha256']),
                  'parent_files_reverified': len(parent['copied_file_sha256']), 'requirements': 118,
                  'groups': 11, 'stage': mission['stage'], 'gate': mission['gate']['status']}, ensure_ascii=False))
