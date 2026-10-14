from pathlib import Path
import copy,hashlib,json,shutil,sys,time
sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();root=repo/'.tmp/scholar-g06-native-v1'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'));sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
base=read(root/'baseline-all-tables.json');imported=read(root/'imported/all-tables.json');final=read(root/'returned-A-final/all-tables.json')
a='manuscript_56652adf9d054cb6ab3819efacf3475c';b='manuscript_bea23f3050174ed1a0df075a32c25e13'
numbers={json.loads(r['import_metadata_json'])['comment_number']:r['comment_id'] for r in imported['review_comments']}
assert numbers=={1:'comment_f7969d2589c14c6a9e3d1c923bd1b381',2:'comment_49f64aa1ab3f4bdca2c74fd0aa84c8a1'}
purposes=['G06 edit 1: linked to A01 and A02; keep original thought and citations.','G06 edit 2: linked only to A02 after removing A01; keep original thought and citations.','G06 edit 3: ordinary edit after ending all comment context; keep original thought and citations.','G06 edit 4: archived A01 is excluded, retain only A02 context; keep original thought and citations.']
changes=[r for r in final['studio_changes'] if r not in base['studio_changes']];a_changes=[r for r in changes if r['manuscript_id']==a];b_changes=[r for r in changes if r['manuscript_id']==b]
assert len(changes)==5 and len(a_changes)==4 and len(b_changes)==1
expected_links=[{numbers[1],numbers[2]},{numbers[2]},set(),{numbers[2]}]
previous=json.loads(next(r for r in base['studio_documents'] if r['manuscript_id']==a)['document_json'])
for i,(change,purpose,links) in enumerate(zip(a_changes,purposes,expected_links)):
    assert json.loads(change['before_json'])==previous
    expected=copy.deepcopy(previous);expected['sections'][0]['paragraphs'][0]['purpose']=purpose
    assert json.loads(change['after_json'])==expected;previous=expected
    linked={r['comment_id'] for r in final['comment_changes'] if r['change_id']==change['change_id']}
    assert linked==links
    operation=next(r for r in final['studio_operations'] if r['operation_id']==change['operation_id'])
    assert operation['base_revision']==14+i and operation['resulting_revision']==15+i
    state=next(r for r in final['studio_change_link_state'] if r['change_id']==change['change_id'])
    assert set(json.loads(state['initial_comment_ids_json']))==links
assert next(r for r in final['studio_documents'] if r['manuscript_id']==a)['revision']==18
assert json.loads(next(r for r in final['studio_documents'] if r['manuscript_id']==a)['document_json'])==previous
assert not any(r['change_id']==b_changes[0]['change_id'] for r in final['comment_changes'])
b_before=json.loads(next(r for r in base['studio_documents'] if r['manuscript_id']==b)['document_json'])
assert json.loads(b_changes[0]['before_json'])==b_before
b_before['abstract']+=' G06 cross-manuscript edit has no A01/A02 context.'
assert json.loads(b_changes[0]['after_json'])==b_before
assert next(r for r in final['studio_documents'] if r['manuscript_id']==b)['revision']==2
assert len(final['review_rounds'])==1 and final['review_rounds']==imported['review_rounds']
assert final['studio_review_round_baselines']==imported['studio_review_round_baselines']
for phase in ['both-linked','only-A02','ended-context','archived-A01','edit-after-archive','restored-A01','cross-manuscript','returned-A-final']:
    tables=read(root/phase/'all-tables.json')
    for table in ['studio_model_calls','studio_chat_messages','research_discussion_messages','studio_suggestion_decisions','studio_jobs','manuscript_versions','studio_artifacts','studio_findings']:
        assert tables[table]==base[table],(phase,table)
    for old in imported['review_comments']:
        current=next(r for r in tables['review_comments'] if r['comment_id']==old['comment_id'])
        assert all(current[k]==old[k] for k in old if k not in {'archived_at','updated_at'})
