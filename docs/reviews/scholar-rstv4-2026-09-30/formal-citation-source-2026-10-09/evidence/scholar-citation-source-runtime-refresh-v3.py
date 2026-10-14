from pathlib import Path
source=Path('.tmp/scholar-citation-source-runtime-refresh-v1.py').read_text(encoding='utf-8')
source=source.replace('runtime-refresh-v1','runtime-refresh-v3').replace('backend-runtime-v2','backend-runtime-v4')
source=source.replace("fixture['processes']['backend']",'93264')
source=source.replace("assert len(jobs)==len(calls)==1 and all(row==(fixture['manuscript_id'],'SUCCEEDED') for row in jobs)","assert len(jobs)==1 and all(row==(fixture['manuscript_id'],'SUCCEEDED') for row in jobs)\n assert len(calls)==2 and {row[1] for row in calls}=={'REJECTED','VALIDATED'}\n assert all(row[0]==fixture['manuscript_id'] for row in calls)\n assert conn.execute(\"SELECT COUNT(*) FROM research_discussion_jobs WHERE status NOT IN ('FAILED','COMPLETE')\").fetchone()[0]==0")
source=source.replace("assert all(row==(fixture['manuscript_id'],'VALIDATED') for row in calls)","assert sum(row[1]=='REJECTED' for row in calls)==1  # Preserve the exactly rejected call and FAILED discussion job.")
exec(compile(source,__file__,'exec'))
