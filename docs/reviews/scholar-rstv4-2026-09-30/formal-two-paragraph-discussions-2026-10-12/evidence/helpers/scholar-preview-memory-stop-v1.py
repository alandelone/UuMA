from pathlib import Path
import json,subprocess,sys,sqlite3,hashlib
sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();out=repo/'.tmp/scholar-preview-memory-cleanup-v1'
before=json.loads((out/'inventory-before.json').read_text(encoding='utf-8'))
expected={3000:'CodeSpace_Local\\writing-studio\\node_modules\\vinext',3004:'scui-material-download-build-p5pwps28',3005:'scui-source-hierarchy-build-w7ni3d4n',3006:'scui-intent-correspondence-build-vcvedpss',3007:'scui-generated-materials-build-kkdc1yik'}
ownership={3000:'.tmp/scholar-ui-fixes-services.json',3004:'.tmp/scholar-material-download-runtime-final-v1.json',3005:'.tmp/scholar-source-hierarchy-modal-runtime-v2.json',3006:'.tmp/scholar-intent-correspondence-native-v1.json',3007:'.tmp/scholar-generated-assets-native-v1.json'}
selected=[]
for port,marker in expected.items():
    chain=before['chains'][str(port)];receipt=json.loads((repo/ownership[port]).read_text(encoding='utf-8'))
    assert marker.lower() in chain[0]['CommandLine'].lower()
    if port==3000:assert receipt['owned_processes']['frontend']==chain[0]['ProcessId']
    else:
        assert marker.lower() in json.dumps(receipt).lower()
        assert len(chain)==4 and all(str(port) in row['CommandLine'] for row in chain)
    selected.extend(chain)
assert len(selected)==17 and len({p['ProcessId'] for p in selected})==17
preserve=before['chains']['3008']+before['chains']['8881']+before['chains']['8880']
assert not {p['ProcessId'] for p in selected}&{p['ProcessId'] for p in preserve}
def ps(code):
    r=subprocess.run(['powershell','-NoProfile','-Command',code],capture_output=True,encoding='utf-8-sig',check=True)
    assert not r.stderr.strip(),r.stderr
    return json.loads(r.stdout or 'null')
def snapshot():return ps('Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine,CreationDate,WorkingSetSize | ConvertTo-Json -Depth 3')
fresh=snapshot();index={p['ProcessId']:p for p in fresh}
for row in [p for p in selected if p['ProcessId'] in index]+preserve:
    now=index[row['ProcessId']]
    assert all(now[key]==row[key] for key in ['ProcessId','ParentProcessId','Name','CommandLine','CreationDate'])
target_ids={p['ProcessId'] for p in selected}
console_hosts=[p for p in fresh if p['ParentProcessId'] in target_ids and p['ProcessId'] not in target_ids]
assert len(console_hosts)<=5
assert all(p['Name'].lower()=='conhost.exe' and p['CommandLine']==r'\??\C:\Windows\system32\conhost.exe 0x4' for p in console_hosts), 'Unexpected descendant: re-inspect before stopping'
assert not any(p['ParentProcessId'] in {x['ProcessId'] for x in console_hosts} for p in fresh)
held_files={}
for name in ['.tmp/scholar-ui-fixes-services.json','.tmp/scholar-source-hierarchy-runtime-v1.json','.tmp/scholar-intent-correspondence-native-v1.json','.tmp/scholar-generated-assets-native-v1.json']:
    root=Path(json.loads((repo/name).read_text(encoding='utf-8'))['root'])
    for path in root.rglob('*.db'):
        held_files[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
(out/'stop-plan.json').write_text(json.dumps({'selected':selected,'preserved':preserve,'ownership_receipts':ownership,'console_hosts_left_to_exit_with_owned_parent':console_hosts,'retained_database_sha256':held_files},indent=2),encoding='utf-8')
stopped=[]
for row in selected:
    pid=row['ProcessId'];epoch=int(row['CreationDate'].split('(')[1].split(')')[0]);cmd=row['CommandLine'].replace("'","''")
    code=f"$taskProcess=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}'; if ($null -eq $taskProcess) {{ '{{\"state\":\"ALREADY_EXITED\"}}' }} else {{ if ($taskProcess.CommandLine -cne '{cmd}' -or $taskProcess.ParentProcessId -ne {row['ParentProcessId']} -or ([DateTimeOffset]$taskProcess.CreationDate).ToUnixTimeMilliseconds() -ne {epoch}) {{ throw 'Process identity changed; refusing stop' }}; Stop-Process -Id {pid} -Force -ErrorAction Stop; '{{\"state\":\"STOPPED_VERIFIED_IDENTITY\"}}' }}"
    result=ps(code);stopped.append({'pid':pid,**result})
    (out/'stop-actions.json').write_text(json.dumps(stopped,indent=2),encoding='utf-8')
after=snapshot();after_index={p['ProcessId']:p for p in after}
assert not target_ids&after_index.keys()
for row in preserve:
    now=after_index[row['ProcessId']]
    assert all(now[key]==row[key] for key in ['ProcessId','ParentProcessId','Name','CommandLine','CreationDate'])
ports=ps('Get-NetTCPConnection -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess | ConvertTo-Json -Depth 3')
assert not any(p['LocalPort'] in expected for p in ports)
assert any(p['LocalPort']==3008 and p['OwningProcess']==104724 for p in ports)
assert any(p['LocalPort']==8881 and p['OwningProcess']==104544 for p in ports)
assert all(Path(path).exists() and hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest for path,digest in held_files.items())
native=Path('C:/Users/Alandelone/AppData/Local/Temp/scui-citation-source-native-du6504t2/data/catalog.db')
with sqlite3.connect(f'file:{native.as_posix()}?mode=ro',uri=True) as conn:
    conn.row_factory=sqlite3.Row
    tables={r[0]:[dict(x) for x in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
assert tables==json.loads((out/'current-native-tables-before.json').read_text(encoding='utf-8'))
nodes_after=[p for p in after if p['Name'].lower()=='node.exe']
removed_node_ids={p['ProcessId'] for p in selected if p['Name'].lower()=='node.exe'}
assert {p['ProcessId'] for p in before['nodes']}-removed_node_ids <= {p['ProcessId'] for p in nodes_after}
receipt={'status':'PASS_OWNED_IDLE_PREVIEWS_STOPPED','stopped_or_parent_exited_process_ids':sorted(target_ids),'stop_actions':stopped,'stopped_node_count':len(removed_node_ids),'closed_preview_ports':list(expected),'removed_process_working_set_bytes_at_initial_inventory':sum(int(p['WorkingSetSize']) for p in selected),'removed_node_working_set_bytes_at_initial_inventory':sum(int(p['WorkingSetSize']) for p in selected if p['Name'].lower()=='node.exe'),'remaining_node_count':len(nodes_after),'current3008_8881_and_material8880_same_identity':True,'current_native109tables_exact':True,'old_native_database_bytes_exact':True,'retained_database_sha256':held_files,'no_files_or_directories_deleted':True,'all_other_before_node_processes_preserved':True}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps(receipt),flush=True)
