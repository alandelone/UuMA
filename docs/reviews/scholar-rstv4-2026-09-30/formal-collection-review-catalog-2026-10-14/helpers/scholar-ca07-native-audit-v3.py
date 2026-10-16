from pathlib import Path

code = Path('.tmp/scholar-ca07-native-v1.py').read_text(encoding='utf-8')
old = 'from runtime_copy_and_serve_v8 import product_guard, snapshot, digest, read_json, exclusive_json'
new = 'from runtime_copy_and_serve_v9 import product_guard, snapshot, digest, read_json, exclusive_json, fixture_vector_unchanged_except_declared_popover'
assert code.count(old) == 1
code = code.replace(old,new)
old = "    assert product_guard() == receipt['source_vector']"
assert code.count(old) == 1
code = code.replace(old,"    fixture_vector_unchanged_except_declared_popover(receipt['source_vector'])")
old = "            assert request['sorts'] == [{'field':'published_year','direction':'desc'},{'field':'authors','direction':'asc'}]"
new = old + '''
            assert request['filter']['type'] == 'group' and request['filter']['operator'] == 'and'
            filters = request['filter']['filters']
            assert len(filters) == 2
            assert [(r['type'],r['field'],r['operator']) for r in filters] == [('rule','published_year','is_empty'),('rule','authors','is_empty')]
        else:
            assert request['sorts'] == [{'field':'updated_at','direction':'desc'}] and request['filter'] is None'''
assert code.count(old) == 1
code = code.replace(old,new)
exec(compile(code,__file__,'exec'))
