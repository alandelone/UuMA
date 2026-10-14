from pathlib import Path
import hashlib,json,shutil,sys,time
sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();root=repo/'.tmp/scholar-g04-native-v1'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'));sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
base=read(root/'baseline-all-tables.json');authored=read(root/'authored-v2/all-tables.json');done=read(root/'done-v2/all-tables.json');final=read(root/'reopened-v2/all-tables.json')
assert all(authored[t]==done[t]==final[t] for t in final if t!='studio_sample_candidates')
for phase in ['checked-v2','authored-v2','done-v2','reopened-v2']:assert read(root/phase/'receipt.json')['status'].startswith('PASS_G04_')
calls=[r for r in final['studio_model_calls'] if r not in base['studio_model_calls']]
assert len(calls)==2 and calls[0]['status']=='FAILED' and calls[1]['status']=='VALIDATED'
assert calls[0]['input_sha256']==calls[1]['input_sha256'] and json.loads(calls[1]['contract_json'])['actual_model']=='TEST_FIXTURE_G04_STAGE3_DONE_NATIVE'
proof=root/'proof'
for name in ['Done-old-v4-open-findings.dom.txt','refreshed-Done-v4.dom.txt','reopened-Done-v4.dom.txt']:
    text=(proof/name).read_text(encoding='utf-8')
    assert 'artifact_7477255312e6405988e21c626026e5ae' in text and text.count('button "保留待改"')==5 and 'G04 software review marker' in text
    assert 'Skeleton / Samples' not in text and 'FieldKG / Evidence' not in text
structure=(proof/'authored-structure-before-Done.dom.txt').read_text(encoding='utf-8')
assert 'button "Done"' in structure and 'Skeleton / Samples' in structure and 'FieldKG / Evidence' in structure
prior=read(repo/'.tmp/scholar-g03-seal-v1.json');prior_report=Path(prior['directory']);prior_manifest=read(prior_report/'manifest.json')
assert all(sha(prior_report/p)==h for p,h in prior_manifest['files'].items()) and all(sha(p)==h for p,h in prior_manifest['current_source_sha256'].items())
report=repo/'docs/reviews/scholar-rstv4-2026-09-30/formal-stage3-done-2026-10-12';report.mkdir()
def copy(source,target):
    dest=report/target;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest);assert sha(source)==sha(dest)
for origin,folder in [(root,'evidence/native-v1'),(repo/'.tmp/scholar-g04-startup-v1','evidence/startup-v1')]:
    for p in origin.rglob('*'):
        if p.is_file():copy(p,Path(folder)/p.relative_to(origin))
for p in (repo/'.tmp').glob('scholar-g04-*'):
    if p.is_file() and p.suffix in {'.py','.json','.log'}:copy(p,Path('evidence/helpers')/p.name)
for p in prior_manifest['current_source_sha256']:
    copy(Path(p),Path('source-current')/Path(p).relative_to(repo.parent))
