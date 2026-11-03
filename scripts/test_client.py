import sqlite3
import json

db_path = '/home/alandelone/.local/share/uuma/production/wisdom-oldman/wisdom.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

orbit_id = 'orbit_9ac4d099873b82f8f5a730cf07792419'
rows = c.execute("SELECT record_json FROM orbit_frontier WHERE orbit_id=? AND status='OPEN'", (orbit_id,)).fetchall()
print(f"Open frontier count: {len(rows)}")
for r in rows:
    f = json.loads(r[0])
    print("Frontier item:", f.get("question_id"), "priority:", f.get("priority"), "no_source_attempts:", f.get("no_source_attempts"))
