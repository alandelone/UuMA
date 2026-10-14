from pathlib import Path

path=Path(__file__).with_name('scholar-studio-history-final-v1.py')
source=path.read_text(encoding='utf-8')
source=source.replace('scholar-studio-history-final-v1.json','scholar-review-original-final-v1.json')
source=source.replace('scholar-discussion-navigation-final-v2.json','scholar-collection-original-final-v1.json')
source=source.replace('scholar-database-startup-fixed-baseline-v1.json','scholar-review-post-migration-baseline-v1.json')
source=source.replace("assert before == prior_final['database_sha256'], 'Preserve the previous accepted navigation batch bytes.'",
                      "assert fixed_baseline['old_rows_preserved'] and fixed_baseline['before_database_sha256'] == prior_final['database_sha256'], 'Verify the exact declared v7 migration.'")
source=source.replace('PASS_CURRENT_STUDIO_HISTORY_AND_ALL_RETRIES','PASS_CURRENT_REVIEW_RECOVERY_AND_ORIGINAL_RETRIES')
source=source.replace("('/catalog-research-workspaces.js', 'catalog_research_workspaces.js')", "('/catalog-research-workspaces.js', 'catalog_research_workspaces.js'), ('/catalog-review-workflow.js', 'catalog_review_workflow.js')")
exec(compile(source,str(path),'exec'))
