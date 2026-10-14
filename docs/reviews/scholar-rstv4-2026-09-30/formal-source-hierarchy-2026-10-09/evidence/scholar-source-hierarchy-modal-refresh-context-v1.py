from pathlib import Path

repo = Path(__file__).resolve().parents[1]
findings = (repo / 'repomemory/findings.md').read_text(encoding='utf-8')
with (repo / 'repomemory/findings.md').open('a', encoding='utf-8') as f:
    f.write('\n\n### 2026-10-09 modal runtime refresh encoding context\n\nBuild v2 and all three modal static checks PASS, but refresh-v1 stopped before any process mutation: the parent repository Python defaulted to GBK while captured PowerShell process metadata contained UTF-8. UnicodeDecodeError made stdout None, so JSON ownership validation failed before Stop-Process. Preserve the successful build instead of rebuilding; set UTF-8 explicitly for metadata stdout and run the continuation with Python -X utf8. Do not weaken command/path/creation-time/ancestry/listener guards. Read full findings and reuse saved build only after successful exact fresh ownership validation.\n')
with (repo / 'rules/scholar-native-acceptance.md').open('a', encoding='utf-8') as f:
    f.write('\n\nWindows ownership/process metadata may contain non-ASCII command lines. Set the child PowerShell stdout encoding explicitly to UTF-8, decode as UTF-8, and use Python -X utf8 for acceptance helpers. A decode failure stops before maintenance; retain a successful build and resume validation rather than rebuilding or weakening process guards.\n')
source = (repo / '.tmp/scholar-source-hierarchy-modal-refresh-v1.py').read_text(encoding='utf-8')
continuation = source[source.index('snapshot_command ='):]
continuation = continuation.replace('snapshot_command = "', 'snapshot_command = "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); ', 1)
continuation = continuation.replace('capture_output=True, text=True, check=True', "capture_output=True, text=True, encoding='utf-8', check=True")
continuation = continuation.replace('modal-runtime-before-v1', 'modal-runtime-before-v2').replace('modal-frontend-runtime-v1', 'modal-frontend-runtime-v2').replace('modal-runtime-v1', 'modal-runtime-v2')
prefix = "import hashlib, json, os, socket, subprocess, time\nfrom pathlib import Path\nrepo=Path(__file__).resolve().parents[1]\nfront=repo.parent/'writing-studio'\nruntime_info=json.loads((repo/'.tmp/scholar-source-hierarchy-runtime-v1.json').read_text(encoding='utf-8'))\nbuild_info=json.loads((repo/'.tmp/scholar-source-hierarchy-build-v2.json').read_text(encoding='utf-8'))\nassert build_info['status']=='PASS'\n"
(repo / '.tmp/scholar-source-hierarchy-modal-refresh-v2.py').write_text(prefix + continuation, encoding='utf-8')
print(f'PASS UTF-8 context corrected; entire findings read ({len(findings)} characters); reuse build v2')
