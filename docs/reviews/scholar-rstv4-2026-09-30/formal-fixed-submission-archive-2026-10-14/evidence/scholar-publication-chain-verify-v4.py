from pathlib import Path
source = Path(__file__).with_name('scholar-publication-chain-verify-v3.py').read_text(encoding='utf-8')
source = source.replace("f'.tmp/scholar-publication-chain-{phase}-v3'", "f'.tmp/scholar-publication-chain-{phase}-v4'")
exec(compile(source, __file__, 'exec'))
