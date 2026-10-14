from pathlib import Path
import hashlib,json,subprocess,sys,sqlite3
sys.stdout.reconfigure(encoding='utf-8')
repo=Path.cwd();out=repo/'.tmp/scholar-preview-memory-cleanup-v1';out.mkdir(exist_ok=True)
mission=json.loads((repo/'mission_status.json').read_text(encoding='utf-8'))
for name in ['AGENTS.md','mission_status.json','rules/session-lifecycle.md',mission['gate']['current'],'active-session/HANDOFF.md']:
    path=repo/name;raw=path.read_bytes();logical=path.read_text(encoding='utf-8')
    dest=out/'startup'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
    print(json.dumps({'read':name,'characters':len(logical),'raw_sha256':hashlib.sha256(raw).hexdigest()}))
    if name=='active-session/HANDOFF.md':print(logical[:14000])
def ps(code):
    result=subprocess.run(['powershell','-NoProfile','-Command',code],capture_output=True,encoding='utf-8-sig',check=True)
    assert not result.stderr.strip(),result.stderr
    return json.loads(result.stdout or 'null')
processes=ps('Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine,CreationDate,WorkingSetSize | ConvertTo-Json -Depth 3')
ports=ps('Get-NetTCPConnection -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess | ConvertTo-Json -Depth 3')
index={p['ProcessId']:p for p in processes};nodes=[p for p in processes if p['Name'].lower()=='node.exe']
listeners=[p for p in ports if p['LocalPort'] in [3000,3004,3005,3006,3007,3008,8880,8881]]
chains={}
for port in listeners:
    pid=port['OwningProcess'];chain=[];seen=set()
    while pid in index and pid not in seen:
        seen.add(pid);row=index[pid];chain.append(row);pid=row['ParentProcessId']
    chains[str(port['LocalPort'])]=chain
native=Path('C:/Users/Alandelone/AppData/Local/Temp/scui-citation-source-native-du6504t2/data/catalog.db')
with sqlite3.connect(f'file:{native.as_posix()}?mode=ro',uri=True) as conn:
    conn.row_factory=sqlite3.Row
    tables={r[0]:[dict(x) for x in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
(out/'current-native-tables-before.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2),encoding='utf-8')
receipt={'nodes':nodes,'listeners':listeners,'chains':chains,'node_working_set_bytes':sum(int(p['WorkingSetSize']) for p in nodes)}
(out/'inventory-before.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'node_count':len(nodes),'node_working_set_mib':receipt['node_working_set_bytes']/1024**2,'listeners':listeners,'nodes':nodes,'chains':chains},ensure_ascii=False))
