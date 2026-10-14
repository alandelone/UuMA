from pathlib import Path
import hashlib
import json
import subprocess

repo=Path.cwd()
root=repo / ".tmp/scholar-g09-current-generation-native-v1"
out=root / "final-pdf-rendered-v1"
out.mkdir()
version=json.loads((root / "generated-current-v5-api.json").read_text(encoding="utf-8"))
pdf=next(a for a in version["artifacts"] if a["artifact_kind"]=="PDF")
source=Path(pdf["storage_path"])
raw=source.read_bytes()
assert hashlib.sha256(raw).hexdigest()==pdf["sha256"] and len(raw)==pdf["size_bytes"]
result=subprocess.run(["pdftoppm","-r","110","-png",str(source),str(out / "page")],capture_output=True,text=True)
assert result.returncode==0,result.stderr
pages=sorted(out.glob("page-*.png"))
assert len(pages)==2
receipt={"status":"PASS_EXACT_FINAL_V5_PDF_RENDERED", "pdf_sha256":pdf["sha256"],
         "pdf_path":str(source),"pages":[str(p) for p in pages],"overall11_complete":False}
(out / "receipt.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
print(json.dumps(receipt),flush=True)
