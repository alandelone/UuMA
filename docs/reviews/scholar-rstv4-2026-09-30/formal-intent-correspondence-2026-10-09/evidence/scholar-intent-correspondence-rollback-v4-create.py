from pathlib import Path

root=Path.cwd()
s=(root/'.tmp/scholar-intent-correspondence-rollback-baseline-v3.py').read_text(encoding='utf-8')
s=s.replace('rollback-baseline-v3','rollback-baseline-v4').replace("['current','before']", "['current','before','checkpoint']")
s=s.replace("['page_size','page_count','freelist_count','schema_version','auto_vacuum']", "['page_size','page_count','freelist_count','schema_version','auto_vacuum','journal_mode']")
old='''    raw = original_read(path)
    caller = inspect.currentframe().f_back
    if path.name == 'catalog.db' and caller.f_code.co_name == 'test_adoption_record_failure_rolls_back_document_and_operation':
        number = len(captures)
        with (out/f'{variant}-{number}.db').open('xb') as stream: stream.write(raw)
        captures.append((raw,snapshot(path)))
    return raw'''
new='''    caller = inspect.currentframe().f_back
    selected = path.name == 'catalog.db' and caller.f_code.co_name == 'test_adoption_record_failure_rolls_back_document_and_operation'
    checkpoint = None
    prior_state = None
    if selected and variant == 'checkpoint' and not captures:
        prior_state = snapshot(path)
        connection = sqlite3.connect(path)
        try:
            checkpoint = tuple(connection.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone())
            assert checkpoint == (0, 0, 0), checkpoint
        finally:
            connection.close()
        assert snapshot(path)['rows'] == prior_state['rows']
    raw = original_read(path)
    if selected:
        number = len(captures)
        wal = Path(str(path)+'-wal')
        wal_raw = original_read(wal) if wal.exists() else b''
        with (out/f'{variant}-{number}.db').open('xb') as stream: stream.write(raw)
        with (out/f'{variant}-{number}.wal').open('xb') as stream: stream.write(wal_raw)
        state = snapshot(path)
        state['wal_exists_at_raw_read'] = wal.exists()
        state['wal_bytes_at_raw_read'] = len(wal_raw)
        state['wal_sha256_at_raw_read'] = hashlib.sha256(wal_raw).hexdigest()
        state['checkpoint_before_freeze'] = checkpoint
        state['checkpoint_all_rows_unchanged'] = prior_state is not None and state['rows'] == prior_state['rows']
        captures.append((raw,state))
    return raw'''
assert s.count(old)==1
s=s.replace(old,new)
with (root/'.tmp/scholar-intent-correspondence-rollback-baseline-v4.py').open('x',encoding='utf-8') as stream: stream.write(s)
print('Prepared v4: capture actual WAL and verify explicit pre-freeze checkpoint, unchanged rows and full original byte assertion.')
