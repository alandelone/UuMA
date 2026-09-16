from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

SPECIALIST_DISABLED_TOOLSETS = {
    "browser",
    "code_execution",
    "computer_use",
    "delegation",
    "terminal",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--role", choices=("control", "worker"), required=True)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--python-exe", required=True)
    parser.add_argument("--source-path", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--gemini-allowed-roots", required=True)
    parser.add_argument("--eschematic-root", default="")
    parser.add_argument("--eschematic-python", default="")
    parser.add_argument("--rstv4-root", default="")
    parser.add_argument("--rstv4-python", default="")
    parser.add_argument("--kag-bridge-url", default="http://127.0.0.1:8891")
    parser.add_argument("--kag-compose-file", default="")
    parser.add_argument("--kag-python", default="")
    parser.add_argument("--kag-config", default="")
    parser.add_argument("--kag-auto-recover", default="true")
    parser.add_argument("--kag-base-url", default="")
    parser.add_argument("--kag-model", default="")
    parser.add_argument("--kag-project-id", default="")
    parser.add_argument("--bge-m3-path", default="")
    return parser.parse_args()


def map_at(root: CommentedMap, key: str) -> CommentedMap:
    value = root.get(key)
    if not isinstance(value, dict):
        value = CommentedMap()
        root[key] = value
    return value


def sequence_at(root: CommentedMap, key: str) -> CommentedSeq:
    value = root.get(key)
    if not isinstance(value, list):
        value = CommentedSeq()
        root[key] = value
    return value


def server(args: argparse.Namespace, module: str) -> CommentedMap:
    environment = CommentedMap(
        {
            "PYTHONPATH": args.source_path,
            "UUMA_DATA_DIR": args.data_dir,
            "UUMA_AGENT_ID": args.agent_id,
        }
    )
    if args.agent_id == "forge-lab-bot":
        lab_root = Path(args.data_dir) / "forge-lab-bot"
        environment.update(
            {
                "LAB_DATABASE_PATH": str(lab_root / "lab.db"),
                "ESCHEMATIC_ROOT": args.eschematic_root,
                "ESCHEMATIC_PYTHON": args.eschematic_python,
                "ESCHEMATIC_DATA_DIR": str(lab_root / "eschematic" / "data"),
                "ESCHEMATIC_OUTPUT_DIR": str(lab_root / "eschematic" / "output"),
            }
        )
    if module == "uuma.mcp_knowledge":
        environment.update(
            {
                "UUMA_KAG_BRIDGE_URL": args.kag_bridge_url,
                "UUMA_KAG_AUTO_RECOVER": args.kag_auto_recover,
            }
        )
        if args.kag_compose_file:
            environment["UUMA_KAG_COMPOSE_FILE"] = args.kag_compose_file
        if args.kag_python:
            environment["UUMA_KAG_PYTHON"] = args.kag_python
        if args.kag_config:
            environment["UUMA_KAG_CONFIG"] = args.kag_config
        if args.kag_base_url:
            environment["OPENAI_BASE_URL"] = args.kag_base_url
        if args.kag_model:
            environment["UUMA_KAG_LLM_MODEL"] = args.kag_model
        if args.kag_project_id:
            environment["UUMA_KAG_PROJECT_ID"] = args.kag_project_id
        if args.bge_m3_path:
            environment["UUMA_BGE_M3_PATH"] = args.bge_m3_path
    return CommentedMap(
        {
            "command": args.python_exe,
            "args": CommentedSeq(["-m", module]),
            "env": environment,
            "timeout": 180,
            "connect_timeout": 30,
            "idle_timeout_seconds": 0,
        }
    )


def rstv4_server(args: argparse.Namespace) -> CommentedMap:
    if not args.rstv4_root or not args.rstv4_python:
        raise ValueError("Scholar RSTV4 MCP requires --rstv4-root and --rstv4-python")
    return CommentedMap(
        {
            "command": args.rstv4_python,
            "args": CommentedSeq(["-m", "rstv4.mcp_server"]),
            "env": CommentedMap(
                {
                    "PYTHONPATH": str(Path(args.rstv4_root) / "src"),
                    "RSTV4_ROOT": args.rstv4_root,
                }
            ),
            "timeout": 180,
            "connect_timeout": 30,
            "idle_timeout_seconds": 0,
        }
    )


def gemini_server(args: argparse.Namespace) -> CommentedMap:
    return CommentedMap(
        {
            "command": args.python_exe,
            "args": CommentedSeq(["-m", "uuma.mcp_gemini"]),
            "env": CommentedMap(
                {
                    "PYTHONPATH": args.source_path,
                    "UUMA_AGENT_ID": args.agent_id,
                    "GEMINI_WORKER_ALLOWED_ROOTS": args.gemini_allowed_roots,
                    "GEMINI_WORKER_LOG_DIR": str(Path(args.data_dir) / "workers" / "gemini"),
                    "GEMINI_WORKER_APPROVAL_MODE": "plan",
                }
            ),
            "timeout": 600,
            "connect_timeout": 30,
            "idle_timeout_seconds": 0,
        }
    )


def main() -> None:
    args = parse_args()
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 100
    yaml.indent(mapping=2, sequence=4, offset=2)

    with args.config.open("r", encoding="utf-8") as handle:
        config = yaml.load(handle) or CommentedMap()
    if not isinstance(config, CommentedMap):
        raise TypeError("Hermes config root must be a mapping")

    backup = args.config.with_suffix(args.config.suffix + ".uuma-backup")
    if not backup.exists():
        shutil.copy2(args.config, backup)

    mcp_servers = map_at(config, "mcp_servers")
    mcp_servers["gemini-worker"] = gemini_server(args)
    if args.role == "control":
        # A single default gateway serves every specialist profile.  Each
        # profile can therefore own an isolated messaging credential (for
        # example, a dedicated Telegram bot) without starting a competing
        # gateway process.
        map_at(config, "gateway")["multiplex_profiles"] = True
        mcp_servers.pop("uuma-worker", None)
        mcp_servers.pop("rstv4-worker", None)
        mcp_servers["uuma-control"] = server(args, "uuma.mcp_control")
        mcp_servers["wisdom-knowledge"] = server(args, "uuma.mcp_knowledge")
    else:
        mcp_servers.pop("xhs", None)
        mcp_servers.pop("uuma-control", None)
        mcp_servers["uuma-worker"] = server(args, "uuma.mcp_worker")
        if args.agent_id == "scholar":
            # Scholar experiments must pass through RSTV4's approved-plan
            # executor. A general coding worker would be an unenforced path.
            mcp_servers.pop("gemini-worker", None)
        if args.agent_id == "wisdom-oldman":
            mcp_servers["wisdom-knowledge"] = server(args, "uuma.mcp_knowledge")
        else:
            mcp_servers.pop("wisdom-knowledge", None)
        if args.agent_id == "scholar" and args.rstv4_root:
            mcp_servers["rstv4-worker"] = rstv4_server(args)
        else:
            mcp_servers.pop("rstv4-worker", None)

        platform_toolsets = map_at(config, "platform_toolsets")
        for toolset in platform_toolsets.values():
            if isinstance(toolset, list):
                toolset[:] = [name for name in toolset if name not in SPECIALIST_DISABLED_TOOLSETS]

    plugins = map_at(config, "plugins")
    enabled = sequence_at(plugins, "enabled")
    if "uuma_audit" not in enabled:
        enabled.append("uuma_audit")

    with args.config.open("w", encoding="utf-8", newline="") as handle:
        yaml.dump(config, handle)


if __name__ == "__main__":
    main()
