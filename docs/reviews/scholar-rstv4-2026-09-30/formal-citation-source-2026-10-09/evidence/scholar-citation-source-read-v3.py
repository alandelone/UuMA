from pathlib import Path
import sys
sys.stdout.reconfigure(encoding='utf-8')
r=Path.cwd().parent
chunks={'writing-studio/lib/studio-types.ts':[(210,238)],
 'RSTV4/src/rstv4/studio_read_views.py':[(1,290)],
 'RSTV4/src/rstv4/research_views.py':[(1,115)],
 'RSTV4/tests/test_acquisition_deep_read.py':[(1,115)],
 'RSTV4/tests/test_skeleton_source_outline.py':[(1,150)],
 'RSTV4/src/rstv4/studio_api.py':[(1,135)],
 'RSTV4/src/rstv4/skeleton_outline.py':[(1,145)]}
for name,ranges in chunks.items():
 lines=(r/name).read_text(encoding='utf-8').splitlines()
 print('FILE',name)
 for start,end in ranges:
  print('\n'.join(f'{i+1}: {lines[i]}' for i in range(start-1,min(end,len(lines)))))
