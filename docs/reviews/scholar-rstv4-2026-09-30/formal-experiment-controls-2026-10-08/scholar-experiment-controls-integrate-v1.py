from pathlib import Path

path = Path(__file__).resolve().parents[2] / 'RSTV4/src/rstv4/catalog_research_workspaces.js'
source = path.read_text(encoding='utf-8')
marker = "${section('Projects（各自唯一 Owner Track）'"
assert source.count(marker) == 1
source = source.replace(marker, "${section('实施与实验计划', '<div data-track-experiments></div>')}" + marker)
path.write_text(source, encoding='utf-8')
