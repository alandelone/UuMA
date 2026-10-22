"""Connect honc to the existing Yonc Graph and enable trusted completion reports."""

from __future__ import annotations

import argparse
import json
import shutil
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from ruamel.yaml import YAML


def deploy(profile: Path, backup: Path) -> dict:
    if profile.name != "honc" or profile.parent.name != "profiles" or backup.exists():
        raise ValueError("Requires existing honc profile and a fresh backup")
    yaml = YAML()
    yaml.preserve_quotes = True
    config_path = profile / "config.yaml"
    runtime_path = profile / "plugins/honc_life/runtime.json"
    before = yaml.load(config_path.read_text(encoding="utf-8"))
    runtime_before = json.loads(runtime_path.read_text(encoding="utf-8"))
    assert runtime_before["profile"] == "honc"
    assert Path(runtime_before["database_path"]).name == "honc.db"
    yonc = yaml.load((profile.parent / "yonc/config.yaml").read_text(encoding="utf-8"))
    url = yonc["mcp_servers"]["yonc-project"]["env"]["YONC_API_URL"].rstrip("/")
    parts = urlsplit(url)
    if parts.scheme != "http" or parts.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Expected existing local Yonc Graph")
    health = httpx.get(url + "/api/v2/health", timeout=15)
    health.raise_for_status()
    database_id = health.json()["database_id"]
    after = deepcopy(before)
    environment = after["mcp_servers"]["honc-execution"].setdefault("env", {})
    environment.update(YONC_GRAPH_URL=url, YONC_GRAPH_DATABASE_ID=database_id)
    unchanged = deepcopy(after)
    old_env = before["mcp_servers"]["honc-execution"].get("env", {})
    unchanged["mcp_servers"]["honc-execution"]["env"] = old_env
    assert unchanged == before
    runtime_after = {
        **runtime_before,
        "work_completion": {"enabled": True, "url": url, "database_id": database_id},
    }
    root = Path(__file__).resolve().parents[1]
    soul = profile / "SOUL.md"
    current = soul.read_text(encoding="utf-8")
    source = (root / "profiles/honc/SOUL.md").read_text(encoding="utf-8")
    marker = "## 6. 用户完成报告自动同步"
    section = source.split(marker, 1)[1]
    if marker in current:
        raise ValueError("Completion instructions already installed; reconcile explicitly")
    backup.mkdir(parents=True)
    target = profile / "plugins/honc_life"
    for path in (
        config_path,
        runtime_path,
        profile / "SOUL.md",
        target / "__init__.py",
        target / "plugin.yaml",
    ):
        relative = path.relative_to(profile)
        saved = backup / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, saved)
    for name in ("__init__.py", "plugin.yaml"):
        shutil.copy2(root / "integrations/hermes/honc_life" / name, target / name)
    with config_path.open("w", encoding="utf-8") as stream:
        yaml.dump(after, stream)
    runtime_path.write_text(
        json.dumps(runtime_after, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    soul.write_text(current + "\n\n" + marker + section, encoding="utf-8")
    assert yaml.load(config_path.read_text(encoding="utf-8")) == after
    assert json.loads(runtime_path.read_text(encoding="utf-8")) == runtime_after
    assert current in soul.read_text(encoding="utf-8")
    receipt = {
        "graph_url": url,
        "database_id": database_id,
        "host_auto_completion": True,
        "model_unchanged": before.get("model") == after.get("model"),
        "existing_life_runtime_fields_preserved": all(
            runtime_after[k] == v for k, v in runtime_before.items()
        ),
        "backup": str(backup),
        "production_task_mutations": 0,
    }
    (backup / "deployment.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-home", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(deploy(args.profile_home, args.backup)))
