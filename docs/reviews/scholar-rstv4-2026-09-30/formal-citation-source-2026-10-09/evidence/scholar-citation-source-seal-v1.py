from pathlib import Path
import hashlib,json,re,shutil,sqlite3,sys
repo=Path.cwd();review=repo/'docs/reviews/scholar-rstv4-2026-09-30';dest=review/'formal-citation-source-2026-10-09'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
full=json.loads((repo/'.tmp/scholar-citation-source-full-v3.json').read_text(encoding='utf-8'))
assert full['before']==full['after'] and full['source_stable'] and full['source_files']==402
assert all(r['exit_code']==0 for r in full['results'])
assert '1067 passed, 20 warnings' in (repo/'.tmp/scholar-citation-source-full-v3.log').read_text(encoding='utf-8')
delta=[name for name,digest in full['after'].items() if sha(repo.parent/name)!=digest]
assert delta==['writing-studio/components/studio-workspace.tsx'],delta
assert '65 passed' in (repo/'.tmp/scholar-citation-discussion-focused-v1.log').read_text(encoding='utf-8')
front=json.loads((repo/'.tmp/scholar-citation-source-front-v3.json').read_text(encoding='utf-8'))
assert len(front)==4 and all(r['exit_code']==0 for r in front)
build=json.loads((repo/'.tmp/scholar-citation-source-build-v3.json').read_text(encoding='utf-8'))
assert build['status']=='PASS' and build['original_source_and_dist_unchanged']
refresh=json.loads((repo/'.tmp/scholar-citation-source-build-refresh-v3.json').read_text(encoding='utf-8'))
assert refresh['status']=='PASS' and refresh['entire_database_bytes_preserved']
audit_dir=repo/'.tmp/scholar-citation-source-native-audit-v1';audit=json.loads((audit_dir/'receipt.json').read_text(encoding='utf-8'))
assert audit['status']=='PASS_READ_ONLY_RECORD_AND_DOWNLOAD_AUDIT' and audit['tables']==109
assert audit['all_original_failed_rows_preserved'] and audit['recorded_real_model_replies']==1
assert audit['software_generation_calls']==audit['software_discussion_replies']==2
assert len(audit['rendered_pages'])==5 and all(sha(item['file'])==item['sha256'] and sha(item['browser_download'])==item['sha256'] for item in audit['downloads'])
fixture=json.loads((repo/'.tmp/scholar-citation-source-native-v1.json').read_text(encoding='utf-8'))
native_root=Path(fixture['root']);db=native_root/'data/catalog.db'
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as conn:
 conn.row_factory=sqlite3.Row
 current={r[0]:[dict(x) for x in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
assert current==json.loads((audit_dir/'all-tables.json').read_text(encoding='utf-8'))
parent=review/'formal-generated-materials-2026-10-09';parent_manifest=json.loads((parent/'manifest.json').read_text(encoding='utf-8'))
assert len(parent_manifest['files'])==240
assert all(sha(parent/name)==digest for name,digest in parent_manifest['files'].items())
assert sha(parent/'acceptance.md')=='2981e545c4e4a3fdee528695a22dbef2a6a2f35e83f8e2a1f23c8b13c6c5679f'
changed_parent_sources=[name for name,digest in parent_manifest['current_source_sha256'].items() if sha(name)!=digest]
assert len(changed_parent_sources)==5
sys.path.insert(0,str(repo.parent/'RSTV4/src'))
from rstv4.studio_read_views import generated_version
old_fixture=json.loads((repo/'.tmp/scholar-generated-assets-native-v1.json').read_text(encoding='utf-8'));old_root=Path(old_fixture['root']);old_db=old_root/'data/catalog.db';old_sha=sha(old_db)
strict_old=[]
with sqlite3.connect(f'file:{old_db.as_posix()}?mode=ro',uri=True) as conn:
 conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON')
 for version in conn.execute('SELECT * FROM manuscript_versions WHERE manuscript_id=? ORDER BY version',(old_fixture['manuscript_id'],)):
  result=generated_version(conn,old_root/'data/writing-studio',old_fixture['manuscript_id'],version['manuscript_version_id'])
  assert len(result['artifacts'])==5
  strict_old.append({'version':version['version'],'generated_version_id':version['manuscript_version_id'],'current_strict_read':'PASS'})
assert len(strict_old)==3 and sha(old_db)==old_sha
scope_path=review/'ui-requirements-preservation.md';scope=scope_path.read_text(encoding='utf-8')
requirements=[line for line in scope.splitlines() if re.match(r'^\|\s*(OV|CA|RV|AC|KG|TR|ST|WF|RE|CH)-\d+',line)]
groups=[line for line in scope.splitlines() if re.match(r'^\|\s*G-\d+',line)]
assert len(requirements)==118 and len(groups)==11
mission_before=sha(repo/'mission_status.json');mission=json.loads((repo/'mission_status.json').read_text(encoding='utf-8'))
assert mission['stage']=='verification' and mission['gate']['status']=='pending_review' and mission['active_skill'] is None
assert not dest.exists();dest.mkdir()
def copy(source,target):
 target=dest/target;target.parent.mkdir(parents=True,exist_ok=True);assert not target.exists();shutil.copy2(source,target);assert sha(source)==sha(target)
for pattern in ['scholar-citation-source-*','scholar-citation-discussion-*']:
 for path in (repo/'.tmp').glob(pattern):
  if path.is_file():copy(path,Path('evidence')/path.name)
for name in ['scholar-citation-source-before-v1','scholar-citation-discussion-before-v1','scholar-citation-source-native-proof-v1','scholar-citation-source-native-audit-v1','scholar-citation-source-failed-discussion-v1','scholar-citation-source-resume-v1']:
 folder=repo/'.tmp'/name;assert folder.is_dir()
 for path in folder.rglob('*'):
  if path.is_file():copy(path,Path('evidence')/name/path.relative_to(folder))
sources=['RSTV4/src/rstv4/studio_sources.py','RSTV4/src/rstv4/studio.py','RSTV4/src/rstv4/studio_api.py','RSTV4/src/rstv4/studio_read_views.py','RSTV4/src/rstv4/studio_discussions.py','RSTV4/tests/test_studio_source_context.py','RSTV4/tests/test_studio_discussion_fixed_references.py','writing-studio/components/studio-source-context.tsx','writing-studio/components/studio-workspace.tsx','writing-studio/lib/studio-types.ts','writing-studio/lib/studio-downloads.ts','writing-studio/tests/unit/studio-downloads.cjs']
source_hashes={}
for name in sources:
 path=repo.parent/name;copy(path,Path('source-after')/name);source_hashes[str(path)]=sha(path)
versions=json.loads((audit_dir/'fixed-generated-versions.json').read_text(encoding='utf-8'))
for version in current['manuscript_versions']:
 if version['manuscript_id']!=fixture['manuscript_id']:continue
 inputs=json.loads(version['inputs_json']);folder=native_root/'data/writing-studio'/fixture['manuscript_id']/'generated'/inputs['job_id']
 for path in folder.rglob('*'):
  if path.is_file():copy(path,Path('generated-versions')/f"v{version['version']}"/path.relative_to(folder))
copy(scope_path,'original-118-and-11-scope.md')
visual={'status':'PASS_ALL_FIVE_ACTUAL_POPPLER_PAGE_IMAGES','method':'view_image inspected each of the two downloaded manuscript PDF pages and all three original source PDF pages after exact byte/identity audit.','pages':{str(i):{'path':path,'sha256':sha(path)} for i,path in enumerate(audit['rendered_pages'],1)},'manuscript_v1':'Numeric [1], [2], [1] and the original bibliography are legible, inside page margins.','manuscript_v2':'Same numbers and changed bibliography (Other selected source; refreshed live catalog title) are legible, inside page margins.','original_pages_1_2_3':'Exact page-specific headings and body 1/2/3, readable and unclipped.','scientific_acceptance':False}
(dest/'pdf-visual-review.json').write_text(json.dumps(visual,ensure_ascii=False,indent=2),encoding='utf-8')
parent_audit={'status':'PASS','original_material_files_verified':240,'original_material_three_versions_strictly_read':strict_old,'original_material_database_bytes_preserved':True,'deliberately_changed_current_material_sources':changed_parent_sources,'all_other_material_sources_unchanged':True}
(dest/'parent-seal-audit.json').write_text(json.dumps(parent_audit,indent=2),encoding='utf-8')
status={'original_requirement_count':118,'original_group_count':11,'original_requirement_rows':requirements,'original_group_rows':groups,'g05_original_numeric_citation_software_acceptance':'PASS_NATIVE_AND_CONTRACT','g01_two_paragraphs_reorder_acceptance':'NOT_COMPLETED_BY_THIS_ONE_PARAGRAPH_FIXTURE','g02_partial_suggestion_acceptance':'RETAINED_PRIOR_EVIDENCE_NOT_RETESTED_BY_THIS_SOURCE_BATCH','g03_g04_g06_g07_g08_g10_g11':'RETAINED_ORIGINAL_REQUIREMENTS_AND_PRIOR_EVIDENCE; COMPLETE_COMBINED_FLOW_PENDING','g09_fixed_generated_source_portion':'PASS_NATIVE_ORIGINAL_PAGES_VERSIONS_CONTEXT_FULL_TEXT','g09_complete_revision_and_live_evidence_source_scope':'PENDING','all118_complete':False,'all11_complete':False,'scientific_acceptance':False,'download_testing_resumed':True,'recorded_real_model_replies':1,'http_attempt_count_not_established':True,'no_schema_migration':True,'full_backend_tests':1067,'warnings':20,'focused_discussion_and_context_tests':65,'frontend_checks':4,'full_regression_source_files_stable':402,'post_full_change_only':delta,'final_frontend_change_type_lint_build_and_native_verified':True}
(dest/'scope-and-limitations.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
contract='''Exact generated Evidence freezes its original excerpt, semantic unit, neighboring units, full original parse blocks, paper/file/parse/skeleton identities, locations and digests. Missing provenance stays explicitly unavailable; partial, foreign or changed provenance rejects before model execution. Original PDF retrieval checks registered original bytes, ownership and immutable version; its native link targets the recorded page. The model receives selected unit and full-context SHA, not a repeated entire paper. Generated references must match the original validated call. Shared discussions receive those verified frozen references before live retrieval without relaxing the response allowlist. Message source buttons read the exact original message version and never replace a generated source with a live catalog guess. Existing legacy generation records remain readable without fabricating absent originals. No knowledge/scientific authority is applied by these software tests. No database migration. Preserve every failed call, original quote, original input/output and all unrelated workers/user changes.\n'''
(dest/'contract.md').write_text(contract,encoding='utf-8')
report='''# 数字引用、原始来源与旧讨论回查验收

G-05 原定义的软件验收通过：阅读显示 [1] / [2]，顺序与固定参考文献一致，点击打开准确 Evidence；引用标识留在引用数据中。本批还补齐生成版本的原文、邻近上下文、完整解析文字、精确页段和原始 PDF，并修复旧讨论错误使用当前来源的两条路径。

第一次讨论实跑失败暴露了真实问题：模型引用的正是该版本的两个来源，但讨论校验只检查即时搜索结果，漏掉已供给的生成参考文献；搜索命中时则可能传入更新后的题录。现优先传入严格校验过的原快照，原拒绝校验保持。另一个页面问题是旧回复的来源按钮只搜索实时目录，现改为读取该消息保存的生成版本。

## 实跑与最终检查

- Chrome 实际生成两版，作者 r1→r4 只修改引用选择，原文字／结构／ID 完整保持。第一版 [1] 是原论文第 2 页，[2] 是第 1 页，重复 [1] 仍回第 2 页。第二版 [1] 改为另一篇论文第 1 页；题录也已更新。旧消息定位、旧版追问、直接点击旧回复来源和刷新后的源回查，仍保留第一版题录／原文／页段／版本。新稿保持第二版。
- 新旧成文 PDF 实际下载到 `manuscript (3).pdf`／`manuscript (4).pdf`；原始 PDF 实际下载到 `original-source (1).pdf`。三份文件分别与登记产物、原始文件 SHA 和大小一致。两份成文各 1 页及原始 PDF 全部 3 页，真实渲染后逐页检查，共 **5 页通过**。没有用命令行下载冒充浏览器下载。
- 最终后端完整回归 **1067 passed / 20 warnings**；讨论、来源和旧对象相关 **65 passed**；类型、type-aware lint、7 个文件交付合同及差异检查通过。最终页面重新隔离构建并完成按钮实跑。402 个源码在后端全量前后相同；此后只改来源按钮的前端组件，这个精确差异由最终前端检查、构建和原生流程覆盖，后端源码未再变化。
- 独立只读核对 **109 表**：两版、5 条消息、两次成功软件讨论、所有 10 件登记产物和原失败记录精确匹配，读取不改变数据库字节。原素材批次 **240 件密封证据**及三个旧生成版本再校验通过，旧数据库字节保持。没有迁移，也没有改变其他科研运行。

## 保留的失败和边界

来源合同修改前的 11 个失败、讨论修改前的 3 个失败和 2 个拒绝保护通过、原按钮失败截图、PDF 默认跳到第 1 页的旧证据均保留。一次全量为 1060 通过、2 个 Windows 长路径失败；记录执行上下文后使用新的短临时目录，原两个断言及源码未放宽，13 项路径合同和后续 1062／1067 全量通过。

原生夹具开始时我只替换了生成服务的模型入口，漏掉独立讨论服务，因此保存了 **1 条真实 gemini-3.8-flash 回复**；有效原引用因上述遗漏被应用校验拒绝。FAILED 讨论、REJECTED 调用、完整原输出和原报价／选区继续保留，未改为通过。之后明确配置两个服务为 `TEST_FIXTURE_SOURCE_NATIVE`，2 次生成和 2 次讨论回复是声明的软件测试。不能声称本夹具远程调用为零；一条保存的回复也不能确定实际 HTTP 尝试总数。这些记录不构成科学批准。

原 **118 条／11 组**完整保留。G-05 的原数字引用定义有本批实际证据；**11 组整体验收仍未完成**。本例只有一个段落，不能关闭 G-01 所要求的两个段落及改序全流程；不能代替 G-02 的建议部分采用、G-09 的全部实时 Evidence 与第二轮返修材料、其他组完整合验。普通资料卡当前的来源展示仍需完整范围验收。mission 保持 verification / pending_review，未推进 gate。用户已允许 IDM 设置调整后的下载重试；这没有扩展上传权限或科学批准。

## 可核对证据

[独立记录与下载核对](evidence/scholar-citation-source-native-audit-v1/receipt.json)、[五页视觉核对](pdf-visual-review.json)、[最终完整回归](evidence/scholar-citation-source-full-v3.log)、[原 118 条及 11 组](original-118-and-11-scope.md)、[剩余范围](scope-and-limitations.json)。

![新稿参考文献与旧讨论第一版第 2 页来源并存](evidence/scholar-citation-source-native-proof-v1/v2-current-paper-and-v1-original-source.png)

![原文第 2 页的实际 PDF](evidence/scholar-citation-source-native-proof-v1/v1-original-pdf-page2.png)
'''
(dest/'acceptance.md').write_text(report,encoding='utf-8')
files={str(p.relative_to(dest)):sha(p) for p in dest.rglob('*') if p.is_file()}
manifest={'status':'G05_NUMERIC_AND_FIXED_GENERATED_SOURCE_SOFTWARE_PASS_OVERALL_INCOMPLETE','files':files,'current_source_sha256':source_hashes,'all118_all11_retained':True,'g05_numeric_software_acceptance':True,'all11_complete':False,'scientific_acceptance':False,'full_backend_tests':1067,'focused_tests':65,'native_recorded_real_reply':1,'exact_http_attempt_count_unknown':True,'schema_migration':False}
(dest/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
assert all(sha(dest/name)==digest for name,digest in files.items()) and all(sha(name)==digest for name,digest in source_hashes.items())
note=f'\n\n2026-10-09 数字引用与固定原来源续验：G-05 原数字编号定义已实跑通过；生成来源冻结全文／页段／版本／原始PDF，讨论漏传原参考文献及旧回复按钮搜索实时目录已修复后实跑。1067全量／65相关、最终前端检查和隔离正式构建通过；两版原生生成、旧版追问／回查和3份实际下载／5页视觉通过。109表原失败记录保持，原素材240件密封证据及3旧版本再核对。1条真实Gemini拒绝回复如实保留，后继明确软件夹具，不宣称0远程或科学批准。原118／全部11仍未整体验收，G01双段改序、G09完整实时来源及返修等继续；missionverification/pending_review。证据：{dest.as_posix()}/acceptance.md。\n'
for name in ['repomemory/findings.md','stage-gates/04-verification-report.md','docs/reviews/scholar-rstv4-2026-09-30/formal-implementation-progress.md','docs/reviews/scholar-rstv4-2026-09-30/ui-requirements-preservation.md']:
 with (repo/name).open('a',encoding='utf-8') as handle:handle.write(note)
assert sha(repo/'mission_status.json')==mission_before
receipt={'status':manifest['status'],'directory':str(dest),'sealed_files':len(files),'report_sha256':sha(dest/'acceptance.md'),'g05_numeric_software_acceptance':True,'all11_complete':False,'owned_backend_root_pid':81104,'owned_frontend_root_pid':68596,'native_root':str(native_root),'native_tab':'1479455140','full_backend_tests':1067,'original118_count':118,'original11_count':11}
(repo/'.tmp/scholar-citation-source-seal-v1.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps(receipt),flush=True)
