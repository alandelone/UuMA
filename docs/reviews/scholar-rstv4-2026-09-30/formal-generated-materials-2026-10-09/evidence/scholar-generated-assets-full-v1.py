from pathlib import Path
root=Path.cwd()
source=(root/'.tmp/scholar-intent-correspondence-full-v4.py').read_text(encoding='utf-8')
source=source.replace('scholar-intent-correspondence-full-v4.','scholar-generated-assets-full-v1.').replace(
    'scholar-intent-correspondence-static-v4.','scholar-generated-assets-static-v1.').replace(
    'scholar-intent-correspondence-full-inline-v4.','scholar-generated-assets-full-inline-v1.')
source=source.replace("'src/rstv4/studio_correspondence.py',","'src/rstv4/studio_materials.py', 'src/rstv4/studio_correspondence.py',")
source=source.replace("'tests/test_studio_correspondence.py',","'tests/test_studio_generated_assets.py', 'tests/test_studio_correspondence.py',")
source=source.replace("files=['studio_correspondence.py'","files=['studio_materials.py','studio_correspondence.py'")
exec(compile(source,__file__,'exec'))
