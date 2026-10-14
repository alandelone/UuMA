from pathlib import Path
import hashlib
import json
import shutil
import zipfile

root=Path.cwd()
out=root/'.tmp/scholar-download-retry-20261009-v1'
downloads=Path('C:/Users/Alandelone/Downloads')
rows=json.loads((out/'package-api-before.json').read_text(encoding='utf-8'))
package=next(r for r in rows if r['package_id']=='submission_package_462feff00b234357a635a3e63254aff4')
assert package['integrity_status']=='RECORDED_AT_PACKAGING'
expected={row['name']:row for row in package['files']}
archive_path=downloads/'submission_package_462feff00b234357a635a3e63254aff4 (1).zip'
assert archive_path.is_file() and archive_path.stat().st_size==20724
assert (downloads/'submission_package_462feff00b234357a635a3e63254aff4.zip').read_bytes()==b''
assert zipfile.is_zipfile(archive_path)
checks=[]
with zipfile.ZipFile(archive_path) as archive:
    assert archive.testzip() is None
    assert len(archive.namelist())==len(set(archive.namelist()))==16
    assert set(archive.namelist())==set(expected)
    manifest=json.loads(archive.read('manifest.json'))
    for name,row in expected.items():
        content=archive.read(name)
        digest=hashlib.sha256(content).hexdigest()
        if name!='manifest.json':
            assert len(content)==row['size_bytes'],name
            assert digest==row['sha256'],name
        checks.append({'name':name,'bytes':len(content),'sha256':digest,'original_packaging_digest_verified':name!='manifest.json'})
    fixed_pdf=archive.read('clean-manuscript.pdf')
    pdf_path=downloads/'clean-manuscript.pdf'
    assert pdf_path.read_bytes()==fixed_pdf
    assert fixed_pdf.startswith(b'%PDF-') and len(fixed_pdf)==8144
    author_structure=json.loads(archive.read('author-structure.json'))
    generated=json.loads(archive.read('generated.json'))
    assert author_structure['manuscript_id']==package['manuscript_id']
    assert generated['input_revision']==package['input_revision']==3
    assert manifest['generated_version_id']==package['generated_version_id']
    assert manifest['review_round_id']==package['review_round_id']
    assert manifest['baseline_manuscript_version_id']==package['baseline_manuscript_version_id']
    assert package['round_number']==2
generated_pdf=downloads/'manuscript.pdf'
assert generated_pdf.stat().st_size==13498
assert hashlib.sha256(generated_pdf.read_bytes()).hexdigest()=='fa294a1fe284baeb7fc3c52a434d4476204e95b9b80067bfcb0f7549fea2f1cb'
for path in [archive_path,pdf_path,generated_pdf]:
    shutil.copyfile(path,out/path.name)
(out/'zip-inner-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
receipt={'status':'PASS_BROWSER_DOWNLOAD_FILES_EXACT','user_resumed_download_testing':True,
         'generated_pdf':{'path':str(generated_pdf),'bytes':13498,'sha256':hashlib.sha256(generated_pdf.read_bytes()).hexdigest()},
         'downloaded_zip':{'path':str(archive_path),'bytes':20724,'sha256':hashlib.sha256(archive_path.read_bytes()).hexdigest()},
         'package_pdf':{'path':str(pdf_path),'bytes':8144,'sha256':hashlib.sha256(fixed_pdf).hexdigest()},
         'zip_entries':checks,'zip_crc_all_passed':True,'fixed_packaged_versions_exact':True,
         'old_zero_byte_failed_file_preserved':True,'idm_popup_press_required_this_retry':False,
         'browser_download_event_observation_timed_out_but_actual_file_and_native_ui_prove_pdf':True,
         'files_were_saved_by_real_browser_clicks_not_shell_download':True,
         'scientific_acceptance':False,'all118_all11_overall_complete':False}
(out/'audit.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k!='zip_entries'},ensure_ascii=False))
