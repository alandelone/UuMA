from pathlib import Path
import hashlib, json, shutil, sys, time
sys.stdout.reconfigure(encoding='utf-8')
repo = Path.cwd(); evidence = repo / '.tmp/scholar-g03-native-v1'
read = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
audit = read(evidence / 'final-audit.json')
assert audit['status'] == 'PASS_ORIGINAL_G03_SOFTWARE_NATIVE_ACCEPTANCE' and not audit['overall_11_groups_complete']
report = repo / 'docs/reviews/scholar-rstv4-2026-09-30/formal-view-restore-offline-2026-10-12'
report.mkdir()
def copy(source, target):
    target = report / target; target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    assert sha(source) == sha(target)
for origin, folder in [(evidence, 'evidence/native-v1'),(repo / '.tmp/scholar-g03-startup-v1', 'evidence/startup-v1')]:
    for p in origin.rglob('*'):
        if p.is_file(): copy(p, Path(folder) / p.relative_to(origin))
for p in (repo / '.tmp').glob('scholar-g03-*'):
    if p.is_file() and p.suffix in {'.py','.json','.log'}: copy(p, Path('evidence/helpers-and-checks') / p.name)
for source in audit['source_sha256']:
    p = Path(source)
    copy(p, Path('source-current') / p.relative_to(repo.parent))
