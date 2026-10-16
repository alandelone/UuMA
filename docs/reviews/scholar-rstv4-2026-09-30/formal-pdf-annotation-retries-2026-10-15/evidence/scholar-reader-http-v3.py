from pathlib import Path

path = Path(__file__).resolve()
source = path.with_name('scholar-reader-http-v1.py').read_text(encoding='utf-8')
source = source.replace('req.method', 'req.get_method()')
source = source.replace('.tmp/scholar-reader-http-v1', '.tmp/scholar-reader-http-v3')
source = source.replace('scholar-reader-frontend-v2', 'scholar-reader-frontend-v3')
needle = "    return call(label, f'/api/catalog/review/cases/{case}/annotations', payload, expected), payload"
assert source.count(needle) == 1
source = source.replace(needle,
    "    if label in {'doi-note', 'title-note'}:\n"
    "        payload['expected_catalog_value'] = {'value': paper()['doi' if field == 'DOI' else 'title']}\n"
    + needle)
exec(compile(source, __file__, 'exec'))
