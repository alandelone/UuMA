from pathlib import Path
source = Path(__file__).with_name('scholar-publication-chain-verify-v1.py').read_text(encoding='utf-8')
source = source.replace("f'.tmp/scholar-publication-chain-{phase}-v1'", "f'.tmp/scholar-publication-chain-{phase}-v3'")
source = source.replace("'tests/test_studio_publication_chain.py',", "'tests/test_skeleton_source_outline.py', 'tests/test_studio_publication_chain.py',")
exec(compile(source, __file__, 'exec'))
