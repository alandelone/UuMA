import os
import shutil
import subprocess
import time
from pathlib import Path

import httpx

repo = Path(__file__).resolve().parents[1]
python = str(repo.parent / 'RSTV4/.venv/Scripts/python.exe')
os.environ.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
runtime = (repo / '.tmp/scholar-discussion-navigation-runtime-v3.py').read_text(encoding='utf-8')
runtime = runtime.replace('scholar-discussion-navigation', 'scholar-studio-history')
runtime = runtime.replace('fixed_discussion_navigation_preview', 'fixed_studio_history_preview')
runtime = runtime.replace('production_build_discussion_navigation_preview', 'production_build_studio_history_preview')
with (repo / '.tmp/scholar-studio-history-owned-reload-v1.py').open('x', encoding='utf-8') as handle:
    handle.write(runtime)
controller = (repo / '.tmp/scholar-discussion-navigation-native-controller-v1.mjs').read_text(encoding='utf-8')
controller = controller.replace('scholar-discussion-navigation-native-controller-v1.json', 'scholar-studio-history-controller-v1.json')
with (repo / '.tmp/scholar-studio-history-controller-v1.mjs').open('x', encoding='utf-8') as handle:
    handle.write(controller)
final = (repo / '.tmp/scholar-discussion-navigation-final-v2.py').read_text(encoding='utf-8')
final = final.replace('scholar-discussion-navigation-final-v2.json', 'scholar-studio-history-final-v1.json')
final = final.replace('scholar-studio-shared-final-v1.json', 'scholar-discussion-navigation-final-v2.json')
final = final.replace("assert before == fixed_baseline['database_sha256']", "assert before == prior_final['database_sha256'], 'Preserve the previous accepted navigation batch bytes.'\nassert before == fixed_baseline['database_sha256']")
final = final.replace("result['previous_batch_byte_equality_failed_and_preserved'] = True", "result['earlier_pre_fix_startup_byte_equality_failure_retained'] = True")
final = final.replace('PASS_CURRENT_DISCUSSION_NAVIGATION_AND_ALL_RETRIES', 'PASS_CURRENT_STUDIO_HISTORY_AND_ALL_RETRIES')
final = final.replace("assert '定位原对象' in scripts", "assert '当前对象 · 此版本' in scripts and 'studio_discussion' in scripts and '选用这条原来源' in scripts\n    assert '定位原对象' in scripts")
with (repo / '.tmp/scholar-studio-history-final-v1.py').open('x', encoding='utf-8') as handle:
    handle.write(final)
output = repo / '.tmp/scholar-studio-history-runtime-v1.log'
with output.open('x', encoding='utf-8') as log:
    result = subprocess.run([python, str(repo / '.tmp/scholar-studio-history-owned-reload-v1.py')], cwd=repo, stdout=log, stderr=subprocess.STDOUT)
    log.flush()
    if result.returncode:
        print(output.read_text(encoding='utf-8')[-6500:]); raise SystemExit(result.returncode)
    for attempt in range(40):
        try:
            with httpx.Client(timeout=2) as client:
                assert all(client.get(url).status_code == 200 for url in ['http://127.0.0.1:8885/', 'http://127.0.0.1:8874/api/tracks', 'http://127.0.0.1:3000/'])
            break
        except (httpx.HTTPError, AssertionError):
            if attempt == 39: raise
            time.sleep(0.5)
    for command in [[shutil.which('node'), str(repo / '.tmp/scholar-studio-history-controller-v1.mjs')],
                    [shutil.which('node'), str(repo / '.tmp/scholar-studio-history-native-view-v1.mjs')],
                    [python, str(repo / '.tmp/scholar-studio-history-final-v1.py')]]:
        log.write(f'CHECK {Path(command[-1]).name}\n'); log.flush()
        result = subprocess.run(command, cwd=repo, stdout=log, stderr=subprocess.STDOUT)
        log.write(f'Exit: {result.returncode}\n'); log.flush()
        if result.returncode:
            print(output.read_text(encoding='utf-8')[-7500:]); raise SystemExit(result.returncode)
print(output.read_text(encoding='utf-8')[-7500:])
