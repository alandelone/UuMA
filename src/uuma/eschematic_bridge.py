from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class ESchematicError(RuntimeError):
    """Raised when the configured eSchematic runtime cannot complete a request."""


@dataclass(frozen=True)
class ESchematicBridge:
    root: Path
    python_executable: Path
    data_dir: Path
    output_dir: Path
    timeout_seconds: int = 180

    @classmethod
    def from_env(cls) -> ESchematicBridge:
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        uuma_data = Path(os.environ.get("UUMA_DATA_DIR", local_app_data / "UuMA"))
        default_root = Path(__file__).resolve().parents[3].parent / "eSchematic_skillset"
        return cls(
            root=Path(os.environ.get("ESCHEMATIC_ROOT", default_root)).expanduser(),
            python_executable=Path(os.environ.get("ESCHEMATIC_PYTHON", sys.executable)).expanduser(),
            data_dir=Path(
                os.environ.get("ESCHEMATIC_DATA_DIR", uuma_data / "forge-lab-bot" / "eschematic" / "data")
            ).expanduser(),
            output_dir=Path(
                os.environ.get(
                    "ESCHEMATIC_OUTPUT_DIR",
                    uuma_data / "forge-lab-bot" / "eschematic" / "output",
                )
            ).expanduser(),
        )

    def status(self) -> dict[str, Any]:
        skill_file = self.root / "skills" / "eschematic" / "SKILL.md"
        return {
            "available": self.root.is_dir() and skill_file.is_file() and self.python_executable.is_file(),
            "root": str(self.root),
            "python_executable": str(self.python_executable),
            "data_dir": str(self.data_dir),
            "output_dir": str(self.output_dir),
            "skill_file": str(skill_file),
        }

    def _environment(self) -> dict[str, str]:
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(self.root) + (os.pathsep + existing if existing else "")
        env["ESCHEMATIC_DATA_DIR"] = str(self.data_dir)
        env["ESCHEMATIC_OUTPUT_DIR"] = str(self.output_dir)
        return env

    def _run(self, module: str, arguments: list[str]) -> dict[str, Any]:
        current = self.status()
        if not current["available"]:
            raise ESchematicError(
                "eSchematic is not available. Check ESCHEMATIC_ROOT and ESCHEMATIC_PYTHON."
            )
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            [str(self.python_executable), "-m", module, *arguments],
            cwd=self.root,
            env=self._environment(),
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        if completed.returncode != 0:
            candidate = stdout or stderr
            try:
                failure_payload = json.loads(candidate)
            except json.JSONDecodeError:
                detail = candidate or f"exit code {completed.returncode}"
                raise ESchematicError(f"eSchematic request failed: {detail[:4000]}")
            if isinstance(failure_payload, dict):
                return {**failure_payload, "command_exit_code": completed.returncode}
            raise ESchematicError("eSchematic returned an unexpected failure response shape.")
        if not stdout:
            return {"status": "ok"}
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ESchematicError(f"eSchematic returned non-JSON output: {stdout[:1000]}") from exc
        if not isinstance(payload, dict):
            raise ESchematicError("eSchematic returned an unexpected response shape.")
        return payload

    def get_component(self, component_id: str) -> dict[str, Any]:
        return self._run(
            "skills.eschematic.scripts.db_manager", ["get", "--id", component_id]
        )

    def list_components(self, category: str = "", limit: int = 200) -> dict[str, Any]:
        requested_limit = max(1, min(limit, 10_000))
        export_path = self.data_dir / "catalog.json"
        result = self._run(
            "skills.eschematic.scripts.db_manager",
            ["export-json", "--output-path", str(export_path)],
        )
        if result.get("status") != "ok" or not export_path.is_file():
            raise ESchematicError("eSchematic could not export the authoritative catalog.")
        try:
            catalog = json.loads(export_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ESchematicError("eSchematic exported an unreadable catalog artifact.") from exc
        components = catalog.get("components", [])
        if category.strip():
            requested_category = category.strip().casefold()
            components = [
                component
                for component in components
                if str(component.get("category", "")).casefold() == requested_category
            ]
        total_count = len(components)
        components = components[:requested_limit]
        return {
            **result,
            "catalog_hash": catalog.get("catalog_hash"),
            "total_count": total_count,
            "count": len(components),
            "components": components,
        }

    def normalize_bom(self, input_path: str, mapping: dict[str, str] | None = None) -> dict[str, Any]:
        args = ["parse", "--input", input_path]
        if mapping:
            args.extend(["--mapping-json", json.dumps(mapping)])
        return self._run("skills.eschematic.scripts.bom_parser", args)

    def resolve_normalized_bom(self, normalized_bom: dict[str, Any]) -> dict[str, Any]:
        if normalized_bom.get("status") != "valid":
            return {
                "status": "blocked",
                "resolved_items": [],
                "unresolved_items": [],
                "findings": normalized_bom.get("findings", []),
            }

        catalog = self.list_components(limit=10_000).get("components", [])
        resolved: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        for item in normalized_bom.get("items", []):
            candidates: list[dict[str, Any]] = []
            if item.get("identity_type") == "exact":
                candidates = [
                    component
                    for component in catalog
                    if (component.get("manufacturer") or "").casefold()
                    == (item.get("manufacturer") or "").casefold()
                    and (component.get("mpn") or "").casefold()
                    == (item.get("mpn") or "").casefold()
                ]
            elif item.get("identity_type") == "generic":
                candidates = [
                    component
                    for component in catalog
                    if component.get("identity_type") == "generic"
                    and (component.get("category") or "").casefold()
                    == (item.get("category") or "").casefold()
                    and (component.get("value") or "").casefold()
                    == (item.get("value") or "").casefold()
                    and (
                        not item.get("package")
                        or (component.get("package") or "").casefold()
                        == (item.get("package") or "").casefold()
                    )
                ]

            if len(candidates) == 1:
                resolved.append({**item, "component_id": candidates[0]["id"]})
            else:
                unresolved.append(
                    {
                        **item,
                        "reason": "not_found" if not candidates else "ambiguous",
                        "candidate_component_ids": [candidate["id"] for candidate in candidates],
                    }
                )
        return {
            "status": "resolved" if not unresolved else "needs_review",
            "source_file": normalized_bom.get("source_file"),
            "resolved_items": resolved,
            "unresolved_items": unresolved,
            "findings": normalized_bom.get("findings", []),
        }

    def normalize_and_resolve_bom(
        self, input_path: str, mapping: dict[str, str] | None = None
    ) -> dict[str, Any]:
        return self.resolve_normalized_bom(self.normalize_bom(input_path, mapping))

    def export_design_manifest(
        self,
        design_id: str,
        revision_id: str,
        resolved_items: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        safe_design = re.sub(r"[^A-Za-z0-9_.-]+", "-", design_id.strip()).strip("-.")
        safe_revision = re.sub(r"[^A-Za-z0-9_.-]+", "-", revision_id.strip()).strip("-.")
        if not safe_design or not safe_revision:
            raise ValueError("design_id and revision_id are required.")
        normalized_items = []
        for item in resolved_items:
            component_id = str(item.get("component_id", "")).strip()
            quantity = float(item.get("quantity", 0))
            if not component_id or quantity <= 0:
                raise ValueError("Every design-manifest item needs component_id and positive quantity.")
            normalized_items.append(
                {
                    "component_id": component_id,
                    "quantity": quantity,
                    "designators": sorted(str(value) for value in item.get("designators", [])),
                }
            )
        normalized_items.sort(key=lambda item: (item["component_id"], item["designators"]))
        core = {
            "schema_version": "1.0.0",
            "design_id": design_id.strip(),
            "revision_id": revision_id.strip(),
            "items": normalized_items,
            "metadata": metadata or {},
        }
        canonical = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        manifest_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        payload = {**core, "manifest_hash": manifest_hash}
        target_dir = self.output_dir / "design-manifests" / safe_design
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{safe_revision}-{manifest_hash[:12]}.json"
        rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if target.exists():
            existing = json.loads(target.read_text(encoding="utf-8"))
            if existing != payload:
                raise ESchematicError("An immutable manifest path already contains different data.")
        else:
            with target.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(rendered)
        return {
            "status": "released",
            "design_id": design_id.strip(),
            "revision_id": revision_id.strip(),
            "manifest_hash": manifest_hash,
            "manifest_path": str(target),
            "manifest": payload,
        }

    def find_components(self, query: str, limit: int = 10) -> dict[str, Any]:
        return self._run(
            "skills.eschematic.scripts.fetch_component",
            ["find", "--query", query, "--limit", str(max(1, min(limit, 50)))],
        )

    def commit_candidate(self, candidate_id: str, *, approved: bool) -> dict[str, Any]:
        if not approved:
            raise PermissionError("Committing an eSchematic catalog candidate requires explicit approval.")
        return self._run(
            "skills.eschematic.scripts.fetch_component", ["commit", "--candidate-id", candidate_id]
        )

    def validate_circuit(self, circuit_ir_path: str) -> dict[str, Any]:
        return self._run(
            "skills.eschematic.scripts.generate_schematic",
            ["validate", "--circuit-ir", circuit_ir_path],
        )

    def render_circuit(
        self, circuit_ir_path: str, output_dir: str = "", *, overwrite: bool = False
    ) -> dict[str, Any]:
        if not output_dir and not overwrite:
            stamp = datetime.now(UTC).strftime("render-%Y%m%dT%H%M%S-%fZ")
            output_dir = str(self.output_dir / stamp)
        args = [
            "render",
            "--circuit-ir",
            circuit_ir_path,
            "--output-dir",
            output_dir or str(self.output_dir),
        ]
        if overwrite:
            args.append("--overwrite")
        return self._run("skills.eschematic.scripts.generate_schematic", args)

    def infer_circuit(self, prompt: str) -> dict[str, Any]:
        return self._run(
            "skills.eschematic.scripts.infer_circuit", ["infer", "--prompt", prompt]
        )

    def check_electrical_rules(self, circuit_ir_path: str) -> dict[str, Any]:
        return self._run(
            "skills.eschematic.scripts.electrical_rules",
            ["check", "--circuit-ir", circuit_ir_path],
        )

    def recommend(self, circuit_ir_path: str) -> dict[str, Any]:
        return self._run(
            "skills.eschematic.scripts.recommendations",
            ["recommend", "--circuit-ir", circuit_ir_path],
        )
