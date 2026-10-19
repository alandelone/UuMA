import hashlib, json, pathlib, subprocess, zipfile
root=pathlib.Path.cwd()
base=pathlib.Path(__file__).resolve().parent
index=json.loads((base/"verification.json").read_text(encoding="utf-8"))
for item in index["diagrams"]:
    artifact=base/item["artifact"]
    candidate=json.loads((artifact.parent/"candidate.json").read_text(encoding="utf-8"))
    assert root/candidate["meta"]["output"] == artifact
    receipt=json.loads((base/item["receipt"]).read_text(encoding="utf-8"))
    assert receipt["ok"] and all(v=="pass" for v in receipt["gates"].values())
    assert hashlib.sha256(artifact.read_bytes()).hexdigest()==receipt["artifact"]["sha256"]
with zipfile.ZipFile(base/"forge-lab-bot-diagrams.zip","w",compression=zipfile.ZIP_DEFLATED) as z:
    for name in ["index.html","verification.json"]:
        z.write(base/name,name)
    for item in index["diagrams"]:
        artifact=base/item["artifact"]
        for name in [artifact.name,"candidate.json",artifact.stem+".delivery.json"]:
            f=artifact.parent/name
            z.write(f,f.relative_to(base))
        receipt=base/item["receipt"]
        z.write(receipt,receipt.relative_to(base))
print("Five artifact hashes and passing receipts verified. ZIP created.",flush=True)
print(subprocess.run(["git","status","--short"],capture_output=True,text=True,check=True).stdout,flush=True)
