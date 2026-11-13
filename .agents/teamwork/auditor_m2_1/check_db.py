"""Verify database immutability and schema integrity."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
from pathlib import Path

CATALOG_DB = Path(r"C:\Users\Alandelone\CodeSpace_Local\RSTV4\data\catalog.db")

def check_db_immutability():
    conn = sqlite3.connect(CATALOG_DB)
    cur = conn.cursor()

    print("=== DATABASE IMMUTABILITY & INTEGRITY ===")
    fk = cur.execute("PRAGMA foreign_key_check").fetchall()
    print(f"PRAGMA foreign_key_check: {fk}")

    integ = cur.execute("PRAGMA integrity_check").fetchall()
    print(f"PRAGMA integrity_check: {integ}")

    # Check triggers
    triggers = cur.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='trigger'").fetchall()
    print(f"Total triggers: {len(triggers)}")
    for t in triggers:
        print(f"  Trigger: {t[0]} on {t[1]}")

    # Check journal mode
    journal_mode = cur.execute("PRAGMA journal_mode").fetchone()[0]
    print(f"Journal mode: {journal_mode}")

    # Check schema version
    schema_ver = cur.execute("SELECT * FROM schema_version").fetchall()
    print(f"schema_version table: {schema_ver}")

    conn.close()

if __name__ == "__main__":
    check_db_immutability()
