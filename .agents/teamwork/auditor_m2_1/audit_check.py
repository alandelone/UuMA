"""Audit verification script for Milestone M2: Database & Artifact Inspection."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
import json
import os
import hashlib
from pathlib import Path

CATALOG_DB = Path(r"C:\Users\Alandelone\CodeSpace_Local\RSTV4\data\catalog.db")

def print_cols(cur, table):
    cols = [r['name'] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    print(f"Table {table} columns: {cols}")
    return cols

def audit():
    conn = sqlite3.connect(CATALOG_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("\n=== 4. SKELETON VIEWS, THEMES, AND PURPOSE JUDGMENTS (W25–W27) ===")
    print_cols(cur, "catalog_skeleton_content_views")
    print_cols(cur, "catalog_skeleton_purpose_judgments")
    print_cols(cur, "catalog_skeleton_theme_observations")

    cvs = cur.execute("SELECT * FROM catalog_skeleton_content_views LIMIT 5").fetchall()
    print(f"catalog_skeleton_content_views sample count={len(cvs)}:")
    for cv in cvs:
        row = dict(cv)
        if 'view_json' in row and row['view_json']:
            row['view_json'] = row['view_json'][:80] + '...'
        print(f"  {row}")

    pjs = cur.execute("SELECT * FROM catalog_skeleton_purpose_judgments LIMIT 5").fetchall()
    print(f"catalog_skeleton_purpose_judgments sample count={len(pjs)}:")
    for pj in pjs:
        print(f"  {dict(pj)}")

    theme_obs = cur.execute("SELECT count(*) FROM catalog_skeleton_theme_observations").fetchone()[0]
    print(f"catalog_skeleton_theme_observations count: {theme_obs}")

    conn.close()

if __name__ == "__main__":
    audit()
