from pathlib import Path
repo=Path(__file__).resolve().parents[1]
source=(repo/'.tmp/scholar-template-full-v2.py').read_text(encoding='utf-8')
source=source.replace('scholar-template-full-v2.','scholar-template-mapping-full-v1.').replace('scholar-template-full-inline-v2.','scholar-template-mapping-full-inline-v1.')
source=source.replace("files=['studio_templates.py'", "files=['studio_structure.py','studio_context.py','studio_read_views.py','studio_templates.py'")
source=source.replace("'tests/test_studio_templates.py'])", "'tests/test_studio_templates.py','tests/test_studio_hierarchy.py'])")
exec(compile(source,__file__,'exec'))
