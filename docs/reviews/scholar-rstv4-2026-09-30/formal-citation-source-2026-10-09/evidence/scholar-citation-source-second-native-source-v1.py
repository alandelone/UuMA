from pathlib import Path
import hashlib,json,sys
repo=Path.cwd();fixture=json.loads((repo/'.tmp/scholar-citation-source-native-v1.json').read_text(encoding='utf-8'));root=Path(fixture['root'])
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject,DictionaryObject,NameObject
from rstv4.acquisition import AcquisitionService
from rstv4.database import transaction
from rstv4.models import TrackFirstEvidenceInput
from rstv4.research_views import skeleton_source
from rstv4.studio import StudioService
service=StudioService(root);ms=fixture['manuscript_id'];db=service.db_path
assert service.get_workspace(ms)['active_generated_version_id']=='manuscript_version_7ea00b67724045db8db687b46beb1530'
pdf=root/'other-software-original.pdf';assert not pdf.exists()
writer=PdfWriter();page=writer.add_blank_page(width=595,height=842)
font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
text='New original software source body.';stream=DecodedStreamObject();stream.set_data(f'BT /F1 12 Tf 72 740 Td (Other software source) Tj 0 -30 Td ({text}) Tj ET'.encode('ascii'));page[NameObject('/Contents')]=writer._add_object(stream);writer.write(str(pdf))
with transaction(db) as conn:
 collections=conn.execute('SELECT collection_id FROM collections').fetchall();assert len(collections)==1
 conn.execute('INSERT INTO source_file_versions VALUES(?,?,?,?,?,?,?,?,?,?,?)',('software-native-other-file','other',hashlib.sha256(pdf.read_bytes()).hexdigest(),pdf.stat().st_size,'application/pdf',str(pdf),'TEST_FIXTURE_SOURCE_NATIVE',None,'VERIFIED','{"software_fixture":true}','software-fixture-now'))
 conn.execute("UPDATE papers SET title='Refreshed live catalog title - software' WHERE paper_id='existing'")
acquisition=AcquisitionService(root)
parsed=acquisition.publish_parse_result(collections[0][0],'other','software-native-other-file',parser_name='TEST_FIXTURE_SOURCE_NATIVE',parser_version='1',config={},manifest={'software_only':True},blocks=[{'text':text,'page_number':1,'section':'Other software source','block_type':'TEXT','location':{'bbox':[72,120,420,140]}}],references=[])
with transaction(db) as conn:block=conn.execute('SELECT * FROM document_blocks WHERE parse_run_id=?',(parsed['parse_run_id'],)).fetchone()
published=acquisition.publish_skeleton_result(parsed['parse_run_id'],[{'block_id':block['block_id'],'page_number':1,'section':block['section'],'raw_text':text,'layer1':{'triplets':[]},'layer2':{},'layer3':{'intent':'Software_Test'},'layer4':{'role':'Software_Test'}}],model_name='TEST_FIXTURE_SOURCE_NATIVE')
with transaction(db) as conn:source=skeleton_source(conn,published['skeleton_id'])
unit=source['units'][0];track=service.get_workspace(ms)['manuscript']['track_id']
evidence=service.track_service.add_evidence(TrackFirstEvidenceInput(track_id=track,paper_id='other',statement=text,excerpt=text,location='Exact software source',location_data={'unit_id':unit['unit_id'],'skeleton_id':source['skeleton_id'],'unit_digest':unit['content_digest'],'skeleton_digest':source['content_digest'],'page':1,'section':unit['section'],'sequence':unit['seq_idx']},confidence=.9,relation='SUPPORTS',extractor_model='TEST_FIXTURE_SOURCE_NATIVE',prompt_version='1'))
assert service.get_workspace(ms)['document_revision']==1
assert hashlib.sha256(Path(fixture['original_pdf']).read_bytes()).hexdigest()==fixture['original_pdf_sha256']
service._executor.shutdown(wait=True)
receipt={'evidence':evidence,'source':source,'original_pdf':str(pdf),'original_pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'old_original_unchanged':True,'author_document_unchanged':True,'software_fixture':True,'actual_remote_model_calls':0,'scientific_acceptance':False}
(repo/'.tmp/scholar-citation-source-second-native-source-v1.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps({'evidence_id':evidence['evidence_id'],'old_original_unchanged':True,'author_document_unchanged':True}),flush=True)