assert all(sha(p) == h for p, h in audit['source_sha256'].items())
text = '''# G03 离开保护与视图恢复：原始软件验收

日期：2026-10-12。结果：本组原始软件路径通过；原始 118 项 / 11 组范围保留，整体验收仍未完成。没有批准 UuMA verification gate，也没有科学证据批准或模型能力结论。

## 修复与真实失败

1. 刷新前定位原 v3 Alpha，刷新后却显示活动 v4，原段落高亮消失。保存所看的生成版本及历史消息/来源索引，重新向服务器核对原历史来源；历史版本不可用时明确保留位置与草稿，不以新版本代替。
2. 离开 A 后 URL 的 view/object/folds/panels 留在 Track 页，新建 B 误继承 A 的成文视图和无效对象。普通打开、新建及返回 Track 清除这些稿件参数，恢复每篇自己的保存状态；初始直接历史链接仍按原来源读取。
3. 第一修正版保住 v3 与高亮，但滚动仍从 807 变为 750。恢复滚动须等待成文、原来源及讨论历史载入，并在自动恢复时避免再次居中定位。实际点击“定位原对象”仍可定位。加载原成文期间显示读取提示。

所有失败的原 DOM、截图、几何数据均保留；没有改低断言、生成新成文、重复发送讨论或丢弃原调用记录。

## 逐项实跑

| 原始 G03 内容 | 浏览器实跑与证据 | 结果 |
| --- | --- | --- |
| 返回稿件恢复对象、成文原版本与选区 | Chrome 原页面重新载入 v3 Alpha；PDF 指向 artifact_4012958fd937410ea0620eca7bd11c73，原 Alpha 高亮与原讨论只读选区保持 | 通过 |
| 滚动、折叠、面板和偏好 | 成文刷新前后：pageHeight 1779、viewport 807、scrollY 807 完全一致；结构刷新前后：pageHeight 1715、viewport 807、scrollY 807 完全一致。A 的 Beta 折叠、选中 Beta、左关右开、直排保持 | 通过 |
| 不同稿件草稿与偏好独立 | A↔Track↔B：A 的 α 问题/annotation、原 v3 和直排保留；B 的 β 问题/annotation、Introduction 折叠及横排保留，均未发送 | 通过 |
| 待同步／断线时换区保留草稿 | 核验 PID/父 PID/命令/创建时间后，仅停本测试端口 8881 服务。B 摘要保存实际 Failed to fetch；返回时显示离开保护，“留在此页”保留全文，“保留本地副本并返回”成功返回离线 Track | 通过 |
| 重连后恢复作者草稿 | 同一服务重启，先打开 A 核对 α 未混入 β，再打开 B。服务器仍是原 r0，安全恢复本地副本并自动保存为 r1；刷新后摘要与 β 讨论草稿保持。只有这笔作者保存，首次保存使 B 从 Planning 进入 Drafting | 通过 |
| 总览手动更新不展开全部 | 对同一测试数据库启动只读 Catalog 页面；折叠 Writing Track 和 f1，点击原“更新状态”。行 ID、hidden/expanded 状态保持；稳定的再次更新前后 scrollY 均为 0。服务与临时页验收后已关闭 | 通过 |

前一次总览采样在折叠后立即读到 scrollY 29、更新后读到 0；这份记录照常保留，不将它作为滚动精确通过证据。稳定页面重新实跑后行状态和 scrollY 一致。导航到顶部的“返回 Track”会实际改变页滚动，本报告没有把导航后的 0 冒充保留原 807。

## 数据与校验

- 所有 109 表已只读比对；原应用记录逐行保持，另明确列出 SQLite 计数器与可重建样本缓存。原 A 文档完整 JSON、r13、活动 v4、Stage 3、旧生成 r11、未选择来源候选/PENDING 状态保持。
- 原 14 次模型记录、15 条讨论、3 个建议决定、4 次生成及 20 份成文材料完整保持；20 个文件逐一 SHA 校验。新模型调用及新讨论消息均为 0。原 Gemini 拒绝记录未改动。
- B 是通过本产品按钮创建的真实测试稿件。只有一笔作者操作：摘要从空串到 G03 软件测试文本，其余文档字段完整相等；来源、科学审批、原稿件和原建议决定未改。
- 类型检查、规范检查、3 项恢复/导航边界契约、7 项文件交付契约及差异格式检查通过；隔离生产构建通过，源工作区及原 dist 未被构建替换。后端源码未改，保留此前 1067 项后台测试结果；本次没有把它算作重新实跑或 11 组整体验收。
- 第一轮检查发现新加载提示需用语义 output 元素，修正后通过；保留失败日志。总览服务实际启动成功后，审计脚本把 PowerShell 单个 PID 误当数组；核对同一完整进程链后登记，没有重复启动或宽泛结束进程。
- 补 B 最终截图时，旧 PLANNING 按钮名未匹配；读取实际 DRAFTING 按钮后打开，未重复建稿或保存。原撤销栈不能与重连前服务器 r0 文档核对时，产品保留原栈并显示提示；没有把这项视为撤销专项验收。

## 可继续状态与剩余范围

当前仅保留必要 Studio 前端 3008 和重连后台 8881；旧预览 3000/3004/3005/3006/3007 未复活，未删除临时目录或停止其他工具/用户任务。Chrome 3 原标签停在 A 的原 v3 Alpha，待继续验收。进程身份以本报告运行记录为证，后续结束前须重新核验。

G01/G02 原 Studio 软件定义、G03 本组原始软件路径、G05 数字引用路径已有封存；G04、G06–G11 及全部 11 组串联仍待完成。下一步是实际 Stage 3 Done：保留原成文、收起面板、保留检查结果，不隐式 Generate 或跨审批推进。所有科学材料与共享完整 handoff 原样保留。
'''
(report / 'acceptance.md').write_text(text, encoding='utf-8')
manifest = {'status':audit['status'],'original_requirement_count':118,'original_group_count':11,'overall_complete':False,'current_source_sha256':audit['source_sha256'],'files':{str(p.relative_to(report)):sha(p) for p in report.rglob('*') if p.is_file()}}
(report / 'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
assert all(sha(report / p) == h for p,h in manifest['files'].items())
gate = repo / 'stage-gates/04-verification-report.md'
previous_gate = gate.read_text(encoding='utf-8'); raw = gate.read_bytes()
backup = repo / f'.tmp/scholar-g03-gate-prior-{time.time_ns()}.raw.md'; backup.write_bytes(raw)
note = '\n\n## 2026-10-12 G03 原始软件路径逐项实跑\n\nG03 刷新原版本/对象/滚动、A/B 草稿与偏好、真实断线离开及重连、本机总览手动更新折叠已通过。原 A r13、14 次模型记录、15 条讨论、3 项决定及 20 文件保持；B 仅一笔作者摘要保存 r0→r1，未新增模型调用。完整报告：`docs/reviews/scholar-rstv4-2026-09-30/formal-view-restore-offline-2026-10-12/acceptance.md`。原始 118 项/11 组与科学审阅边界保持，整体验收未完成，gate 未批准；继续实际 G04 后剩余 G06–G11 和完整 11 组串联。\n'
assert '## 2026-10-12 G03 原始软件路径逐项实跑' not in previous_gate
gate.write_text(previous_gate + note, encoding='utf-8')
assert gate.read_text(encoding='utf-8').startswith(previous_gate) and backup.read_bytes() == raw
receipt = {'status':'PASS_SEALED_ORIGINAL_G03','directory':str(report),'sealed_files':len(manifest['files']),'report_sha256':sha(report / 'acceptance.md'),'manifest_sha256':sha(report / 'manifest.json'),'overall_complete':False}
(repo / '.tmp/scholar-g03-seal-v1.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps(receipt),flush=True)
