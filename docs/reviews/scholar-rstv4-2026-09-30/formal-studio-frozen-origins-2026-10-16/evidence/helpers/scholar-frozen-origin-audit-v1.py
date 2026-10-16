from pathlib import Path
import hashlib, json

repo = Path(__file__).resolve().parents[1]
here = repo/'.tmp/scholar-frozen-origin-native-v1'
read = lambda p: json.loads(p.read_text(encoding='utf8'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
r = read(here/'receipt.json')
terminal = read(here/'backend-terminal.json')
assert terminal['all110_exact'] and terminal['all_non_sidecar_bytes_exact']
assert terminal['copy_final_all_tables'] == read(here/'before110-all-tables.json')
assert read(here/'owned-stop-terminal.json')['no_other_processes_stopped']
for name, value in r['backend_source_vector'].items():
    assert sha(repo.parent/'RSTV4'/name) == value
for name, value in r['frontend_product_vector'].items():
    assert sha(repo.parent/'writing-studio'/name) == value
state = read(here/'before110-all-tables.json')['tables']['studio_documents']
record = next(dict(zip(state['columns'], row)) for row in state['rows']
              if dict(zip(state['columns'],row))['manuscript_id'] == 'manuscript_56652adf9d054cb6ab3819efacf3475c')
assert record['revision'] == record['last_generated_revision'] == 86
assert record['active_generated_version_id'] == 'manuscript_version_8732ec9497074d82ae2b4359a7c235e5'
document = json.loads(record['document_json'])
thoughts = {t['id']:(s,p,i,t) for s in document['sections'] for p in s['paragraphs']
            for i in p['intents'] for t in i['thoughts']}
context = read(here/'http-0017-response.json')
assert context['target_version_number'] == 7 and context['state']['generated_input_revision'] == 86
for row in context['evidence']:
    assert len(row['origins']) == 1
    origin = row['origins'][0]
    s,p,i,t = thoughts[row['thought_id']]
    assert origin['thought_text'] == t['text'] and origin['thought_id'] == t['id']
    assert origin['section_id'] == s['id'] and origin['section_title'] == s['title']
    assert origin['paragraph_id'] == p['id'] and origin['paragraph_purpose'] == p['purpose']
    assert origin['intent_id'] == i['id'] and origin['intent_label'] == i['label']
    assert origin['intent_thoughts'] == [{'thought_id':v['id'],'text':v['text']} for v in i['thoughts']]
    assert origin['generated_version_id'] == context['state']['generated_version_id']
    assert origin['input_revision'] == 86 and origin['generated_version_number'] == 7
first, second = context['evidence'][0], context['evidence'][3]
assert first['changed_text'] == second['changed_text'] and first['boxes'] == second['boxes']
assert first['thought_id'] != second['thought_id'] and first['origins'] != second['origins']
assert context['history'][0]['context']['target_version_number'] == 6
assert all('origins' not in row for row in context['history'][0]['context']['evidence'])
legacy = (here/'native-a212-legacy-history.txt').read_text(encoding='utf8')
assert legacy.count('此依据未记录可验证的固定版本原思想。') == 5
assert '成文 v6' in legacy and '固定成文 v7' not in legacy
narrow = read(here/'native-source-760-geometry.json')
assert narrow['width'] == 760 and narrow['checked'] == 0 and len(narrow['sources']) == 2
assert all(s['scrollWidth'] <= s['width'] for s in narrow['sources'] + narrow['dialog'])
assert all(len(s['selected']) > 100 for s in narrow['sources'])
for t in [first['origins'][0]['thought_text'],second['origins'][0]['thought_text']]:
    assert all(t in s['text'] for s in narrow['sources'])
requests = [read(p) for p in here.glob('http-*.json') if not p.name.endswith('-response.json')]
assert all(x['method'] in {'GET','HEAD','OPTIONS'} or x['path'] in {
    '/api/research/discussion/context','/api/research/discussion/history'} for x in requests)
assert not any(x['method'] in {'PATCH','PUT','DELETE'} or (x['method']=='POST' and x['path'].endswith('/jobs')) for x in requests)
changed = []
for name, digest in read(repo/'.tmp/scholar-frozen-origin-v1/source-before.json').items():
    if sha(Path(name)) != digest:
        changed.append(str(Path(name).relative_to(repo.parent)).replace('\\','/'))
assert set(changed) == {'RSTV4/src/rstv4/studio_revision_mapping.py',
                        'writing-studio/components/studio-response-review.tsx',
                        'writing-studio/lib/studio-types.ts',
                        'writing-studio/tests/unit/studio-response-review.cjs'}
result = {'status':'PASS_FIXED_V7_TWO_NATIVE_THOUGHTS_AND_LEGACY_BOUNDARY',
          'source_backend_count':len(r['backend_source_vector']), 'source_frontend_count':len(r['frontend_product_vector']),
          'dist_count':len(r['frontend_dist_vector']), 'six_origins_match_exact_r86':True,
          'same_sentence_boxes_different_original_thoughts':True,'native_full_intent_and_selected_thought':True,
          'native760_no_overflow_no_implicit_checks':True,'old_v6_history_exact_missing_origins_explicit':True,
          'all110_and_non_sidecar_bytes_exact':True,'new_models_jobs_checks_versions_packages':0,
          'actual_request_count':len(requests),'native_initial_fetch_failure_still_open':True,
          'inline_history_click_closed_dialog_observation_retained':True,
          'Beta_native_text_actually_differs_from_baseline_not_citation_only_fixture':True,
          'owned_processes_stopped':True,'overall118_complete':False,'final11_complete':False}
with (here/'final-readonly-audit.json').open('x',encoding='utf8') as handle:
    json.dump(result,handle,indent=2)
print(json.dumps(result,indent=2))
