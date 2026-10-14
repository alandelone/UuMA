from pathlib import Path
code = Path('.tmp/scholar-g03-startup-v1.py').read_text(encoding='utf-8')
code = code.replace('scholar-g03-startup-v1', 'scholar-g04-startup-v1').replace('scholar-g02-seal-v1.json', 'scholar-g03-seal-v1.json')
code = code.replace("len(manifest['files'])==109", "len(manifest['files'])==116").replace('previous109_sealed_files_exact', 'previous116_sealed_files_exact').replace('previous12_source_files_current_exact', 'previous15_source_files_current_exact')
code = code.replace("'g03_definition':groups[2]", "'g04_definition':groups[3]").replace("logical[:15000]", "logical[:7500]")
exec(compile(code, __file__, 'exec'))
