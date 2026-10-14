from pathlib import Path

prior=Path(__file__).with_name('scholar-revision-native-audit-v1.py')
source=prior.read_text(encoding='utf-8')
source=source.replace("output=repo/'.tmp/scholar-revision-native-audit-v1.json'",
                      "output=repo/'.tmp/scholar-revision-native-audit-v2.json'")
source=source.replace("'studio_changes','studio_change_link_state'}",
                      "'studio_changes','studio_change_link_state','studio_comment_response_state'}")
source=source.replace("assert set(changed)<=allowed,changed", """assert set(changed)<=allowed,changed
# Archive and restore each advance the reply-verification revision. Existing rows stay exact.
assert current['studio_comment_response_state']==original['studio_comment_response_state']+[
    {'comment_id':'comment_af961fc8ce894b4cb185308fb1ca52d4','revision':2}
]
""")
exec(compile(source,str(prior),'exec'))
