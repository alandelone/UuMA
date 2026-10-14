import hashlib
import json
from pathlib import Path

repo=Path(__file__).resolve().parents[1]
path=repo.parent/'RSTV4/src/rstv4/studio_read_views.py'
target=repo/'.tmp/scholar-hierarchy-before-v1/RSTV4/src/rstv4/studio_read_views.py'
assert not target.exists()
target.write_bytes(path.read_bytes())
with (repo/'.tmp/scholar-hierarchy-readviews-before-v1.json').open('x',encoding='utf-8') as handle:
    json.dump({'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()},handle)
text='''

2026-10-08 explicit author hierarchy and L2 contract: additive parent_section_id represents actual author-selected Section/Subsection ancestry in the existing ordered section records, without inferring physical hierarchy from L1-L4 or paragraph groups. Preserve preorder, stable IDs, whole subtree move/delete/fold, historical snapshot and compensating Undo. Current article output supports five heading levels Section through Subparagraph; deeper/cyclic/foreign/noncontiguous parents must be rejected explicitly. A parent may own child sections without owning paragraphs. Template replacement keeps entire selected subtree and old author content visibly unplaced; no implicit content mapping. Author argument_relations are a separate graph of paragraph/Intent/Thought endpoints plus custom relation/condition, not containment, research approval or evidence. Validate owner/endpoints/unique IDs; moving preserves edges, explicit deletion removes only incident edges in the new author snapshot, Undo restores both. Writing inputs freeze both relation endpoints; immutable old flat generated artifacts keep identical bytes and headings. These changes do not close all11 or approve a mission gate.
'''
for name in ['stage-gates/03-execution-brief.md','rules/scholar-native-acceptance.md']:
    with (repo/name).open('a',encoding='utf-8') as handle:handle.write(text)