archived=read(root/'archived-A01/all-tables.json')['review_comments'];assert archived[0]['archived_at'] and archived[1]['archived_at'] is None
assert all(r['archived_at'] is None for r in final['review_comments'])
assert len(final['comment_changes'])==4 and len(final['studio_model_calls'])==16 and len(final['studio_artifacts'])==20
assert all(sha(r['storage_path'])==r['sha256'] for r in final['studio_artifacts'])
proof=root/'proof'
requirements={
'both-context-saved.dom.txt':['解除关联 A01','解除关联 A02','结束本次关联'],
'only-A02-after-removing-A01.dom.txt':['解除关联 A02'],
'ended-context-ordinary-edit.dom.txt':['普通编辑','后续修改不关联审稿意见'],
'archived-A01-active-A02.dom.txt':['解除关联 A02','comment_49f64aa1ab3f4bdca2c74fd0aa84c8a1'],
'deleted-A01-original-number-links.dom.txt':['恢复意见 A01','comment_f7969d2589c14c6a9e3d1c923bd1b381','查看修改 1'],
'restored-same-A01-A02.dom.txt':['开始修改意见 A01','结束关联意见 A02','comment_f7969d2589c14c6a9e3d1c923bd1b381','comment_49f64aa1ab3f4bdca2c74fd0aa84c8a1'],
'returned-A-ordinary-same-comments.dom.txt':['普通编辑','固定被审稿 v4 / 作者结构 r11','comment_f7969d2589c14c6a9e3d1c923bd1b381','comment_49f64aa1ab3f4bdca2c74fd0aa84c8a1'],
}
for file,tokens in requirements.items():assert all(t in (proof/file).read_text(encoding='utf-8') for t in tokens),file
for file in ['only-A02-after-removing-A01.dom.txt','archived-A01-active-A02.dom.txt']:assert '解除关联 A01' not in (proof/file).read_text(encoding='utf-8')
assert '解除关联 A02' not in (proof/'returned-A-ordinary-same-comments.dom.txt').read_text(encoding='utf-8')
assert '当前意见关联' not in (proof/'B-no-A-comment-context-before-edit.dom.txt').read_text(encoding='utf-8')
prior=read(repo/'.tmp/scholar-g04-seal-v1.json');prior_report=Path(prior['directory']);prior_manifest=read(prior_report/'manifest.json')
assert all(sha(prior_report/p)==h for p,h in prior_manifest['files'].items()) and all(sha(p)==h for p,h in prior_manifest['current_source_sha256'].items())
report=repo/'docs/reviews/scholar-rstv4-2026-09-30/formal-revision-comment-context-2026-10-12';report.mkdir()
def save(source,target):
    dest=report/target;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest);assert sha(source)==sha(dest)
for p in root.rglob('*'):
    if p.is_file():save(p,Path('evidence/native-v1')/p.relative_to(root))
for p in (repo/'.tmp').glob('scholar-g06-*'):
    if p.is_file() and p.suffix in {'.py','.json','.log'}:save(p,Path('evidence/helpers')/p.name)
