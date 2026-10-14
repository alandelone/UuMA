from __future__ import annotations

import argparse
import json

from .service import RSTV4Service


def main() -> None:
    parser = argparse.ArgumentParser(prog="rstv4")
    parser.add_argument("command", choices=("init", "project", "papers"))
    parser.add_argument("--project")
    args = parser.parse_args()
    service = RSTV4Service()
    if args.command == "init":
        print(
            json.dumps(
                {"catalog": str(service.catalog_path), "projects_root": str(service.projects_root)},
                indent=2,
            )
        )
    elif args.command == "project":
        if not args.project:
            parser.error("--project is required for project")
        print(json.dumps(service.get_project(args.project), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(service.list_papers(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
