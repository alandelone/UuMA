from pathlib import Path
from datetime import datetime, UTC
import difflib, hashlib, json, shutil

repo = Path(__file__).resolve().parents[1]
read = lambda p: json.loads(p.read_text(encoding='utf8'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
full_dir = repo/'.tmp/scholar-frozen-origin-full-v1'
full = read(full_dir/'receipt.json')
assert full['status'] == 'PASS' and not full['changed_during_run'] and full['commands_completed'] == full['commands_expected'] == 26
assert '1190 passed, 20 warnings' in (full_dir/'check-00.log').read_text(encoding='utf8')
assert all(sha(Path(x['log'])) == x['log_sha256'] and x['exit_code'] == 0 for x in full['results'])
for name,h in read(Path(full['source_before'])).items():
    assert sha(Path(name)) == h
runtime = repo/'.tmp/scholar-frozen-origin-native-v1'
audit = read(runtime/'final-readonly-audit.json')
assert audit['status'] == 'PASS_FIXED_V7_TWO_NATIVE_THOUGHTS_AND_LEGACY_BOUNDARY'
assert audit['all110_and_non_sidecar_bytes_exact'] and audit['owned_processes_stopped']
focused = read(repo/'.tmp/scholar-frozen-origin-v1/focused-v2-receipt.json')
assert all(x['exit_code'] == 0 for x in focused)
build = read(repo/'.tmp/scholar-frozen-origin-build-v1.json')
assert build['status'] == 'PASS' and build['original_source_and_dist_unchanged']
dest = repo/'docs/reviews/scholar-rstv4-2026-09-30/formal-studio-frozen-origins-2026-10-16'
dest.mkdir()

def copy(source, relative):
    target = dest/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    assert not target.exists()
    shutil.copyfile(source,target)
    assert sha(source) == sha(target)

for folder in [repo/'.tmp/scholar-frozen-origin-v1', runtime, full_dir]:
    for p in folder.iterdir():
        if p.is_file():
            copy(p, 'evidence/'+folder.name+'/'+p.name)
for pattern in ['scholar-frozen-origin-*.py','scholar-frozen-origin-build-v1.json','scholar-frozen-origin-build-v1.log']:
    for p in (repo/'.tmp').glob(pattern):
        copy(p, 'evidence/helpers/'+p.name)
names = ['RSTV4/src/rstv4/studio_revision_mapping.py','RSTV4/tests/test_studio_frozen_origins.py',
         'writing-studio/components/studio-response-review.tsx','writing-studio/lib/studio-types.ts',
         'writing-studio/tests/unit/studio-response-review.cjs']
patch, digests = [], {}
for name in names:
    p = repo.parent/name
    copy(p,'source/'+name)
    backup = repo/'.tmp/scholar-frozen-origin-v1/before'/name
    old = backup.read_text(encoding='utf8') if backup.exists() else ''
    if not backup.exists():
        vector = read(repo/'.tmp/scholar-frozen-origin-v1/source-before.json')
        if str(p) in vector:
            # The original frontend test is retained by the previous sealed layout run.
            full_old = repo/'docs/reviews/scholar-rstv4-2026-09-30/formal-studio-layout-native-2026-10-15/evidence/scholar-layout-full-v2/source-before.json'
            assert read(full_old)[str(p)] == vector[str(p)]
            # Show this file as a current complete source; do not invent absent before bytes.
            digests[name] = {'sha256':sha(p),'bytes':p.stat().st_size,'before_sha256':vector[str(p)],'before_bytes_not_retained_here':True}
            continue
    patch.extend(difflib.unified_diff(old.splitlines(True),p.read_text(encoding='utf8').splitlines(True),
                                    fromfile='a/'+name if backup.exists() else '/dev/null',tofile='b/'+name))
    digests[name] = {'sha256':sha(p),'bytes':p.stat().st_size,'before_sha256':sha(backup) if backup.exists() else None}
(dest/'product-change.patch').write_text(''.join(patch),encoding='utf8')
(dest/'source-digests.json').write_text(json.dumps(digests,indent=2),encoding='utf8')
report = f'''# Studio 固定原思想反查与仅引用变化验收

共享成文句子现能分别展开其原 Thought，并显示整个原 Intent 的完整有序思想；仅引用身份、添加、删除或顺序变化不能证明科学正文文字已修改。11组整体验收仍未完成，本批不批准科研内容或阶段门。

## 产品行为

从已经验证的目标成文对应作者原稿版本读取原 Section、Paragraph、Intent 和 Thought，不读取当前编辑器或模板投影后替代的文本。证据携带稿件、成文ID/版本、输入revision、原对象ID/标题、完整Thought文本及整个Intent有序思想。相同共享句子保留不同Thought行。原文不截断，展开时突出当前Thought，查看来源不选择证据。

新核对上下文按原流程摘要并追加保存这些快照；历史界面只读当时context。稿件/成文/revision/思想不匹配的来源拒绝显示。旧记录没有快照时明确提示不可验证，不从可变原稿补写；旧request_id重试仍返回原记录。无schema迁移。

比较已记录的完整句子时，引用标记变化单列CITATION_ONLY/change_kind=CITATION，保留最终PDF真实页/行和词框，supports_scientific_text_modification=false；既有MODIFIED确认拒绝该行。缺少原句记录且不能证明保留时明确未知。新段落从空基准比较可证实文字增加。该比较是机械文字观察，不是语义或科研判断。

## 实际验收

保留复杂原分支scui-complex-native-qjbemsgz，作者r86、成文v7及既有投稿包完全复用。实际生产新构建{build['seconds']:.2f}秒通过，源码和原dist不变。只读预览的23次实际请求保留；模型、工作任务、作者修改和新核对提交均禁止。未重新生成、打包、跑GPU/QuickRead/深读、修改预算或重新测试IDM。

原生A212选取原回复UTF16[24,151]，两个共享句子相同PDF词框，来源分别thought_author_1与thought_5f3edebed89d482cb0b2d9d42c4930d8。分别展开完整原Intent、完整两个Thought，正确突出对应思想，固定v7/r86。六行来源逐字段等于确切r86，宽1280与760实际检查；760对话框730px、来源670px，全文无横向溢出、零误勾。截图已实际查看。

原生独立历史入口仍显示原A212/v6核对和两段声明，五条选用证据明确提示旧快照未记录；没有把v7/r86伪写进旧v6。新增核对的快照持久化、后改原稿不影响原记录及原request_id重试由实际编译服务测试验证；该新增历史路径的前端由真实组件控制测试覆盖，没有声称本轮在保留原生分支新建check。

真实源文献/PDF/编译测试在相同编号[1]和相同可见正文下替换原引用身份，实际页行/词框存在，返回CITATION_ONLY，服务拒绝把它确认为正文改动，核对历史仍空。另8组引用增删/重排、正文/标点/否定变化边界及未知基准检查通过。原生A214的Beta仍为文字已变：独立读取固定两版证明旧文“Beta software paragraph cites original page 1 …”与新文“Beta software original paragraph …”确实不同，不能伪称这个旧夹具仅换引用；素材正向归因仍未完成。

## 完整验证与保全

47项相关后端检查、真实组件来源/历史/Unicode/冲突与重试检查、TypeScript与Ruff通过。当前完整回归1190项后端通过、20项既有warnings，24个JS检查集和相关Ruff通过；{full['source_count']}个完整源码向量在运行期间和封存时逐字节保持。完整后端耗时见原日志，全部检查总耗时{full['seconds']:.2f}秒。当前后端315、前端91、构建76向量一致。

原生前后全部110表及非数据库产物字节一致，旧v6/v7、调用、核对、素材、ZIP均未重写。仅自己的后端8877/前端54375和已知控制台进程按出生时间、命令、目录核实后关闭，端口已释放；原Studio和用户要求保留8891页未动。

保留首轮44通过/3失败：引用移除残留空格是真缺陷，已修复；新测试漏传venue和控制测试文本辅助器忽略数字子节点为测试执行上下文，修正后保留原完整断言通过。初次预览使用缺psutil的UuMA环境，在服务/目录创建前失败，随后使用已有验收环境。子代理因用量限制退出，主代理完成实现与验证。

## 仍待验收

首屏并行读取仍出现Failed to fetch，页面提供的重新读取可恢复意见；根因未证实。窄屏恢复后点击内联历史入口使对话框关闭，保留观察，不算内联历史通过；独立历史入口正常。旧历史无快照的固定原文补充读取仍待；结构/素材/引用的正向完整类型归因、排版独立回复确认、其他原118命名项及最终同源11组流程均未通过。科研语义和科学结论不由软件夹具批准。
'''
(dest/'acceptance.md').write_text(report,encoding='utf8')
manifest = {p.relative_to(dest).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size}
            for p in sorted(dest.rglob('*')) if p.is_file()}
(dest/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
assert all(sha(dest/n) == v['sha256'] and (dest/n).stat().st_size == v['bytes'] for n,v in manifest.items())
receipt = {'status':'SEALED_FROZEN_THOUGHT_ORIGINS_AND_CITATION_ONLY_NOT_ALL11',
           'directory':str(dest),'acceptance_sha256':sha(dest/'acceptance.md'),'manifest_sha256':sha(dest/'manifest.json'),
           'payload_files':len(manifest),'full_backend_passed':1190,'JS_suites':24,
           'source_count':full['source_count'],'all110_and_old_bytes_exact':True,
           'overall118_complete':False,'final11_complete':False,'sealed_at_utc':datetime.now(UTC).isoformat()}
with (repo/'.tmp/scholar-frozen-origin-seal-v1.json').open('x',encoding='utf8') as handle:
    json.dump(receipt,handle,indent=2)
print(json.dumps(receipt,indent=2))
