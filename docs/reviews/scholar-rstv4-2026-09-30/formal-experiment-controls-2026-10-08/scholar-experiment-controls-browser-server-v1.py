import hashlib
import json
import socket
import sys
import tempfile
from pathlib import Path

import uvicorn
from rstv4.approval import capture_user_approval
from rstv4.catalog_web import create_app
from rstv4.models import DecisionProposalInput
from rstv4.track_first import TrackFirstService

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo.parent / 'RSTV4/tests'))
from test_track_first_fieldkg import create_hierarchy

root = Path(tempfile.mkdtemp(prefix='scui-plan-browser-')).resolve()
service = TrackFirstService(root)
_, _, track, project = create_hierarchy(service)
method = service.propose_decision(track['track_id'], DecisionProposalInput(
    kind='method', statement='隔离软件实验：读取输入并生成指标', rationale='仅验收软件执行流程'))
capture_user_approval(root, profile='scholar', session_id='software-browser-fixture',
                      message_id='method-fixture', user_message=method['approval_phrase'])
service.approve_decision(method['proposal_id'], 1)
work = root / 'projects' / project['slug']
work.mkdir(parents=True)
(work / 'input.txt').write_text('7', encoding='utf-8')
(work / 'experiment.py').write_text(
    "import json,os\nfrom pathlib import Path\n"
    "p=Path('execution-count.txt')\np.write_text(str(int(p.read_text())+1) if p.exists() else '1')\n"
    "print('actual browser-selected execution '+ 'x'*2200)\n"
    "Path('metrics.json').write_text(json.dumps({'value':int(Path('input.txt').read_text()),'selected_env':os.environ.get('SELECTED_ENV')}))\n",
    encoding='utf-8')
sock = socket.socket()
sock.bind(('127.0.0.1', 0))
sock.listen(128)
metadata = {'root': str(root), 'port': sock.getsockname()[1], 'track_id': track['track_id'],
            'project_id': project['project_id'], 'method_id': method['node_id'],
            'software_approval_fixture': True, 'scientific_approval': False,
            'source_script_sha256': hashlib.sha256((work / 'experiment.py').read_bytes()).hexdigest()}
with (repo / '.tmp/scholar-experiment-controls-browser-v1.json').open('x', encoding='utf-8') as handle:
    json.dump(metadata, handle, ensure_ascii=False, indent=2)
print(json.dumps(metadata, ensure_ascii=False), flush=True)
server = uvicorn.Server(uvicorn.Config(create_app(root), log_level='warning'))
server.run(sockets=[sock])
