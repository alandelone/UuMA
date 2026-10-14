from pathlib import Path
import hashlib,json
repo=Path.cwd();source=repo/'.tmp/scholar-g02-seal-v1.py';raw=source.read_bytes();context=repo/'.tmp/scholar-g02-seal-snapshot-context-v1';context.mkdir()
(context/'original-sealer.py').write_bytes(raw)
(context/'diagnosis.json').write_text(json.dumps({'failure':'The accessibility receipt was a no-change diff, not a full tree. The original full DOM snapshot and screenshot retain the actual source-button error.','failed_receipt':'.tmp/scholar-g02-partial-native-v1/proof/additional-source-button-failed.txt','complete_snapshot':'.tmp/scholar-g02-partial-native-v1/proof/additional-source-button-failed.dom.txt','guard':'Require the same exact error text in the originally captured complete DOM snapshot. No live product state, original evidence or product assertion changes.','original_sealer_sha256':hashlib.sha256(raw).hexdigest()},indent=2),encoding='utf-8')
code=source.read_text(encoding='utf-8').replace("failure=(proof/'additional-source-button-failed.txt')","failure=(proof/'additional-source-button-failed.dom.txt')")
code=code.replace("for name in ['scholar-g02-partial-native-server-v1.py'","for p in context.rglob('*'):\n    if p.is_file():copy(p,Path('evidence/sealer-snapshot-context-v1')/p.relative_to(context))\nfor name in ['scholar-g02-seal-v1.py','scholar-g02-seal-v2.py','scholar-g02-partial-native-server-v1.py'")
code=code.replace('拒绝后的比较窗口仍打开，一次定位器因此未找到背景文章；','封存首轮读取的是无变化的可访问性差异；改为原来同时保存的完整 DOM 快照，仍要求完全相同的失败文字，原封存工具与失败上下文保留。拒绝后的比较窗口仍打开，定位器因此未找到背景文章；')
assert "failure=(proof/'additional-source-button-failed.dom.txt')" in code
exec(compile(code,__file__,'exec'))
