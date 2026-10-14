from pathlib import Path
r=Path.cwd().parent
chunks={'RSTV4/src/rstv4/catalog_web.py':[(842,886)],'RSTV4/src/rstv4/fieldkg_workspace.py':[(133,207)],
        'RSTV4/tests/test_fieldkg_workspace.py':[(1,98)],'RSTV4/tests/test_skeleton_source_outline.py':[(1,81)],
        'RSTV4/src/rstv4/studio_api.py':[(336,382),(403,448)]}
for name,ranges in chunks.items():
    lines=(r/name).read_text(encoding='utf-8').splitlines();print('FILE',name)
    for start,end in ranges:print('\n'.join(f'{i+1}: {lines[i]}' for i in range(start-1,min(end,len(lines)))))
