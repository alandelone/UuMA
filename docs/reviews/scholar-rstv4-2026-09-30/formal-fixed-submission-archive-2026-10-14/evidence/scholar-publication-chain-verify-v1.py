from pathlib import Path
import sys

path = Path(__file__).resolve()
source = path.with_name('scholar-publication-verify-v1.py').read_text(encoding='utf-8')
source = source.replace("f'.tmp/scholar-publication-{phase}-v1'", "f'.tmp/scholar-publication-chain-{phase}-v1'")
source = source.replace("elif phase == 'before':", "elif phase == 'chain':\n    args = ['tests/test_studio_publication_chain.py', 'tests/test_studio_submission_events.py', 'tests/test_writing_studio.py', 'tests/test_scholar_acceptance_contracts.py', '-q']\nelif phase == 'before':")
exec(compile(source, __file__, 'exec'))