for p in prior_manifest['current_source_sha256']:save(Path(p),Path('source-current')/Path(p).relative_to(repo.parent))
text='''# G06 Revision 意见上下文、归档和稳定编号：原始软件实跑

2026-10-12。本组原始 G06 软件定义通过；原始 118 项 / 11 组保持，整体验收未完成。

在同一原稿 A 的真实 Revision 视图，显式建立软件测试第 1 轮，固定原 v4 / 作者结构 r11。期刊字段明确写为“G06 software acceptance — no external reviewer”，意见也明确为软件测试，没有外部审稿或科学判断。通过原粘贴预览和确认入口创建两条真实意见 A01/A02。稿件工作阶段保持 Stage 3，未为了测试提前推进到阶段 5。

## 逐项实跑

| 路径 | 浏览器操作及实际保存 | 结果 |
| --- | --- | --- |
| 可见当前上下文、同时关联 | A01 铅笔进入原结构；结构页显示“正在回应”、解除 A01、关联、结束。显式加入 A02，实际 r14→r15 只改 Beta 段落目的，保存时同时关联 A01/A02 | 通过 |
| 明确增减关联 | 点击解除 A01，结构页仅剩 A02；r15→r16 的实际保存只关联 A02，原 r15 的两个历史链接不被删除 | 通过 |
| 明确结束 | 点击结束本次关联，界面显示“普通编辑／后续修改不关联审稿意见”；r16→r17 的实际保存没有意见链接 | 通过 |
| 归档清当前 ID | 重新启用 A01/A02，实际将 A01 移入已删除。上下文仅剩 A02，A02 仍为 A02；r17→r18 的后续保存只关联 A02，A01 的既有修改链接保留 | 通过 |
| 同编号与同 ID 恢复 | 已删除列表仍显示 A01 的原 ID、原文和一条历史链接；恢复后仍为 A01，A02 仍为 A02。恢复不自动重新关联 A01，原文、批次、顺序、决定/回复状态保持 | 通过 |
| 切稿不带错上下文 | A02 仍活动时返回 Track 打开 B；B 没有 A 的意见上下文。B 实际摘要保存 r1→r2，没有任何 A01/A02 链接。回到 A 后显示普通编辑，原两条意见和轮次基线仍在 | 通过 |

四笔 A 修改都只改变同一原 Beta 的 purpose，完整 before/after JSON 相等比较证实其余作者字段、思想、引用、条件保持。保存时意见集合逐笔为 `{A01,A02}`、`{A02}`、`{}`、`{A02}`；具体 change_id、operation_id、base/resulting revision 及初始关联事件都可查。B 仅摘要追加了明确的跨稿软件测试标记。

A01 的真实 comment ID 为 comment_f7969d2589c14c6a9e3d1c923bd1b381；A02 为 comment_49f64aa1ab3f4bdca2c74fd0aa84c8a1。轮次 review_round_16b039af771747eb899cc0939c271cd4。归档前、已删除、恢复后及重新打开全部核对 ID 与 import_metadata 中固定编号 1/2；没有重排成 A01 或重新创建意见。

## 保护和范围

- 16 次既有模型记录（含 G04 一失败、一通过）、15 条讨论、3 项建议决定、6 个既有任务、4 个生成版本、20 文件及五条 OPEN 检查问题逐项完整保持。本组新增模型、生成、讨论均为 0，没有科学批准或完成问题的操作。
- A 当前 r18、活动 v4、上次生成 r11、Stage 3、未选择来源候选/PENDING 保持；B r2/Drafting。原 G03 α/β 未发送讨论草稿在各自稿件内保持。原 Gemini 拒绝及完整原模型/科学材料均未改。
- 轮次基线行完整保持，原修改和初始关联历史不因解除、结束或归档而丢失。A01 保留一条真实修改链接，A02 保留三条；第三笔普通编辑及 B 的实际编辑均无意见关联。
- 本轮没有产品代码修改，当前 15 项前后端源码 SHA 与 G04/G03 一致；未重复跑无关构建或把历史绿色测试当作本组浏览器结果。没有启动新的预览或模型运行。
- 一次只读查询命令因引号错误在执行前失败，随后改用保存的检查脚本；一次会话进度投影写入异常发生在跨稿检查已成功、结果已保存且 journal 追加之后。官方 resume 成功，未重复作者操作、改动会话引擎或降低断言。

G07 单条/重复/101 条预览、G08 结构组/标签/模板、G09 多轮回复与原来源、G10/G11 全流程及最终 11 组串联仍未整体完成。软删除保存修改链接已证明；回复与核对历史留存的完整周期继续在 G09 核验。本组报告不是科学验证或 gate 批准。
'''
(report/'acceptance.md').write_text(text,encoding='utf-8')
manifest={'status':'PASS_ORIGINAL_G06_NATIVE_SOFTWARE_SCOPE','original_requirement_count':118,'original_group_count':11,'overall_complete':False,'current_source_sha256':prior_manifest['current_source_sha256'],'files':{str(p.relative_to(report)):sha(p) for p in report.rglob('*') if p.is_file()}}
(report/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');assert all(sha(report/p)==h for p,h in manifest['files'].items())
gate=repo/'stage-gates/04-verification-report.md';raw=gate.read_bytes();previous=gate.read_text(encoding='utf-8');backup=repo/f'.tmp/scholar-g06-gate-prior-{time.time_ns()}.raw.md';backup.write_bytes(raw)
heading='## 2026-10-12 G06 Revision 意见上下文与稳定编号原始软件实跑';assert heading not in previous
gate.write_text(previous+'\n\n'+heading+'\n\n实际 A01/A02 上下文增减、结束、归档清 ID、归档后修改、同 ID/编号恢复及 A→B 实际保存无错链通过。四笔 A 保存关联依次为双意见、A02、无意见、A02，B 保存无意见；旧模型/成文/问题保持，未推进阶段。本轮无代码修改或新模型调用。报告：`docs/reviews/scholar-rstv4-2026-09-30/formal-revision-comment-context-2026-10-12/acceptance.md`。原始 118 项/11 组及科学审阅边界保持，整体验收未完成，gate 未批准，继续 G07–G11 和完整串联。\n',encoding='utf-8')
assert gate.read_text(encoding='utf-8').startswith(previous) and backup.read_bytes()==raw
receipt={'status':manifest['status'],'directory':str(report),'sealed_files':len(manifest['files']),'report_sha256':sha(report/'acceptance.md'),'manifest_sha256':sha(report/'manifest.json'),'overall_complete':False}
(repo/'.tmp/scholar-g06-seal-v1.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps(receipt),flush=True)
