import sqlite3
import json

db_path = '/home/alandelone/.local/share/uuma/production/wisdom-oldman/wisdom.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

orbit_id = 'orbit_9ac4d099873b82f8f5a730cf07792419'
cycle_row = c.execute("SELECT record_json FROM orbit_cycles WHERE orbit_id=? ORDER BY rowid DESC LIMIT 1", (orbit_id,)).fetchone()
if cycle_row:
    cycle = json.loads(cycle_row[0])
    print('Latest Cycle ID:', cycle.get('orbit_cycle_id'))
    print('Latest Cycle Status:', cycle.get('status'))
    print('Latest Cycle Attempt:', cycle.get('attempt'))
    print('Latest Cycle Error:', cycle.get('error'))
    print('Lease expires at:', cycle.get('lease_expires_at'))
