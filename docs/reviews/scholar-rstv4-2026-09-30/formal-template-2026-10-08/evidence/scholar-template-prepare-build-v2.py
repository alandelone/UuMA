from pathlib import Path

repo = Path(__file__).resolve().parents[1]
source = (repo / '.tmp/scholar-template-build-v1.py').read_text(encoding='utf-8')
source = source.replace("root = Path(tempfile.mkdtemp(prefix='scui-template-build-'))", "container = Path(tempfile.mkdtemp(prefix='scui-template-build-'))\nroot = container / 'writing-studio'")
source = source.replace("assert root.parent == Path(tempfile.gettempdir()) and root.name.startswith('scui-template-build-')", "assert container.parent == Path(tempfile.gettempdir()) and container.name.startswith('scui-template-build-')\nshared = container / 'RSTV4/src/rstv4/catalog_research_chat.js'\nshared.parent.mkdir(parents=True)\nshutil.copyfile(repo.parent / 'RSTV4/src/rstv4/catalog_research_chat.js', shared)\nassert sha(shared) == sha(repo.parent / 'RSTV4/src/rstv4/catalog_research_chat.js')")
source = source.replace('scholar-template-build-v1.', 'scholar-template-build-v2.')
with (repo / '.tmp/scholar-template-build-v2.py').open('x', encoding='utf-8') as handle:
    handle.write(source)
for file in ['rules/scholar-native-acceptance.md', 'repomemory/findings.md']:
    path = repo / file
    assert path.exists()
    with path.open('a', encoding='utf-8') as handle:
        handle.write('\n\n2026-10-08 template build context: isolated frontend copies must retain the declared sibling RSTV4/src/rstv4/catalog_research_chat.js import with exact source bytes. Build v1 failed unresolved import before runtime and preserved the original source/dist; successor v2 restores the directory contract in a new isolated container, without altering product imports or assertions.\n')
