import json
from pathlib import Path
from rstv4.approval import capture_user_approval

repo = Path(__file__).resolve().parents[1]
meta = json.loads((repo / '.tmp/scholar-experiment-controls-browser-v2.json').read_text())
assert meta['software_approval_fixture'] and not meta['scientific_approval']
result = capture_user_approval(meta['root'], profile='scholar',
                              session_id='software-pinned-browser-fixture',
                              message_id='software-plan-pinned-fixture',
                              user_message='APPROVE proposal_07c71ebcc6474741a3956e84504c7ef4')
assert result is not None
print('Captured software fixture grant only')
