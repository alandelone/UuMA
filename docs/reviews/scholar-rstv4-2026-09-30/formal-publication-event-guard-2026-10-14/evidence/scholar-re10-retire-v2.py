from pathlib import Path

path = Path(__file__).resolve()
code = path.with_name('scholar-re10-retire-v1.py').read_text(encoding='utf-8')
code = code.replace("'.tmp/scholar-re10-retire-v1'", "'.tmp/scholar-re10-retire-v2'")
old = "    frontpids.update(p.pid for p in launcher.children(recursive=True))"
new = '''    for child in launcher.children(recursive=True):
        if child.name().casefold() == 'conhost.exe':
            assert Path(child.cwd()).resolve() == Path(os.environ['WINDIR']).resolve()
            continue  # Windows console host is not an application process to terminate.
        assert child.name().casefold() in {'node.exe', 'cmd.exe'}
        frontpids.add(child.pid)'''
assert code.count(old) == 1
code = code.replace(old, new)
exec(compile(code, __file__, 'exec'))
