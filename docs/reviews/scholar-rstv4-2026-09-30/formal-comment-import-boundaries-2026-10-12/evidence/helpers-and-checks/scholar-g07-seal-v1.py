from pathlib import Path
import hashlib,json,shutil,sys,time
sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();root=repo/'.tmp/scholar-g07-native-v1';proof=root/'proof'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'));sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
base=read(root/'baseline-all-tables.json');final=read(root/'final/all-tables.json')
for phase in ['single','duplicate-cancel','duplicate-kept','bulk-preview','bulk100-imported','corrected100','corrected101','final']:
    assert read(root/phase/'receipt.json')['status'].startswith('PASS_G07_')
assert len(final['review_comments'])==205 and len(final['studio_model_calls'])==16
assert final['review_comments'][:104]==read(root/'bulk100-imported/all-tables.json')['review_comments']
assert final['review_comments'][:204]==read(root/'corrected100/all-tables.json')['review_comments']
assert all(final[t]==base[t] for t in ['manuscripts','studio_documents','studio_operations','studio_changes','comment_changes','studio_model_calls','studio_jobs','manuscript_versions','studio_artifacts','studio_findings','review_rounds','studio_review_round_baselines'])
single=read(proof/'single-blank-lines-before-confirm.values.json');assert single['input']==single['preview'] and '\n\n' in single['input']
assert read(proof/'duplicate-cancel-retained-input.json')['input']==single['input']
duplicate=(proof/'duplicate-before-author-choice.dom.txt').read_text(encoding='utf-8');assert '发现相同意见' in duplicate and '不会自动合并' in duplicate
before=read(proof/'101-complete-preview.values.json');assert len(before['rows'])==101 and before['input']=='\n\n'.join(r['value'] for r in before['rows'])
assert before['confirm']==[{'text':'✓ 确认导入 101 条','disabled':True}]
failed=read(proof/'failed-partial-import-cleared-remainder.values.json');assert failed=={'input':'','previewCount':0,'sourceFullControl':False}
retained=read(proof/'fixed-after-100-retained-101.values.json');assert len(retained['rows'])==101 and retained['input']==retained['rows'][100]['value']
assert all(r['disabled'] for r in retained['rows'][:100]) and not retained['rows'][100]['disabled']
assert any('1 条未选意见仍保留' in value for value in retained['alerts'])
assert retained['confirm']==[{'text':'✓ 确认导入 0 条','disabled':True}]
last=final['review_comments'][-1];metadata=json.loads(last['import_metadata_json'])
assert metadata['comment_number']==205 and metadata['original_index']==100
assert metadata['raw_import_text']=='\n\n'.join(r['value'] for r in retained['rows'])
assert last['original_text']==retained['rows'][100]['value']
assert '原始顺序：第 101 条' in (proof/'fixed-A205-original-order101-final.dom.txt').read_text(encoding='utf-8')
source=(proof/'fixed-A205-complete-original-source.txt').read_text(encoding='utf-8');assert retained['rows'][0]['value'] in source and retained['rows'][100]['value'] in source
assert before['rows'][100]['value'] in (proof/'fixed-A104-complete-original-source.txt').read_text(encoding='utf-8')
checks=read(repo/'.tmp/scholar-g07-front-v1.json');assert len(checks)==6 and all(r['exit_code']==0 for r in checks)
build=read(repo/'.tmp/scholar-g07-build-v1.json');assert build['status']=='PASS' and build['original_source_and_dist_unchanged']
front=repo.parent/'writing-studio';assert all(sha(front/p)==h for p,h in build['before'].items())
prior=read(repo/'.tmp/scholar-g06-seal-v1.json');prior_report=Path(prior['directory']);prior_manifest=read(prior_report/'manifest.json')
assert all(sha(prior_report/p)==h for p,h in prior_manifest['files'].items())
assert all(sha(p)==h for p,h in prior_manifest['current_source_sha256'].items() if not p.endswith('components\\studio-workspace.tsx'))
sources=list(prior_manifest['current_source_sha256'])+[str(front/p) for p in ['lib/review-comment-preview.ts','tests/unit/review-comment-preview.cjs']]
source_sha={p:sha(p) for p in sources}
report=repo/'docs/reviews/scholar-rstv4-2026-09-30/formal-comment-import-boundaries-2026-10-12';report.mkdir()
def save(source,target):
    dest=report/target;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest);assert sha(source)==sha(dest)
