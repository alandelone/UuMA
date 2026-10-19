from __future__ import annotations
import concurrent.futures
import json
import pathlib
import shutil
import subprocess
import sys
root = pathlib.Path.cwd()
base = pathlib.Path(__file__).resolve().parent
cli = pathlib.Path(r"C:/Users/Ling's/.codex/skills/archify/bin/archify.mjs")
node = shutil.which("node")
def run(mode):
    folder = base / mode
    output = folder / ("forge-" + mode + ".html")
    args = [node, str(cli), "finalize", mode, str(folder / "candidate.json"), str(output),
            "--repo-root", str(root), "--quality", "showcase", "--json"]
    if (folder / ("forge-" + mode + ".delivery.json")).exists():
        count = len(list(folder.glob("review-*"))) + 2
        args.extend(["--out-dir", str(folder / ("review-" + str(count)))])
    p = subprocess.run(args, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (folder / "last-finalize-stdout.json").write_text(p.stdout, encoding="utf-8")
    (folder / "last-finalize-stderr.txt").write_text(p.stderr, encoding="utf-8")
    return {"mode": mode, "exit": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
modes = sys.argv[1:] or ["architecture","workflow","sequence","dataflow","class"]
with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
    for result in pool.map(run, modes):
        print(json.dumps(result, ensure_ascii=False), flush=True)
