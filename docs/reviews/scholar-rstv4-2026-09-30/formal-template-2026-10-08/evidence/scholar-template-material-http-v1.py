import hashlib
import io
import json
import zipfile
from pathlib import Path

import httpx

repo = Path(__file__).resolve().parents[1]
info = json.loads((repo / '.tmp/scholar-template-native-fixture-v1.json').read_text(encoding='utf-8'))
db = Path(info['root']) / 'data/catalog.db'
before = db.read_bytes()
prior = json.loads((repo / '.tmp/scholar-studio-shared-native-v2.json').read_text(encoding='utf-8'))
responses = {}
contents = {}
for name, fixture in [('zip','package'),('pdf','pdf')]:
    network = json.loads((repo / f'.tmp/scholar-template-{fixture}-download-native-v1.json').read_text(encoding='utf-8'))['network']
    requests = [e for e in network['events'] if e['method'] == 'Network.requestWillBeSent' and e['params']['request']['method']=='GET' and '/packages/' in e['params']['request']['url']]
    assert len(requests) == 1
    url = requests[0]['params']['request']['url']
    assert url.startswith('http://127.0.0.1:8877/api/manuscripts/manuscript_bd7568923be94a2c8510d176010e4cca/packages/')
    with httpx.Client(timeout=15) as client:
        response = client.get(url,headers={'Origin':'http://127.0.0.1:3004'})
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'http://127.0.0.1:3004'
    contents[name] = response.content
    digest = hashlib.sha256(response.content).hexdigest()
    if name == 'zip':
        package_id = url.split('/packages/')[1].split('/')[0]
        assert digest == prior['old_package_zip_sha256'][package_id]
    responses[name] = {'url':url,'status':200,'bytes':len(response.content),'sha256':digest,
                       'access-control-allow-origin':response.headers['access-control-allow-origin'],
                       'content-type':response.headers.get('content-type'),'browser_verified':False,
                       'browser_request_id':requests[0]['params']['requestId']}
with zipfile.ZipFile(io.BytesIO(contents['zip'])) as bundle:
    members = [name for name in bundle.namelist() if name.endswith('clean-manuscript.pdf')]
    assert len(members) == 1 and bundle.read(members[0]) == contents['pdf']
assert db.read_bytes() == before
assert hashlib.sha256((Path(info['golden_root'])/'data/catalog.db').read_bytes()).hexdigest() == info['golden_database_sha256']
result = {'status':'PASS_EXACT_BROWSER_URL_HTTP_BYTES_AND_CORS_BROWSER_DOWNLOAD_STILL_FAILED',
          'responses':responses,'database_bytes_unchanged':True,'pdf_equals_zip_member':True,
          'browser_download_passed':False,'browser_security_changed':False}
with (repo / '.tmp/scholar-template-material-http-v1.json').open('x',encoding='utf-8') as handle:
    json.dump(result,handle,indent=2)
print(json.dumps(result,ensure_ascii=False))