for origin,folder in [(root,'evidence/native-v1'),(repo/'.tmp/scholar-g07-session-reopen-context-v1','evidence/shared-session-context')]:
    for p in origin.rglob('*'):
        if p.is_file():save(p,Path(folder)/p.relative_to(origin))
for p in (repo/'.tmp').glob('scholar-g07-*'):
    if p.is_file() and p.suffix in {'.py','.json','.log'}:save(p,Path('evidence/helpers-and-checks')/p.name)
for p in source_sha:save(Path(p),Path('source-current')/Path(p).relative_to(repo.parent))
text='''# G07 单条、重复与 101 条分批：逐项修复和原始软件实跑

2026-10-12。本组原始 G07 软件定义通过，原始 118 项 / 11 组保留；11 组整体验收仍未完成，未批准 gate 或科学依据。

## 发现并修复的实际缺口

原界面确实能预览全部 101 条并阻止一次提交超过 100 条。但实际选择前 100 条导入成功后，入口变为空串、预览全部消失，未选第 101 条不能直接继续。后台 100 条保存记录中的 raw_import_text 仍包含全部 101 条；原界面“原意见与导入来源”仅显示单条原文及可选文件名，无法从界面回查完整来源。保留这次真实 100 条导入、空入口/零预览数据、DOM 和原代码，没有删掉失败前置数据或把后台留存冒充原界面可继续。

修复后，成功条目保持原数组位置并锁定，未选条目及其预览编辑文本留在入口和原预览中，原文/原始索引/完整来源元数据保持。后续只确认新的选择，已导入条目不能重选或重复提交；所有条目处理完毕才清空预览。原意见面板新增原始顺序、导入批次及完整导入原文回查。

## 逐项真实操作

| 原始要求 | 实跑结果 | 结果 |
| --- | --- | --- |
| 单条新增中的空行仍为单条 | 在原单条入口输入两段及段内换行，预览 1 条，文本值逐字相等；确认后只有 A03 一条，原文和编辑后文本都保留空行/换行 | 通过 |
| 重复只提示、由作者决定 | 相同输入再次预览显示重复警示，取消勾选时 0 条确认禁用，取消后全文保留且后台仍 3 条；随后明确保留，独立创建 A04，A03 原 ID/文本不变，没有自动合并 | 通过 |
| 101 条明确提示、完整原文不丢 | 原完整 101 条预览逐条与输入比较一致，确认 101 条禁用；实际取消第 101 条后成功导入前 100 条，后台完整源文本仍含原第 101 条 | 通过，原续导入缺口已修复 |
| 修复后的真实 100＋1 完整流程 | 用新的 101 条、每条含段内换行的语料重跑。第一批实际新增 100 条；保留预览仍是原 101 个位置，前 100 条只读锁定，第 101 条可编辑且仍未选择。入口精确保留第 101 条，提示 1 条未选意见仍保留。仅选择最后一条再确认，实际仅新增一条，没有重导前 100 条 | 通过 |
| 原始来源与顺序持久回查 | 最后一条是 A205，数据库及展开原来源面板都显示原始第 101 条，original_index=100；两批完整源文本完全一致。完整来源面板同时可见第 1/101 条原文；原失败批次 A104 的完整 101 条来源也已可回查 | 通过 |
| 刷新后的记录及旧数据 | 刷新后 205 条软件测试意见保留，A01/A02、原 G06 修改关联与基线保持，已完成预览不再重复提交 | 通过 |

当前 205 条 = 原 G06 两条 + 本组单条/重复两条 + 修复前真实 100 条 + 修复后真实 100＋1 条。修复前未选的第 101 条没有补造为意见；它完整留在第一批原始来源中且现已可从界面回查。所有批次都明确是软件测试，不是外部审稿或科学判断。原失败批次及未选原文都没有删除。

## 保护、校验与限制

- 当前 A r18、B r2 作者文档和作者操作完全不变；本组新模型/生成/讨论/作者操作均为 0。16 次旧模型记录、6 个旧任务、4 个生成版本、20 文件 SHA、五条 OPEN 检查问题、原建议决定和原 Gemini 拒绝全部保持。
- 六项前端校验通过：类型、拒绝警告的规范检查、3 项真实批次保留边界契约、3 项原视图恢复契约、7 项文件交付契约及差异格式；隔离生产构建通过，原 source/dist 未被构建替换。后台代码未改，没有把历史 1067 检查算成本次重新实跑或全部 11 组验收。
- 修复只更新原 Studio 的意见预览与来源回查，新增一个批次状态纯函数及有意义的边界测试。未批准科学来源、自动处理意见、生成成文或推进阶段。
- 长预览的工具指针式取消勾选曾未改变状态；读取真实 aria-checked 后使用同一控件 Space 完成。下一批最后条目的直接点击成功。原来源面板的长页面指针操作也曾未展开，读取实际 details 状态后用该 summary 的 Enter 展开并核对真实文字；保留原工具失败快照，不宣称这些失败动作成功。
- 封存前官方管理会话已被另一项只读 honc 讨论关闭，最终审计子命令未执行。重新读取并备份完整最新共享 handoff/mission/progress，确认 verification/pending_review 后官方 start，再执行只读最终审计。未重导意见、重发检查或启动模型；完整 honc 讨论与先前科学/验收交接在最终 handoff 中原样保留。

当前前端仍使用 3008，仅替换了经过完整身份核验的原前端链；后台 8881 未重启，其他用户/工具/科学运行与已关闭旧预览未动。下一步继续原 G08–G11，最后完成全部 11 组串联。205 个测试意见仍为待处理，这不等于意见已处理、返修完成或可发表。
'''
(report/'acceptance.md').write_text(text,encoding='utf-8')
manifest={'status':'PASS_ORIGINAL_G07_REPAIRED_NATIVE_SOFTWARE_SCOPE','original_requirement_count':118,'original_group_count':11,'overall_complete':False,'current_source_sha256':source_sha,'files':{str(p.relative_to(report)):sha(p) for p in report.rglob('*') if p.is_file()}}
(report/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');assert all(sha(report/p)==h for p,h in manifest['files'].items())
gate=repo/'stage-gates/04-verification-report.md';raw=gate.read_bytes();previous=gate.read_text(encoding='utf-8');backup=repo/f'.tmp/scholar-g07-gate-prior-{time.time_ns()}.raw.md';backup.write_bytes(raw)
heading='## 2026-10-12 G07 单条、重复与 101 条真实分批修复实跑';assert heading not in previous
gate.write_text(previous+'\n\n'+heading+'\n\n实际发现选择 100/101 导入后未选条目预览清空及完整来源不可回查，修复并重跑真实 100＋1。成功条目锁定，剩余条留在原索引/来源；最后只新增一条，原始顺序仍第 101 条，完整全文可回查。单条空行、重复取消/保留及刷新通过。205 条均为软件测试待处理意见，未处理问题/科学审批/11 组整体仍未完成；原模型/作者/成文保持。本组报告：`docs/reviews/scholar-rstv4-2026-09-30/formal-comment-import-boundaries-2026-10-12/acceptance.md`。gate 未批准，继续 G08–G11 和完整串联。\n',encoding='utf-8')
assert gate.read_text(encoding='utf-8').startswith(previous) and backup.read_bytes()==raw
receipt={'status':manifest['status'],'directory':str(report),'sealed_files':len(manifest['files']),'report_sha256':sha(report/'acceptance.md'),'manifest_sha256':sha(report/'manifest.json'),'overall_complete':False}
(repo/'.tmp/scholar-g07-seal-v1.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps(receipt),flush=True)
