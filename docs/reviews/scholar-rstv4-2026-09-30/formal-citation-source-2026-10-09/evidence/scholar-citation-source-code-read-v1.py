from pathlib import Path
r=Path.cwd().parent
chunks={'writing-studio/components/studio-workspace.tsx':[(1540,1598),(2078,2140),(2877,2898),(2992,3010)],
        'writing-studio/lib/studio-types.ts':[(312,349)],
        'RSTV4/src/rstv4/studio_context.py':[(1,140)],
        'RSTV4/tests/test_studio_context.py':[(1,255)]}
for name,ranges in chunks.items():
    lines=(r/name).read_text(encoding='utf-8').splitlines()
    print('FILE',name)
    for start,end in ranges:
        print('\n'.join(f'{i+1}: {lines[i]}' for i in range(start-1,min(end,len(lines)))))
source=(r/'RSTV4/src/rstv4/studio.py').read_text(encoding='utf-8')
for name in ['_evidence_by_ids','_reference_snapshot']:
    start=source.index('    def '+name+'(')
    end=source.find('\n    def ',start+1)
    print('BACKEND',name,source[start:end])
