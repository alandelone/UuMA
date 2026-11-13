"""Deep forensic verification of L1-L4 units in RSTV4 catalog.db."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
import json
from pathlib import Path

CATALOG_DB = Path(r"C:\Users\Alandelone\CodeSpace_Local\RSTV4\data\catalog.db")

def verify_l1_to_l4():
    conn = sqlite3.connect(CATALOG_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    paper_id = "paper_dd83af8026e39dd2a2e9316622a7ca49"
    skel_id = "skeleton_e87a79f2f1e6fc99acb67b4568757132"
    parse_run_id = "parse_run_c3873033e0729a9dab355d6af14622ac"

    print("=== A. PARSE RUN AUDIT ===")
    pr = cur.execute("SELECT * FROM parse_runs WHERE parse_run_id=?", (parse_run_id,)).fetchone()
    if pr:
        for k in pr.keys():
            print(f"  {k}: {pr[k]}")
    else:
        print("  parse_runs record NOT FOUND in DB!")

    print("\n=== B. DOCUMENT BLOCKS AUDIT (85 blocks) ===")
    blocks = cur.execute("SELECT * FROM document_blocks WHERE parse_run_id=? ORDER BY sequence", (parse_run_id,)).fetchall()
    print(f"Total blocks: {len(blocks)}")
    # Sample blocks across different parts of the paper
    sample_indices = [0, 10, 20, 40, 60, 84]
    for idx in sample_indices:
        b = blocks[idx]
        print(f"  Block seq={b['sequence']}, page={b['page_number']}, type={b['block_type']}, section='{b['section']}'")
        print(f"    text snippet: {b['text'][:120]}...")
        loc = json.loads(b['location_json']) if b['location_json'] else None
        print(f"    location keys: {list(loc.keys()) if isinstance(loc, dict) else type(loc)}")

    print("\n=== C. SKELETON UNITS AUDIT (85 units) ===")
    units = cur.execute("SELECT * FROM skeleton_units WHERE skeleton_id=? ORDER BY seq_idx", (skel_id,)).fetchall()
    print(f"Total units: {len(units)}")
    for idx in sample_indices:
        u = units[idx]
        print(f"\n  Unit seq={u['seq_idx']}, page={u['page_idx']}, role={u['layer4']}, section='{u['section']}'")
        print(f"    raw_text snippet: {u['raw_text'][:100]}...")
        l1 = json.loads(u['layer1_json'])
        l2 = json.loads(u['layer2_json'])
        l3 = json.loads(u['layer3_json'])
        print(f"    L1 propositions: {len(l1.get('propositions', []))}")
        if l1.get('propositions'):
            p0 = l1['propositions'][0]
            print(f"      sample prop: stmt='{p0.get('statement', '')[:60]}', quote='{p0.get('quote', '')[:40]}', span={p0.get('source_span')}")
            # Verify quote is actually in raw_text!
            quote = p0.get('quote', '')
            if quote:
                in_raw = quote in u['raw_text']
                print(f"      quote verified in raw_text: {in_raw}")
        print(f"    L2 relations: {len(l2.get('relations', []))}")
        print(f"    L3 intents: {len(l3.get('intents', []))}")
        if l3.get('intents'):
            print(f"      intent: primary={l3['intents'][0].get('primary')}, rationale='{l3['intents'][0].get('rationale', '')[:60]}'")

    print("\n=== D. SKELETON TRIPLETS AUDIT (347 triplets) ===")
    triplets = cur.execute("""SELECT st.*, su.seq_idx FROM skeleton_triplets st
                              JOIN skeleton_units su ON st.unit_id=su.unit_id
                              WHERE su.skeleton_id=? ORDER BY st.rowid""", (skel_id,)).fetchall()
    print(f"Total triplets: {len(triplets)}")
    print("Sample triplets:")
    for t in triplets[:5]:
        print(f"  seq={t['seq_idx']}: ({t['subject']}) --[{t['predicate']}]--> ({t['object']})")

    print("\n=== E. SKELETON CHECKPOINTS AUDIT (340 checkpoints) ===")
    cps = cur.execute("""SELECT sc.* FROM skeleton_checkpoints sc
                         JOIN skeleton_runs sr ON sc.skeleton_run_id=sr.skeleton_run_id
                         WHERE sr.parse_run_id=? ORDER BY sc.rowid""", (parse_run_id,)).fetchall()
    print(f"Total checkpoints: {len(cps)}")
    layers = {}
    for c in cps:
        layers[c['layer']] = layers.get(c['layer'], 0) + 1
    print(f"Checkpoints per layer: {layers}")
    print(f"Status distribution: {set(c['status'] for c in cps)}")

    # Check 1-to-1 match: 85 blocks x 4 layers = 340 checkpoints
    block_ids = set(b['block_id'] for b in blocks)
    cp_section_keys = set(c['section_key'] for c in cps)
    print(f"Block IDs match Checkpoint section keys: {block_ids == cp_section_keys} (diff: {len(block_ids - cp_section_keys)})")

    # Check that each block has checkpoints for layer 1, 2, 3, 4
    all_four = True
    for b_id in block_ids:
        b_layers = set(c['layer'] for c in cps if c['section_key'] == b_id)
        if b_layers != {1, 2, 3, 4}:
            all_four = False
            print(f"Block {b_id} missing layers: {b_layers}")
            break
    print(f"All 85 blocks have exactly layers 1, 2, 3, 4 checkpoints: {all_four}")

    conn.close()

if __name__ == "__main__":
    verify_l1_to_l4()
