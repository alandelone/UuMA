import json
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
observed=json.loads((repo/'.tmp/scholar-template-mapping-observe-final-compensate-template-v1.json').read_text(encoding='utf-8'))
print('OPERATION_FIELDS',list(observed['operations'][0]['operation']))
for item in observed['operations']:
    op=item['operation'];print(op['base_revision'],op.get('kind'),op.get('operation_type'),op['operation_id'],list(json.loads(op['payload_json'])))
for name in ['scholar-template-package-download-native-v1.json','scholar-template-pdf-download-native-v1.json']:
    record=json.loads((repo/'.tmp'/name).read_text(encoding='utf-8'))
    print(name,record.get('outcome'))
    for event in record.get('network',{}).get('events',[]):
        p=event['params']; method=event['method']
        if method=='Network.requestWillBeSent': print(method,p['request']['method'],p['request']['url'])
        elif method=='Network.responseReceived':print(method,p['response']['status'],p['response']['url'],p['response'].get('headers'))
        elif method=='Network.loadingFailed':print(method,p.get('corsErrorStatus'),p.get('errorText'))
full=json.loads((repo/'.tmp/scholar-template-mapping-full-v2.json').read_text(encoding='utf-8'))
print('FULL', {k:v for k,v in full.items() if k not in {'before','after','results','source_before','source_after'}}.keys())
print('RESULTS',[(r.get('name'),r.get('exit_code'),r.get('returncode')) for r in full.get('results',[])])
