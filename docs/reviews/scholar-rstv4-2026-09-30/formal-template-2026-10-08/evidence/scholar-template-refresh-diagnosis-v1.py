import json
import subprocess
from pathlib import Path

import httpx

repo = Path(__file__).resolve().parents[1]
info = json.loads((repo / '.tmp/scholar-revision-isolated-services-v1.json').read_text())
processes = subprocess.run(['powershell', '-NoProfile', '-Command',
    "Get-CimInstance Win32_Process -Filter \"CommandLine LIKE '%scholar-revision-isolated-services-v1.py%'\" | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine | ConvertTo-Json"],
    capture_output=True, text=True, check=True).stdout
with httpx.Client(timeout=5) as client:
    results = []
    for kind in ['reading', 'revision']:
        prefix = f"http://127.0.0.1:8877/api/manuscripts/{info['manuscripts'][kind]}"
        for suffix in ['/workspace', '/templates/skeleton_c4def72df1572dd62073ba2ac38a556c']:
            response = client.get(prefix + suffix)
            results.append({'kind': kind, 'suffix': suffix, 'status': response.status_code,
                            'response': response.text[:500] if response.status_code != 200 else 'valid'})
data = {'processes': json.loads(processes), 'http': results}
with (repo / '.tmp/scholar-template-refresh-diagnosis-v1.json').open('x', encoding='utf-8') as handle:
    json.dump(data, handle, indent=2)
print(json.dumps(data))
