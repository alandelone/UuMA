from pathlib import Path
r=Path.cwd().parent
files={'RSTV4/src/rstv4/database.py':[(150,186),(409,450),(556,580),(734,780)],
       'RSTV4/src/rstv4/track_first.py':[(447,485)],
       'RSTV4/src/rstv4/research_context.py':[(343,381)],
       'RSTV4/src/rstv4/research_views.py':[(44,73)],
       'writing-studio/lib/studio-types.ts':[(1,22)]}
for name,ranges in files.items():
    lines=(r/name).read_text(encoding='utf-8').splitlines()
    print('FILE',name)
    for start,end in ranges:print('\n'.join(f'{i+1}: {lines[i]}' for i in range(start-1,min(end,len(lines)))))
source=(r/'RSTV4/src/rstv4/models.py').read_text(encoding='utf-8')
for name in ['EvidenceInput','TrackFirstEvidenceInput']:
    start=source.index('class '+name+'(');end=source.find('\nclass ',start+1)
    print('MODEL',source[start:end])
source=(r/'RSTV4/src/rstv4/studio.py').read_text(encoding='utf-8')
start=source.index('        # One source snapshot feeds');print('REALIZATION',source[start:start+2000])
