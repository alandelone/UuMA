from pathlib import Path
from datetime import datetime,UTC
import difflib,hashlib,json,shutil
repo=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text(encoding='utf8'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
full_dir=repo/'.tmp/scholar-presentation-review-full-v1';full=read(full_dir/'receipt.json')
assert full['status']=='PASS' and full['commands_completed']==full['commands_expected']==26 and not full['changed_during_run']
assert '1207 passed, 20 warnings' in (full_dir/'check-00.log').read_text(encoding='utf8')
assert all(x['exit_code']==0 and sha(Path(x['log']))==x['log_sha256'] for x in full['results'])
assert all(sha(Path(p))==h for p,h in read(Path(full['source_before'])).items())
native=repo/'.tmp/scholar-presentation-review-native-v1';audit=read(native/'final-audit.json')
assert audit['status']=='PASS_ONE_NATIVE_A215_TYPED_PRESENTATION_CHECK' and audit['one_http_post200_only']
assert audit['all_other108_tables_and_old_checks_exact'] and audit['all_non_database_files_exact'] and audit['all_owned_services_stopped']
build=read(repo/'.tmp/scholar-presentation-review-build-v1.json');assert build['status']=='PASS'
focused=read(repo/'.tmp/scholar-presentation-review-v1/focused-receipt.json')
assert all(focused[i]['exit_code']==0 for i in [1,2,3])
assert 'All checks passed!' in (repo/'.tmp/scholar-presentation-review-v1/lint-repository-config-v2.log').read_text(encoding='utf8')
dest=repo/'docs/reviews/scholar-rstv4-2026-09-30/formal-studio-presentation-review-2026-10-16';dest.mkdir()
def copy(p,name):
    target=dest/name;target.parent.mkdir(parents=True,exist_ok=True);assert not target.exists();shutil.copyfile(p,target);assert sha(p)==sha(target)
for folder in [repo/'.tmp/scholar-presentation-review-v1',native,full_dir]:
    for p in folder.iterdir():
        if p.is_file():copy(p,'evidence/'+folder.name+'/'+p.name)
design=repo/'.tmp/scholar-legacy-origin-design-v1/design.md'
assert sha(design)=='bcbafcf62322343360e68b5dbafd694fd921af60a3f1cc41e931689ebdb231e1'
assert sha(repo/'.tmp/scholar-presentation-review-v1/independent-review.md')=='2b49df54cf5c7f724cd164817b1fb73dac97e313dba1c3b71a351751509a086e'
copy(design,'evidence/scholar-legacy-origin-design-v1/design.md')
for p in (repo/'.tmp').glob('scholar-presentation-review-*.py'):copy(p,'evidence/helpers/'+p.name)
for name in ['scholar-presentation-review-build-v1.json','scholar-presentation-review-build-v1.log']:copy(repo/'.tmp'/name,'evidence/'+name)
names=[*read(repo/'.tmp/scholar-presentation-review-v1/before.json'),'RSTV4/tests/test_studio_presentation_review.py']
patch=[];digests={}
for name in names:
    path=repo.parent/name;before=repo/'.tmp/scholar-presentation-review-v1/before'/name
    copy(path,'source/'+name)
    old=before.read_text(encoding='utf8') if before.exists() else ''
    patch.extend(difflib.unified_diff(old.splitlines(True),path.read_text(encoding='utf8').splitlines(True),fromfile='a/'+name if before.exists() else '/dev/null',tofile='b/'+name))
    digests[name]={'sha256':sha(path),'bytes':path.stat().st_size,'before_sha256':sha(before) if before.exists() else None}
(dest/'source-digests.json').write_text(json.dumps(digests,indent=2),encoding='utf8');(dest/'product-change.patch').write_text(''.join(patch),encoding='utf8')
report=f'''# Studio 仅排版修改的独立回复核对

已补真实纯排版修改的独立确认。原生A215在保留v6→v7和原完整回复上只提交一次，当前RESOLVED/CURRENT，类型PRESENTATION_MODIFIED；没有把排版说成科学正文修改，也没有伪选“不修改”。全部11组仍未完成。

## 完整产品契约

新类型要求保存的完整回复与理由、非归档状态、当前作者版本已生成、逐条完整UTF16声明与唯一证据、显式完整回复确认。基准稿可证实存在，两版全文摘要相同且raw diff为空。每条证据必须LAYOUT_ONLY/PRESENTATION、正文修改支持false、changed_text为空、两版真实词框不同、两版PDF摘要不同，且原基线/目标ID及当前PDF摘要匹配。此前固定版本读取和原文/来源/素材身份、完整唯一定位守卫保留。正文MODIFIED仍要求真实正文diff与GENERATED_TEXT_CHANGED；既有有理由不修改与旧request_id重试保持。

页面新增“仅修改排版，核对实际PDF位置变化”，按类型选择证据。切换类型清空先前声明和确认，不能沿用不兼容证据。历史明确写“作者确认仅排版修改”和真实页行；不标为不修改或科学批准。新类型使用现有自由文本outcome字段，无schema迁移。

## 实际原生执行

继续原scui-complex-native-qjbemsgz，作者r86、成文v7，第四轮基线v6。旧A215决定/回复原字节未改，选取原声明UTF16[24,126]。默认正文模式的排版证据仍禁选，作者确认禁用；切换独立排版模式清空旧声明，重新加入、选择实际位置证据并勾完整回复。

实际只有一次POST200，新check {audit['new_check_id']}；结果PRESENTATION_MODIFIED、RESOLVED/CURRENT。独立历史入口显示原完整理由/回复、原排版声明、固定v7和最终PDF第1页可见文本第4行。两张实际截图已查看。原v6 PDF SHA ec3988b80410560cd1b40d9bd15615718b2c9ab144147a2d028af461d497c0a1；v7 SHA a78ee2ad02957da5bb56876c4c4c526d7be1fe76359fc0489960b80929634b9b。原位置证据和真实变动词框精确保存，零新生成/编译/模型/工作任务/预算/QuickRead/GPU/深读/IDM动作。

完整110表只变化review_comments与studio_response_checks：A215仅status和updated_at改变，新增唯一check；其他108表、所有旧核对行及上下文/请求原字节、全部非数据库产物字节精确。既有v6/v7、原模型调用、素材和21文件包未改。旧包仍是此前冻结快照，未冒称已包含这次确认；最终组合交付仍待统一制作。

## 验证

新增17项真实编译/HTTP/负例检查通过：同一原模型谱系无新调用的排版、一次确认与原请求重试、真实导出、随后回复变化导致STALE且原历史不变；错类型/改正文/缺基准/无旧词框/无位置变化/同PDF/错版本或PDF/错声明/重复证据均拒绝。实际组件测试覆盖新类型、无需正文diff、类型切换清空与历史标签。TypeScript通过。

当前完整回归1207项后端通过、20既有warnings，24个JS检查集和相关Ruff通过；{full['source_count']}个完整源文件向量在运行期间和封存时精确。总耗时{full['seconds']:.2f}秒。生产构建{build['seconds']:.2f}秒，原源码/dist未改；实际后台316/前端91/构建76向量核验。临时后端8877/前端56581及已知控制台子进程均按精确身份退出，端口释放，原Studio和8891未动。

首轮行为17/组件/类型全部通过，保留共享fixture同名alias引发的Ruff错误；__all__显式导出后在RSTV4目录使用本项目配置通过。从UuMA调用Ruff产生不同import排序规则的观察也保留。只读审计v1将历史request误比为纯HTTP体而失败；原record契约还保存稿件/意见owner。v2要求两个精确owner及全部原body字段，原生确认没有重放。

独立代理只读审核科学守卫隔离、原请求幂等、原历史保全与UI类型切换，未发现本轮实质缺陷；记录审查范围/未覆盖项和精确源码hash。该审查未重复执行父任务的测试或原生动作。其旧历史来源补读设计另行保留为尚未实现的下一步，不计作验收通过。

## 尚未完成

完整结构/引用/素材正向类型归因与对应确认、旧历史无快照的固定来源补读、其他原118命名项及最终同源11流程/组合交付仍待。首屏并行读取仍Failed to fetch，原生重读可恢复意见；根因未证实。旧内联历史点击关闭观察保留。科研语义、科学有效性和外部评审不由软件核对批准。
'''
(dest/'acceptance.md').write_text(report,encoding='utf8')
manifest={p.relative_to(dest).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(dest.rglob('*')) if p.is_file()}
(dest/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
assert all(sha(dest/n)==v['sha256'] and (dest/n).stat().st_size==v['bytes'] for n,v in manifest.items())
receipt={'status':'SEALED_ONE_NATIVE_PRESENTATION_ACK_NOT_ALL11','directory':str(dest),'acceptance_sha256':sha(dest/'acceptance.md'),
 'manifest_sha256':sha(dest/'manifest.json'),'payload_files':len(manifest),'full_backend_passed':1207,'JS_suites':24,
 'source_count':full['source_count'],'check_id':audit['new_check_id'],'all_other108_and_old_records_exact':True,
 'overall118_complete':False,'final11_complete':False,'sealed_at_utc':datetime.now(UTC).isoformat()}
with (repo/'.tmp/scholar-presentation-review-seal-v1.json').open('x',encoding='utf8') as f:json.dump(receipt,f,indent=2)
print(json.dumps(receipt,indent=2))