text='''# G04 Stage 3 Done 原始软件实跑验收

2026-10-12。本组原始定义通过，11 组整体验收仍未完成；原始 118 项 / 11 组范围保持。G04：从正式生成稿修改结构，Done 返回旧成文、收起两栏，不生成、不清问题、不推进阶段。

## 实跑结果

同一原稿 A 从活动 v4 的“修改原始结构”进入 Stage 3 结构视图。通过本产品一次作者编辑，将 Beta 段落目的改为 G04 软件测试标记；r13→r14，其余作者文档完整相等，原思想、引用选择、候选/PENDING 状态不变。结构视图确有 Done，左右两栏均展开。

点击 Done 后实际返回 reading，URL left=0/right=0，两栏均消失；仍显示原 v4 的 Beta/Alpha 成文和 PDF artifact_7477255312e6405988e21c626026e5ae。四个原生成任务、四个原成文版本和 20 个原文件 SHA 全部保持，新增 Generate 为 0。工作阶段仍为 WHOLE_PAPER_REVIEW，没有进入定稿、Revision 或 Publication。

检查前置步骤留下了五条 OPEN 问题（四条原规则记录和一条明确的软件模型测试标记）。Done、刷新、返回 Track 后重新打开，五条“保留待改”操作均可见；记录 ID、来源、正文、版本、状态及 resolved_at 完整不变。Done 前后和重新打开后的全部 109 表逐表相等，仅把可重建样本缓存单独列出；没有删除、忽略、解决检查问题。

刷新还核对了检查依据：原成文输入修订为 11，实际模型明确为 TEST_FIXTURE_G04_STAGE3_DONE_NATIVE。当前作者修订 14，旧生成输入 11，真实 stale 状态继续显示。这验证软件工作流程，不代表科学判断有效或获得审批。

## 原失败及前置上下文

初始数据库没有全文检查任务，因此不能用“没有问题可清除”来证明保留问题。通过原浏览器按钮创建实际检查任务；测试服务仅允许一个指定 v4/r11 的 writing_review，其他任务禁止，无远程回退、无数据库造记录分支。

第一轮测试入口把页面数字 [1]/[2] 格式与保存原文的 [@evidence_ID] 格式混淆，实际调用 FAILED/AssertionError，规则结果保留，界面明确提示模型检查未完成。原调用、任务、规则问题、完整输入、错误、DOM 和截图均保存。按同一真实原输入修正为精确的来源标识文本，再通过原浏览器按钮重新检查。第二轮调用 VALIDATED，输入 SHA 与第一轮完全相等，返回一条明确的软件标记。两次检查任务和两次测试调用都保留，没有把第一轮藏掉，也没有降低模型或保留问题的断言。

当前四条 UNRESOLVED_CITATION 规则记录仍为 OPEN；本次仅验证 Done 不清除它们，不把它们当作已解决或科学依据已批准。来源绑定/审批边界留待原 G10/G11 全流程核验。

## 当前状态和范围

- 原 14 次模型记录、15 条讨论、3 个建议决定完整保持。本组显式增加两次软件检查调用（一失败、一验证通过）和两次检查任务；Done 动作新增调用/任务/生成/讨论均为 0。
- A 当前作者 r14、活动 v4、上次生成 r11、Stage 3、未选择候选/PENDING 保持。B 的 r1/Drafting 作者摘要和原 G03 草稿测试数据未改。原 Gemini 拒绝记录完整保留。
- 本轮无需产品修改：现有 Done 经真实输入修改、已有问题和重新打开验证，符合原 G04 定义。当前 15 个前后端源码 SHA 与 G03 封存值一致；没有为证据任务重复运行无关测试或把历史测试算作新验收。
- 前端仍是既有 3008；只对精确身份验证后的测试后台 8881 更换测试入口。新后台身份见 runtime-v2.json。旧临时预览和已关闭 Catalog 未重启，其他工具、用户和科学运行未动。

本组报告不是 11 组全流程完成，也没有批准 UuMA gate 或科学证据。继续原 G06–G11 和全部 11 组串联。新后台只允许本轮已用过的一次软件 review；后续工作不要误发讨论、Generate 或再次检查，应按所需契约核验并更换测试入口。
'''
(report/'acceptance.md').write_text(text,encoding='utf-8')
manifest={'status':'PASS_ORIGINAL_G04_NATIVE_SOFTWARE_SCOPE','original_requirement_count':118,'original_group_count':11,'overall_complete':False,'current_source_sha256':prior_manifest['current_source_sha256'],'files':{str(p.relative_to(report)):sha(p) for p in report.rglob('*') if p.is_file()}}
(report/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');assert all(sha(report/p)==h for p,h in manifest['files'].items())
gate=repo/'stage-gates/04-verification-report.md';raw=gate.read_bytes();previous=gate.read_text(encoding='utf-8');backup=repo/f'.tmp/scholar-g04-gate-prior-{time.time_ns()}.raw.md';backup.write_bytes(raw)
heading='## 2026-10-12 G04 Stage 3 Done 原始软件实跑'
assert heading not in previous
gate.write_text(previous+'\n\n'+heading+'\n\n从活动 v4 修改 Beta 原结构 r13→r14，Done 返回原 v4 并收两栏；五条 OPEN 检查问题完整保留，刷新和重新打开保持；Done 不生成、不增加任务/调用、不推进 Stage 3。两个显式前置软件检查（一失败一验证通过）完整保留。原 20 文件 SHA 与 15 源码 SHA 保持。报告：`docs/reviews/scholar-rstv4-2026-09-30/formal-stage3-done-2026-10-12/acceptance.md`。原始 118 项/11 组不缩减，整体验收和科学审批未完成，gate 未批准。\n',encoding='utf-8')
assert gate.read_text(encoding='utf-8').startswith(previous) and backup.read_bytes()==raw
receipt={'status':manifest['status'],'directory':str(report),'sealed_files':len(manifest['files']),'report_sha256':sha(report/'acceptance.md'),'manifest_sha256':sha(report/'manifest.json'),'overall_complete':False}
(repo/'.tmp/scholar-g04-seal-v1.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps(receipt),flush=True)
