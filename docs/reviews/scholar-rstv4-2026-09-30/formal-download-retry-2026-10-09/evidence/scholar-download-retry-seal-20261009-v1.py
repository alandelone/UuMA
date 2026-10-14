from pathlib import Path
import hashlib
import json
import shutil

root=Path.cwd()
work=root/'.tmp/scholar-download-retry-20261009-v1'
audit=json.loads((work/'audit.json').read_text(encoding='utf-8'))
assert audit['status']=='PASS_BROWSER_DOWNLOAD_FILES_EXACT'
assert len(audit['zip_entries'])==16 and audit['zip_crc_all_passed']
parent=root/'docs/reviews/scholar-rstv4-2026-09-30/formal-intent-correspondence-2026-10-09'
manifest=json.loads((parent/'manifest.json').read_text(encoding='utf-8'))
assert manifest['overall_complete'] is False
for name,digest in manifest['files'].items():
    assert hashlib.sha256((parent/name).read_bytes()).hexdigest()==digest,name
for name,digest in manifest['source_sha256'].items():
    assert hashlib.sha256((root.parent/name).read_bytes()).hexdigest()==digest,name
assert manifest['files']['acceptance.md']=='bc8eb969fe545e4c468307989cdff15d8262ae789d430895e6bd4e367f46b124'
mission=json.loads((root/'mission_status.json').read_text(encoding='utf-8'))
assert mission['stage']=='verification' and mission['gate']['status']=='pending_review'
folder=root/'docs/reviews/scholar-rstv4-2026-09-30/formal-download-retry-2026-10-09'
assert not folder.exists()
shutil.copytree(work,folder/'evidence')
for name in ['scholar-download-retry-audit-20261009-v1.py','scholar-download-retry-seal-20261009-v1.py','scholar-download-retry-handoff-20261009-v1.py']:
    if (root/'.tmp'/name).is_file(): shutil.copyfile(root/'.tmp'/name,folder/'evidence'/name)
report='''# ZIP／PDF原生下载重试验收

2026-10-09，用户已调整IDM设置并明确授权重试。本批下载通过；原118条／11组总验收仍未完成。

## 真实下载及逐字节检查

|入口|实际保存文件|字节数|核对|
|---|---|---:|---|
|成文PDF|C:/Users/Alandelone/Downloads/manuscript.pdf|13,498|与原生成产物SHA256完全一致|
|完整投稿包ZIP|C:/Users/Alandelone/Downloads/submission_package_462feff00b234357a635a3e63254aff4 (1).zip|20,724|16个条目，CRC全部通过，固定清单一致|
|包内PDF独立下载|C:/Users/Alandelone/Downloads/clean-manuscript.pdf|8,144|与ZIP内clean-manuscript.pdf逐字节一致|

PDF摘要：fa294a1fe284baeb7fc3c52a434d4476204e95b9b80067bfcb0f7549fea2f1cb。
ZIP摘要：c8690ba64bb08dbe3935cc2751ae52e15a983842d718c137938609a1bd5a94c4。
包内PDF摘要：8a2b53a55ddab052ec0625475cefbb1c21b1f0229cf70057956bbaecd6e0d754。

所有文件由真实浏览器点击保存，本轮没有用终端HTTP下载代替原生下载。Chrome实际
下载弹窗显示manuscript.pdf完成，随后在Downloads目录验证原文件。浏览器插件的
download事件观察超时不能当作下载失败；实际UI和落地文件构成更强证据。IDM本轮未
出现需要按键的下载窗口，没有代用户修改IDM／浏览器设置或权限。

ZIP原submission_package_462feff00b234357a635a3e63254aff4.zip零字节失败文件完整保留。
本次由Chrome另存为带(1)的新副本，没有覆盖历史失败证据。ZIP清单16个条目无重复，
15个有原打包摘要的文件全部匹配原大小和摘要，manifest.json的稿件、固定生成
版本、第二轮review_round和基线版本也核对一致。空references.bib是原清单记录的
合法零字节内容，不把它与先前失败的零字节整包混淆。

本批使用既有软件验收稿和固定包，成文v3、作者结构r3、第二轮及被审基线保持。
没有生成新学术内容、执行真实模型或作出科学批准。也未进行文件上传、安装、
安全／隐私权限变更或删除。原11组中的输入格式及真实学术全流程继续待验。

## 证据与范围

- [Chrome PDF完成弹窗](evidence/pdf-native-complete.png)
- [投稿包与16个独立文件入口](evidence/package-download-view.png)
- [逐文件摘要与实际保存路径](evidence/audit.json)
- 浏览器DOM、原包API清单、原失败文件基线、ZIP内manifest及三个实际下载副本在evidence目录。

用户当前授权撤销了此前下载暂停，只恢复下载测试；不等于上传授权、扩展权限授权
或科学批准。旧报告中的“暂停／未完成”保持为当时事实，本报告记录此次续验成功。
没有修改产品代码；上批872份封存证据及15份当前源码均重新核验一致。本轮未重复
无变化的1042项全量测试，用实际下载、CRC、原摘要与固定版本核验完成下载检查。

工具限制和失败保留：事件观察超时、CUA未提供listWindows方法、曾用错误猜测的ZIP
控件名等待未匹配。随后读取实际控件、用已安装Computer Use观察真实Chrome弹窗，
再核对实际文件。一次共享session.progress写入错误发生于子命令成功之后，已通过
原生命周期resume恢复；未修改会话引擎。没有把这些失败隐藏或改成通过。

全部118条／G-01至G-11目标继续active，mission仍verification／pending_review。
本批只证明上述实际下载路径和既有软件包字节，不证明整组G-09或全部11组完成。
'''
(folder/'acceptance.md').write_text(report,encoding='utf-8')
result={'status':'NATIVE_ZIP_AND_PDF_DOWNLOAD_PASS_OVERALL_INCOMPLETE','overall_complete':False,
        'g09_complete':False,'all118_all11_scope_retained':True,'user_resumed_download_testing':True,
        'download_testing_paused':False,'scientific_acceptance':False,'files':{
            str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob('*') if p.is_file()}}
(folder/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
entry='\n\n2026-10-09 user expressly resumed ZIP/PDF download tests after their IDM setting change. RealChrome-click PDF13498/ZIP20724/packagePDF8144 bytes verified exact; ZIP16 entries CRC+original hashes+fixed versions PASS; prior0Bzip remains. No code/model/science/permission/upload/delete action. Original118/all11 objective remainsACTIVE/incomplete. Former download pause superseded ONLY for download testing; former reports preserved. Formal evidence: '+str(folder/'acceptance.md')+'.\n'
for name in ['repomemory/findings.md','rules/scholar-native-acceptance.md','stage-gates/04-verification-report.md','docs/reviews/scholar-rstv4-2026-09-30/smoke.md']:
    with (root/name).open('a',encoding='utf-8') as handle: handle.write(entry)
print(json.dumps({'status':result['status'],'report':str(folder/'acceptance.md'),'files':len(result['files']),'report_sha256':result['files']['acceptance.md'],'overall_complete':False}))
