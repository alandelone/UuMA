from pathlib import Path
import hashlib
import json
import re
import shutil
import sqlite3
import sys

r=Path.cwd()
review=r/'docs/reviews/scholar-rstv4-2026-09-30'
dest=review/'formal-generated-materials-2026-10-09'
assert not dest.exists()
dest.mkdir()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def copy(source,target):
    source=Path(source);target=dest/target
    target.parent.mkdir(parents=True,exist_ok=True)
    assert not target.exists()
    shutil.copy2(source,target)
    assert sha(source)==sha(target)

full=json.loads((r/'.tmp/scholar-generated-assets-full-v2.json').read_text(encoding='utf-8'))
static=json.loads((r/'.tmp/scholar-generated-assets-static-v2.json').read_text(encoding='utf-8'))
assert full['status']=='PASS' and full['before_sha256']==full['after_sha256'] and full['changed_during_verification']==[]
assert len(full['results'])==23 and len(static)==15 and all(v['exit_code']==0 for v in full['results']+static)
assert all(sha(path)==digest for path,digest in full['after_sha256'].items())
assert '1051 passed, 20 warnings' in (r/'.tmp/scholar-generated-assets-full-v2.log').read_text(encoding='utf-8')
assert '67 passed' in (r/'.tmp/scholar-generated-assets-focused-v9.log').read_text(encoding='utf-8')
audit=json.loads((r/'.tmp/scholar-generated-assets-native-audit-v3/receipt.json').read_text(encoding='utf-8'))
assert audit['status']=='PASS_NATIVE_MATERIAL_DELIVERY_AND_INDEPENDENT_AUDIT'
assert audit['all_pdf_words_within_page_margins'] and audit['table_titles_above_rows']
assert audit['all109tables_preserve_foreign_records'] and audit['prior_native_versions_and_downloads_preserved']
assert audit['independent_recompile_exit']==0 and audit['zip_files']==25
assert sha(audit['downloaded_pdf'])==audit['pdf_sha256'] and sha(audit['downloaded_zip'])==audit['zip_sha256']
assert len(audit['rendered_pages'])==3
visual={'status':'PASS_ACTUAL_THREE_PAGE_IMAGE_INSPECTION','pdf_sha256':audit['pdf_sha256'],
        'method':'All three actual Poppler PNG pages inspected with view_image after native download and independent geometry audit.',
        'page1':'Original PNG and original text/title/caption legible, no clipping.',
        'page2':'Original JPEG and SVG shapes/colors/captions legible; complete ten-row CSV remains together with caption above, inside margins.',
        'page3':'Both original XLSX sheets and complete ten-row Markdown table legible with captions above and all cells inside margins.',
        'pages':{str(i):{'path':path,'sha256':sha(path)} for i,path in enumerate(audit['rendered_pages'],1)},
        'prior_native_v1_visual_status':'FAIL_TABLE_RIGHT_EDGE_RETAINED','scientific_acceptance':False}
(dest/'pdf-visual-review.json').write_text(json.dumps(visual,ensure_ascii=False,indent=2),encoding='utf-8')

