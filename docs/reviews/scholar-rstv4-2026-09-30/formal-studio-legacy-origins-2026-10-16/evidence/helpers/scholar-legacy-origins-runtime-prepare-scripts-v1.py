from pathlib import Path
repo=Path(__file__).resolve().parents[1]
full=(repo/'.tmp/scholar-presentation-review-full-v1.py').read_text(encoding='utf8').replace('scholar-presentation-review-full-v1','scholar-legacy-origins-full-v1').replace('scui-presentation-review-full-','scui-legacy-origins-full-')
full=full.replace("'tests/test_studio_presentation_review.py'", "'tests/test_studio_presentation_review.py','tests/test_studio_historical_origins.py','src/rstv4/studio_history_origins.py'")
(repo/'.tmp/scholar-legacy-origins-full-v1.py').write_text(full,encoding='utf8')
build=(repo/'.tmp/scholar-presentation-review-build-v1.py').read_text(encoding='utf8').replace('scholar-presentation-review-build-v1','scholar-legacy-origins-build-v1').replace('scui-presentation-review-build-','scui-legacy-origins-build-')
(repo/'.tmp/scholar-legacy-origins-build-v1.py').write_text(build,encoding='utf8')
