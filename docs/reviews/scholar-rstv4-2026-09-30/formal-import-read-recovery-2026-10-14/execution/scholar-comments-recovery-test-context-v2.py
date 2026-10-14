from pathlib import Path
import hashlib
import json
repo=Path(__file__).resolve().parents[1]
p=repo.parent/'writing-studio/tests/e2e/review-read-recovery.spec.ts'
raw=p.read_bytes()
here=repo/'.tmp/scholar-native-import-v1/comments-read-recovery-v1'
(here/'e2e-spec-v1.raw').open('xb').write(raw)
s=raw.decode('utf-8')
old="const opinion = (page: Page, n = 210) => page.getByText('Original software opinion A' + n, { exact: true });"
new="const opinion = (page: Page, n = 210) => page.getByRole('article').filter({ has: page.getByRole('button', { name: '开始修改意见 A' + n, exact: true }) }).locator('.comment-main > p');"
assert s.count(old)==1
s=s.replace(old,new)
old="await expect(page.getByText('One acknowledged import, never replayed.', { exact: true })).toBeVisible();"
new="await expect(opinion(page, 211)).toHaveText('One acknowledged import, never replayed.');\n    await expect(opinion(page, 211)).toBeVisible();"
assert s.count(old)==1
s=s.replace(old,new)
p.write_bytes(s.encode('utf-8'))
sha=hashlib.sha256(p.read_bytes()).hexdigest()
(here/'e2e-v2-context.json').open('x',encoding='utf-8').write(json.dumps({'before':hashlib.sha256(raw).hexdigest(),'after':sha,'reason':'Exact same text occurs in rendered edited text and collapsed original provenance. Scope assertion to unique semantic comment article, direct edited paragraph. Every original behavior assertion retained.'},indent=2))
runner=repo/'.tmp/scholar-comments-read-e2e-v1.py'
code=runner.read_text().replace("/e2e-v1'","/e2e-v2'").replace("review-read-recovery.config.ts","review-read-recovery-v2.config.ts").replace('40e8bfaff4750f96321300acfd25be1cae4acb598e5f66a335018c32232dc90a',sha)
(repo/'.tmp/scholar-comments-read-e2e-v2.py').open('x',encoding='utf-8').write(code)
print(sha)
