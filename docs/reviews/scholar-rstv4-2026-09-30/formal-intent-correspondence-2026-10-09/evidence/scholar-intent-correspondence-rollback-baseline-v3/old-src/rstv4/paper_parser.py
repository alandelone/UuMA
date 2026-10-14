from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

from .parser_quality import normalize_mineru_result


class MinerUParser:
    """Invoke the pinned MinerU environment as an isolated, versioned subprocess."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.python = Path(
            os.environ.get(
                "RSTV4_MINERU_PYTHON",
                r"C:\Users\Alandelone\anaconda3\envs\ragent-mineru122\python.exe",
            )
        )
        self.bridge = self.root / "scripts" / "mineru_bridge.py"
        self.legacy_root = self.root / "文献POOL"
        self.artifact_root = Path(
            os.environ.get(
                "RSTV4_MINERU_ARTIFACT_ROOT",
                str(self.root / "data" / "artifacts" / "mineru"),
            )
        )

    def _new_short_attempt(self) -> tuple[Path, Path]:
        """Keep MinerU's source and image paths below Windows' native path limit."""
        attempt_name = f"attempt-{uuid4().hex}"
        artifact_root = self.artifact_root.resolve()
        expected_image = artifact_root / attempt_name / "out" / "source" / "images" / (
            "f" * 64 + ".jpg"
        )
        if os.name == "nt" and len(str(expected_image)) >= 240:
            local_app_data = os.environ.get("LOCALAPPDATA")
            if not local_app_data:
                raise RuntimeError("MinerU needs a short artifact root on Windows")
            artifact_root = Path(local_app_data) / "RSTV4" / "mineru"
            expected_image = artifact_root / attempt_name / "out" / "source" / "images" / (
                "f" * 64 + ".jpg"
            )
            if len(str(expected_image)) >= 240:
                raise RuntimeError("MinerU artifact path is too long on Windows")
        attempt_dir = artifact_root / attempt_name
        attempt_dir.mkdir(parents=True, exist_ok=False)
        return attempt_dir / "source.pdf", attempt_dir / "out"

    def check(self) -> dict[str, Any]:
        missing = [
            str(path)
            for path in (self.python, self.bridge, self.legacy_root)
            if not path.exists()
        ]
        if missing:
            return {"available": False, "missing": missing}
        probe_code = (
            "import sys; from importlib.metadata import version; "
            "assert version('magic-pdf') == '1.2.2', version('magic-pdf'); "
            "assert version('transformers') == '4.42.4', version('transformers'); "
            f"sys.path.insert(0, {str(self.legacy_root)!r}); "
            f"sys.path.insert(0, {str(self.root / 'scripts')!r}); "
            "from mineru_bridge import install_transformers_compatibility; "
            "install_transformers_compatibility(); "
            "from paperpool.workers.pdf_parser_worker import pdf_parse_main; "
            "print('ok magic-pdf=1.2.2 transformers=4.42.4')"
        )
        environment = os.environ.copy()
        environment.update({"PYTHONUTF8": "1", "OMP_NUM_THREADS": "1"})
        probe = subprocess.run(
            [str(self.python), "-c", probe_code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            timeout=30,
            check=False,
        )
        return {
            "available": probe.returncode == 0,
            "python": str(self.python),
            "detail": (probe.stdout or probe.stderr).strip(),
        }

    def parse(
        self, pdf: str | Path, output: str | Path, *, timeout_seconds: int = 7200
    ) -> dict[str, Any]:
        readiness = self.check()
        if not readiness["available"]:
            raise RuntimeError(f"MinerU environment unavailable: {readiness}")
        environment = os.environ.copy()
        environment.update({"PYTHONUTF8": "1", "OMP_NUM_THREADS": "1", "PYTHONFAULTHANDLER": "1"})
        staged_pdf, attempt_output = self._new_short_attempt()
        try:
            shutil.copyfile(Path(pdf).resolve(), staged_pdf)
            for stage in ("analyze", "materialize"):
                process = subprocess.run(
                    [
                        str(self.python),
                        str(self.bridge),
                        "--pdf",
                        str(staged_pdf),
                        "--output",
                        str(attempt_output),
                        "--legacy-root",
                        str(self.legacy_root),
                        "--method",
                        "auto",
                        "--stage",
                        stage,
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=environment,
                    timeout=timeout_seconds,
                    check=False,
                )
                if process.returncode != 0:
                    raise RuntimeError(
                        f"MinerU {stage} exited with code {process.returncode}: "
                        f"{(process.stderr or process.stdout)[-8000:]}"
                    )
        finally:
            staged_pdf.unlink(missing_ok=True)
        manifest_path = Path(process.stdout.strip().splitlines()[-1])
        if not manifest_path.is_file():
            raise RuntimeError("Parser returned no verified result manifest")
        result = json.loads(manifest_path.read_text(encoding="utf-8"))
        result["manifest"]["requested_output_dir"] = str(Path(output).resolve())
        result["manifest"]["source_pdf_path"] = str(Path(pdf).resolve())
        return normalize_mineru_result(
            result,
            source_pdf_path=pdf,
        )
