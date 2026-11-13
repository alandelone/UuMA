"""Standalone Master CLI Test Runner for Scholar Catalog E2E Acceptance Test Suite.

Supports:
- Selective tier execution: --tier all|tier1|tier2|tier3|tier4
- Structured reporting: --report (generates JSON and Markdown reports)
- Pass/fail semantics: exit code 0 on all pass, exit code 1 on any failure.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure both UuMA and RSTV4 are present in Python search path
script_dir = Path(__file__).resolve().parent
uuma_root = script_dir.parents[1]
rstv4_root = uuma_root.parent / "RSTV4"
if str(uuma_root / "src") not in sys.path:
    sys.path.insert(0, str(uuma_root / "src"))
if str(rstv4_root / "src") not in sys.path:
    sys.path.insert(0, str(rstv4_root / "src"))

import pytest

TIER_FILES = {
    "tier1": script_dir / "test_tier1_features.py",
    "tier2": script_dir / "test_tier2_boundaries.py",
    "tier3": script_dir / "test_tier3_combinations.py",
    "tier4": script_dir / "test_tier4_scenarios.py",
}

TIER_NAMES = {
    "tier1": "Tier 1: Feature Coverage (F01–F19)",
    "tier2": "Tier 2: Boundary Value Analysis (B01–B10)",
    "tier3": "Tier 3: Cross-Feature Combinations (PW01–PW07)",
    "tier4": "Tier 4: Real-World Application Scenarios (SC01–SC04)",
}


class E2ETestReportCollector:
    """In-process pytest plugin collecting structured test metrics across tiers."""

    def __init__(self):
        self.records: list[dict[str, Any]] = []
        self.start_time: float = 0.0
        self.end_time: float = 0.0

    def pytest_sessionstart(self, session):
        self.start_time = time.time()

    def pytest_sessionfinish(self, session, exitstatus):
        self.end_time = time.time()

    def pytest_runtest_logreport(self, report):
        if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
            # Determine which tier file this test belongs to
            tier_key = "unknown"
            node_path = str(report.nodeid).replace("\\", "/")
            for t_key, t_path in TIER_FILES.items():
                if t_path.name in node_path:
                    tier_key = t_key
                    break

            error_repr = None
            if report.failed and report.longrepr:
                error_repr = str(report.longrepr)

            self.records.append({
                "nodeid": report.nodeid,
                "name": report.location[2] if report.location else report.nodeid,
                "tier": tier_key,
                "tier_name": TIER_NAMES.get(tier_key, "Unknown"),
                "outcome": report.outcome,
                "duration": round(report.duration, 4),
                "error": error_repr,
            })


def generate_markdown_report(
    summary: dict[str, Any],
    tier_stats: dict[str, dict[str, int]],
    records: list[dict[str, Any]],
) -> str:
    lines = [
        "# Scholar Catalog E2E Acceptance Test Report",
        "",
        f"- **Execution Timestamp**: {summary['timestamp']}",
        f"- **Target Tier Scope**: `{summary['target_tier']}`",
        f"- **Overall Status**: **{summary['overall_status']}**",
        f"- **Total Executed Tests**: {summary['total_tests']}",
        f"- **Passed**: {summary['passed_tests']} ({(summary['passed_tests'] / max(1, summary['total_tests'])) * 100:.1f}%)",
        f"- **Failed**: {summary['failed_tests']}",
        f"- **Skipped**: {summary['skipped_tests']}",
        f"- **Duration**: {summary['duration_seconds']}s",
        "",
        "## Tier Breakdown Summary",
        "",
        "| Tier | Name | Total | Passed | Failed | Status |",
        "|---|---|:---:|:---:|:---:|:---:|",
    ]

    for t_key, name in TIER_NAMES.items():
        if t_key in tier_stats:
            stats = tier_stats[t_key]
            tot = stats["total"]
            pass_cnt = stats["passed"]
            fail_cnt = stats["failed"]
            st = "PASS" if fail_cnt == 0 and tot > 0 else "FAIL" if fail_cnt > 0 else "N/A"
            lines.append(f"| `{t_key}` | {name} | {tot} | {pass_cnt} | {fail_cnt} | {st} |")

    lines.extend([
        "",
        "## Detailed Test Inventory",
        "",
        "| # | Tier | Test Case | Outcome | Duration (s) |",
        "|---|---|---|:---:|:---:|",
    ])

    for idx, rec in enumerate(records, 1):
        outcome_badge = "**PASSED**" if rec["outcome"] == "passed" else f"**{rec['outcome'].upper()}**"
        lines.append(f"| {idx} | `{rec['tier']}` | `{rec['name']}` | {outcome_badge} | {rec['duration']} |")

    lines.append("")
    return "\n".join(lines)


def run_tests(
    tier: str = "all",
    report: bool = False,
    report_dir: Path | None = None,
    verbose: bool = True,
    extra_pytest_args: list[str] | None = None,
) -> int:
    """Execute tests for designated tier, generate reports, and return exit code."""
    if tier == "all":
        target_files = list(TIER_FILES.values())
    elif tier in TIER_FILES:
        target_files = [TIER_FILES[tier]]
    else:
        print(f"Error: Unknown tier '{tier}'. Choose from 'all', 'tier1', 'tier2', 'tier3', 'tier4'.", file=sys.stderr)
        return 1

    # Verify target test files exist
    for f in target_files:
        if not f.exists():
            print(f"Error: Test file not found: {f}", file=sys.stderr)
            return 1

    collector = E2ETestReportCollector()
    pytest_args = [str(f) for f in target_files]
    if verbose:
        pytest_args.append("-v")
    if extra_pytest_args:
        pytest_args.extend(extra_pytest_args)

    print(f"=== Starting Scholar Catalog E2E Acceptance Test Run [Tier: {tier}] ===")
    exit_code = pytest.main(pytest_args, plugins=[collector])

    # Compute statistics
    total = len(collector.records)
    passed = sum(1 for r in collector.records if r["outcome"] == "passed")
    failed = sum(1 for r in collector.records if r["outcome"] == "failed")
    skipped = sum(1 for r in collector.records if r["outcome"] == "skipped")
    duration = round(collector.end_time - collector.start_time, 2)
    overall_status = "PASSED" if exit_code == 0 and failed == 0 and total > 0 else "FAILED"

    tier_stats: dict[str, dict[str, int]] = {}
    for r in collector.records:
        t_key = r["tier"]
        if t_key not in tier_stats:
            tier_stats[t_key] = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
        tier_stats[t_key]["total"] += 1
        if r["outcome"] == "passed":
            tier_stats[t_key]["passed"] += 1
        elif r["outcome"] == "failed":
            tier_stats[t_key]["failed"] += 1
        elif r["outcome"] == "skipped":
            tier_stats[t_key]["skipped"] += 1

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target_tier": tier,
        "overall_status": overall_status,
        "exit_code": int(exit_code),
        "total_tests": total,
        "passed_tests": passed,
        "failed_tests": failed,
        "skipped_tests": skipped,
        "duration_seconds": duration,
        "tier_stats": tier_stats,
    }

    print("\n" + "=" * 70)
    print(f"E2E Test Run Complete: {overall_status} (Passed: {passed}/{total}, Duration: {duration}s)")
    print("=" * 70)

    if report:
        out_dir = report_dir or (script_dir / "reports")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        # JSON report
        json_report_path = out_dir / f"e2e_report_{tier}_{ts_str}.json"
        full_json_payload = {
            "summary": summary,
            "tests": collector.records,
        }
        json_report_path.write_text(json.dumps(full_json_payload, indent=2), encoding="utf-8")
        print(f"JSON Report written to: {json_report_path}")

        # Markdown report
        md_report_path = out_dir / f"e2e_report_{tier}_{ts_str}.md"
        md_content = generate_markdown_report(summary, tier_stats, collector.records)
        md_report_path.write_text(md_content, encoding="utf-8")
        print(f"Markdown Report written to: {md_report_path}")

    return 0 if overall_status == "PASSED" else 1


def main():
    parser = argparse.ArgumentParser(
        description="Scholar Catalog E2E Acceptance Test Runner",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--tier",
        choices=["all", "tier1", "tier2", "tier3", "tier4"],
        default="all",
        help="Target tier to execute",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate JSON and Markdown test execution reports in reports/",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=None,
        help="Custom output directory for reports",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Run pytest in quiet mode",
    )

    args, unknown = parser.parse_known_args()
    exit_code = run_tests(
        tier=args.tier,
        report=args.report,
        report_dir=args.report_dir,
        verbose=not args.quiet,
        extra_pytest_args=unknown,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
