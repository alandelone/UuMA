from pathlib import Path
source = Path(__file__).with_name('scholar-publication-chain-verify-v1.py').read_text(encoding='utf-8')
source = source.replace(".replace(\"f'.tmp/scholar-publication-{phase}-v1'\", \"f'.tmp/scholar-publication-chain-{phase}-v1'\")",
                        ".replace(\"f'.tmp/scholar-publication-{phase}-v1'\", \"f'.tmp/scholar-publication-chain-{phase}-v2'\")")
exec(compile(source, __file__, 'exec'))
