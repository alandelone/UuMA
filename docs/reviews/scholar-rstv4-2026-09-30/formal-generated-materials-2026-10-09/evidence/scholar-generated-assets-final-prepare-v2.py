from pathlib import Path
r=Path.cwd()
focused=(r/'.tmp/scholar-generated-assets-focused-v6.py').read_text(encoding='utf-8').replace('scholar-generated-assets-focused-v6.','scholar-generated-assets-focused-v8.')
full=(r/'.tmp/scholar-generated-assets-full-v1.py').read_text(encoding='utf-8').replace('scholar-generated-assets-full-v1.','scholar-generated-assets-full-v2.').replace('scholar-generated-assets-static-v1.','scholar-generated-assets-static-v2.').replace('scholar-generated-assets-full-inline-v1.','scholar-generated-assets-full-inline-v2.')
refresh=(r/'.tmp/scholar-generated-assets-runtime-refresh-v1.py').read_text(encoding='utf-8')
refresh=refresh.replace("assert not [r for r in before['studio_jobs'] if r['manuscript_id']==fixture['manuscript_id']]","owned_jobs=[r for r in before['studio_jobs'] if r['manuscript_id']==fixture['manuscript_id']]\nassert len(owned_jobs)==2 and all(j['status']=='SUCCEEDED' for j in owned_jobs)")
refresh=refresh.replace("str(fixture['processes']['backend'])","str(json.loads((root/'.tmp/scholar-generated-assets-runtime-refresh-v1.json').read_text(encoding='utf-8'))['new_backend_root_pid'])")
refresh=refresh.replace('scholar-generated-assets-backend-runtime-v2.log','scholar-generated-assets-backend-runtime-v3.log')
refresh=refresh.replace("'no_prior_native_material_job':True","'prior_two_jobs_terminal':True")
refresh=refresh.replace("root/'.tmp/scholar-generated-assets-runtime-refresh-v1.json').write_text","root/'.tmp/scholar-generated-assets-runtime-refresh-v2.json').write_text")
for name,source in [('focused-v8',focused),('full-v2',full),('runtime-refresh-v2',refresh)]:
    with (r/('.tmp/scholar-generated-assets-'+name+'.py')).open('x',encoding='utf-8') as handle:handle.write(source)
print('Prepared final affected/full regressions and exact owned runtime refresh; prior jobs terminal guard.')