fixture=json.loads((r/'.tmp/scholar-generated-assets-native-v1.json').read_text(encoding='utf-8'))
native_root=Path(fixture['root'])
def tables():
    with sqlite3.connect(f"file:{(native_root/'data/catalog.db').as_posix()}?mode=ro",uri=True) as c:
        c.row_factory=sqlite3.Row
        return {x[0]:[dict(v) for v in c.execute('SELECT * FROM "'+x[0]+'" ORDER BY rowid')]
                for x in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
before=tables()
sys.path.insert(0,str(r.parent/'RSTV4/src'))
from rstv4.studio import StudioService
service=StudioService(native_root)
versions=[v for v in before['manuscript_versions'] if v['manuscript_id']==audit['manuscript_id']]
assert len(versions)==3
strict=[]
try:
    for version in versions:
        view=service.get_generated_version(audit['manuscript_id'],version['manuscript_version_id'])
        assert len(view['artifacts'])==5
        strict.append({'version':version['version'],'generated_version_id':version['manuscript_version_id'],'strict_current_reader':'PASS'})
finally:service._executor.shutdown(wait=True)
assert tables()==before
(dest/'strict-version-read-audit.json').write_text(json.dumps({'status':'PASS','all109tables_exact_after_reads':True,'versions':strict},indent=2),encoding='utf-8')
for path in (r/'.tmp').glob('scholar-generated-assets-*'):
    if path.is_file():copy(path,Path('evidence')/path.name)
for name in ['before-v1','render-v1','visual-before-v2','native-proof-v1','native-proof-v2','native-audit-v2','native-audit-v3']:
    source=r/('.tmp/scholar-generated-assets-'+name)
    assert source.exists(),source
    for path in source.rglob('*'):
        if path.is_file():copy(path,Path('evidence')/source.name/path.relative_to(source))
for version in versions:
    inputs=json.loads(version['inputs_json'])
    source=native_root/'data/writing-studio'/audit['manuscript_id']/'generated'/inputs['job_id']
    assert source.exists()
    for path in source.iterdir():
        if path.is_file():copy(path,Path('generated-versions')/('v'+str(version['version']))/path.name)
for record in before['studio_submission_packages']:
    if record['manuscript_id']!=audit['manuscript_id']:continue
    manifest=json.loads(record['manifest_json'])
    source=native_root/'data/writing-studio'/audit['manuscript_id']/'packages'/record['job_id']
    for name in manifest['files']:copy(source/name,Path('packages')/record['package_id']/name)
copy(audit['downloaded_pdf'],'downloads/manuscript-v3.pdf')
copy(audit['downloaded_zip'],'downloads/submission-package-v3.zip')
old=json.loads((r/'.tmp/scholar-generated-assets-native-audit-v2/receipt.json').read_text(encoding='utf-8'))
copy(old['downloaded_pdf'],'downloads/manuscript-v1-retained.pdf')
copy(old['downloaded_zip'],'downloads/submission-package-v1-retained.zip')
changed=['RSTV4/src/rstv4/studio_materials.py','RSTV4/src/rstv4/studio.py','RSTV4/src/rstv4/studio_api.py',
         'RSTV4/src/rstv4/studio_context.py','RSTV4/src/rstv4/studio_read_views.py','RSTV4/pyproject.toml',
         'RSTV4/tests/test_studio_generated_assets.py','writing-studio/lib/studio-types.ts','writing-studio/components/studio-workspace.tsx']
current={}
for name in changed:
    path=r.parent/name
    copy(path,Path('source-after')/name)
    current[str(path)]=sha(path)
for repo in ['RSTV4','writing-studio']:
    assert not (r.parent/repo/'.codegraph').exists() and not (r.parent/repo/'AGENTS.md').exists()
copy(review/'generated-materials-contract-2026-10-09.md','contract.md')
copy(review/'ui-requirements-preservation.md','original-118-and-11-scope.md')
scope=(review/'ui-requirements-preservation.md').read_text(encoding='utf-8')
requirements=[line for line in scope.splitlines() if re.match(r'^\|\s*(OV|CA|RV|AC|KG|TR|ST|WF|RE|CH)-\d+',line)]
groups=[line for line in scope.splitlines() if re.match(r'^\|\s*G-\d+',line)]
assert len(requirements)==118 and len(groups)==11
scope_status={'original_requirement_count':118,'original_group_count':11,'original_scope_sha256':sha(review/'ui-requirements-preservation.md'),
              'material_batch_requirement_ids':['ST-19','ST-16','WF-03','WF-06','RE-14'],
              'original_rows_retained':requirements,'original_groups_retained':groups,
              'all118_complete':False,'all11_complete':False,'g05_closed_by_this_material_batch':False,'g09_closed_by_this_material_batch':False,
              'scientific_acceptance':False,'remote_model_calls':0,'download_testing_resumed':True,
              'scope_limit':'Supported material output and native downloads were verified with explicitly declared software fixtures. Numeric-citation/evidence context, qualified scientific sources, upload permission and all broader workflow requirements are not certified by this batch.'}
(dest/'scope-and-limitations.json').write_text(json.dumps(scope_status,ensure_ascii=False,indent=2),encoding='utf-8')
parent_audits=[]
for name in ['formal-download-retry-2026-10-09','formal-intent-correspondence-2026-10-09']:
    parent=review/name
    manifest=json.loads((parent/'manifest.json').read_text(encoding='utf-8'))
    for filename,record in manifest['files'].items():
        expected=record if isinstance(record,str) else record['sha256']
        assert sha(parent/filename)==expected,filename
    parent_audits.append({'report':name,'sealed_files':len(manifest['files']),'status':'ALL_SEALED_FILES_EXACT',
                          'historical_current_source_hashes':'not compared to deliberately changed material source'})
(dest/'parent-seal-audit.json').write_text(json.dumps(parent_audits,indent=2),encoding='utf-8')
report=f'''# 六种原素材进入固定成文、PDF 和投稿包：修复与实跑验收

已修复素材只停留在作者区／ID 记录、没有进入成文和编译稿的问题。PNG、JPEG、SVG 图片和 CSV、XLSX、Markdown 表格现在使用同一份固定素材快照进入成文页面、Markdown、LaTeX、PDF 和投稿包；完整表格不再取六行小预览。原文件按字节保留，素材缺失、损坏或不属于稿件时明确拒绝生成。

本轮还修复了 Windows 长路径导致图片无法编译、十行小表被拆开、表格标题挤在同行而使右侧内容越出纸面三个实际问题。保留原失败日志、旧 PDF／ZIP 和逐页截图，修复后重新实跑，没有覆盖旧成文版本。

## 最终验证

- 最终完整回归 **1051 passed / 20 warnings**；相关套件 **67 passed**，其中六格式／字节与所有单元格／腐败拒绝／独立编译／16 位 PNG 等新增素材契约为 9 项。前端 15 项检查和后台／目录 23 项检查全部通过。392 个源码文件在最终回归前后相同，封存时再次核对。
- Chrome 实际点击生成、定稿、投稿包和下载入口。稿件 `{audit['manuscript_id']}`，作者修订 r3（原目的编辑后撤销，最终完整作者文档与原始 r1 精确相同），当前固定成文 v3 `{audit['generated_version_id']}`。CSV、Markdown 各十行及表头、XLSX 十行与第二工作表逐格对应原文件；三幅图实际加载，刷新后的内容和固定链接相同。
- 新下载 PDF `manuscript (2).pdf`，SHA256 `{audit['pdf_sha256']}`；**三页实际图像逐页检查通过**，三图和所有表格完整、标题在表上方、没有右侧裁切；独立 Poppler 位置检查同时通过。原 v1 的右侧越界证据继续保留。
- 新下载 ZIP `{Path(audit['downloaded_zip']).name}`，{audit['zip_bytes']} 字节，SHA256 `{audit['zip_sha256']}`；**25 个文件**全部 CRC、名称、大小及固定清单哈希一致。六个原文件、三份渲染图及全部编译依赖在包内；包内 PDF 与新下载 PDF 完全相同。解包到独立目录后，真实编译返回 0。
- 独立核对 109 表，所有旧记录和其他稿件不变；当前作者完整原文／ID／素材顺序不变，旧三个生成版本均通过当前严格读取，旧产物和下载文件保持。没有数据库迁移。上轮下载报告 20 个、作者对应报告 872 个密封文件再次完整核对。

## 实跑范围与继续项

| 原要求 | 本轮证明 | 尚不能由本轮证明 |
| --- | --- | --- |
| ST-19 | 六种正式格式保留；作者小预览与成文完整素材分别实看；编译、冻结和整包交付 | 浏览器上传权限仍按此前边界；所有复杂文件／公式和科学素材场景还须完整原范围验收 |
| ST-16 | 原素材文件名、SHA、版本、固定文件可查，旧版本不追随实时文件变化 | 全部 Evidence 原文、精确页段与上下文回查 |
| WF-03 | 当前完整作者输入、顺序、素材、模型调用输入与固定快照一致，刷新可回读 | 全部真实科学来源／模板／引用组合 |
| WF-06 | 声明的软件原文未重写；所有五个主产物成功登记，真实编译和拒绝路径通过 | 真实模型对科学命题、条件和强度的合格保持 |
| RE-14 | 新旧包共存、原文件和依赖完整、真实下载及独立编译通过 | 本例没有审稿意见和被审轮次，不能据此证明完整返修六件材料质量 |

原 **118 条要求／G-01 至 G-11** 全部保留，**11 组整体验收仍未完成**。本素材批次不关闭 G-05 数字引用、G-09 完整来源与返修，其他历史证据也不因本轮被重写。3 次段落实跑调用均明确标为 `TEST_FIXTURE_MATERIALS_NATIVE`，远程真实模型调用为 0；软件通路通过不代表科学内容获得批准。任务继续保持 active，mission 仍为 verification / pending_review，未推进 gate。

## 可核对产物

[新 PDF](downloads/manuscript-v3.pdf)、[新 ZIP](downloads/submission-package-v3.zip)、[独立核对回执](evidence/scholar-generated-assets-native-audit-v3/receipt.json)、[逐页视觉核对](pdf-visual-review.json)、[最终回归](evidence/scholar-generated-assets-full-v2.log)、[完整原要求](original-118-and-11-scope.md)。

![浏览器中新旧固定版本同时保留](evidence/scholar-generated-assets-native-proof-v2/package-v3-and-retained-v1.png)

![完整表格和 XLSX 第二工作表](evidence/scholar-generated-assets-native-proof-v2/generated-v3-full-tables.png)

![修复后的 PDF 第三页](evidence/scholar-generated-assets-native-audit-v3/render/page-3.png)

SVG 渲染使用声明依赖 resvg-py 0.5.0，PNG/JPEG 使用 Pillow；实现依据：[维护者 API 文档](https://resvg-py.readthedocs.io/en/latest/api.html)。冻结和哈希保护由本项目实际验证。
'''
(dest/'acceptance.md').write_text(report,encoding='utf-8')
files={str(p.relative_to(dest)):sha(p) for p in dest.rglob('*') if p.is_file()}
manifest={'status':'SUPPORTED_MATERIAL_NATIVE_DELIVERY_PASS_OVERALL_INCOMPLETE','files':files,'current_source_sha256':current,
          'all118_all11_scope_retained':True,'all11_complete':False,'g05_complete':False,'g09_complete':False,
          'scientific_acceptance':False,'schema_migration':False,'download_testing_resumed':True,
          'full_python_tests':1051,'affected_tests':67,'frontend_checks':15,'backend_catalog_checks':23,
          'native_generated_versions':3,'native_fixture_model_calls':3,'native_packages':2,
          'final_pdf_sha256':audit['pdf_sha256'],'final_zip_sha256':audit['zip_sha256']}
(dest/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
assert all(sha(dest/name)==digest for name,digest in files.items())
assert all(sha(path)==digest for path,digest in current.items())
note=f'\n\n2026-10-09 原素材实跑续批：六种格式进入固定成文／完整表格／实际 PDF／25 文件投稿包，Windows 长路径与实际排版问题修复后再次逐页核对。最终1051全量／67相关／23后台和15前端检查通过；浏览器原生下载PDF/ZIP、独立重编译、109表旧记录与原作者精确核对通过。原118／全部11仍未整体通过；G05／G09不关闭，真实科学内容与完整工作流继续。下载已恢复，未扩展上传／科学批准边界。证据：{dest.as_posix()}/acceptance.md。\n'
for name in ['repomemory/findings.md','stage-gates/04-verification-report.md','docs/reviews/scholar-rstv4-2026-09-30/formal-implementation-progress.md','docs/reviews/scholar-rstv4-2026-09-30/ui-requirements-preservation.md']:
    with (r/name).open('a',encoding='utf-8') as handle:handle.write(note)
mission=json.loads((r/'mission_status.json').read_text(encoding='utf-8'))
assert mission['stage']=='verification' and mission['gate']['status']=='pending_review' and mission['active_skill'] is None
receipt={'status':manifest['status'],'directory':str(dest),'sealed_files':len(files),'report_sha256':sha(dest/'acceptance.md'),
         'final_pdf_sha256':audit['pdf_sha256'],'final_zip_sha256':audit['zip_sha256'],'all11_complete':False,
         'native_tab':'1479455125','backend_root_pid':47692,'frontend_root_pid':100000}
(r/'.tmp/scholar-generated-assets-seal-v1.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps(receipt))
