from pathlib import Path

repo = Path(__file__).resolve().parents[1]
finding = '\n\n### 2026-10-09 source hierarchy focused failure 1\n\nThe first focused run retained `.tmp/scholar-source-hierarchy-focused-v1.log`: 9 failed, 56 passed. All nine failed before the new preview because the outline reader used `page_number` on a persisted skeleton unit, whose historical column is `page_idx`. Native publication already stores the one-based parser page number in that old column. Corrected the reader adapter to map that exact column back to `page_number`; no source data/schema assertion or test requirement was weakened. Source hierarchy remains software-only and downloads remain paused.\n'
with (repo / 'repomemory/findings.md').open('a', encoding='utf-8') as f:
    f.write(finding)
source = (repo / '.tmp/scholar-source-hierarchy-focused-v1.py').read_text(encoding='utf-8')
(repo / '.tmp/scholar-source-hierarchy-focused-v2.py').write_text(source.replace('focused-v1', 'focused-v2'), encoding='utf-8')
print('PASS retained first failure and corrected adapter context')
