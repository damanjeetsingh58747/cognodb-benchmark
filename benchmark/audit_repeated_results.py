from __future__ import annotations

import csv
import math
from pathlib import Path

import audit_results as base


ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "results" / "runs"
RESULTS = ROOT / "results"

EXPECTED_RUNS = 3

SUMMARY_FILES = {
    "repeated_summary_ingest.csv": 5,
    "repeated_summary_reads.csv": 30,
    "repeated_summary_mixed.csv": 15,
    "repeated_summary_control.csv": 5,
}

CHARTS = [
    ROOT / "charts" / "repeated_ingest_relationships_mean_std.png",
    ROOT / "charts" / "repeated_read_p50_mean_std.png",
    ROOT / "charts" / "repeated_mixed_qps_mean_std.png",
    ROOT / "charts" / "repeated_control_p50_mean_std.png",
]


def audit_archived_runs():
    run_dirs = sorted(
        p for p in RUNS_DIR.glob("run_*")
        if p.is_dir()
    )

    assert len(run_dirs) == EXPECTED_RUNS, (
        f"Expected {EXPECTED_RUNS} archived runs, found {len(run_dirs)}"
    )

    original_raw = base.RAW

    try:
        for run_dir in run_dirs:
            json_files = list(run_dir.glob("*.json"))

            assert len(json_files) == 16, (
                f"{run_dir}: expected 16 JSON files, found {len(json_files)}"
            )

            base.RAW = run_dir

            for platform in base.PLATFORMS:
                base.audit_ingest(platform)
                base.audit_reads(platform)
                base.audit_mixed(platform)

            base.audit_control()

            print(f"✅ {run_dir.name}: 16 files and all benchmark checks passed")
    finally:
        base.RAW = original_raw


def audit_repeated_summaries():
    for filename, expected_rows in SUMMARY_FILES.items():
        path = RESULTS / filename

        assert path.exists(), f"Missing {path}"

        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        assert len(rows) == expected_rows, (
            f"{filename}: expected {expected_rows} rows, found {len(rows)}"
        )

        for row in rows:
            assert int(row["runs"]) == EXPECTED_RUNS

            for key, value in row.items():
                if key in {"platform", "workload", "runs"}:
                    continue

                number = float(value)

                assert math.isfinite(number), (
                    f"{filename}/{key}: non-finite value"
                )

                if "stdev" in key or key == "total_errors":
                    assert number >= 0
                else:
                    assert number > 0

        print(f"✅ {filename}: {expected_rows} rows")


def audit_generated_outputs():
    report = RESULTS / "REPEATED_RUNS.md"
    assert report.exists() and report.stat().st_size > 0

    for chart in CHARTS:
        assert chart.exists() and chart.stat().st_size > 0

    print("✅ repeated-run report and 4 charts")


def main():
    print("Repeated benchmark evidence audit")
    print("=" * 44)

    audit_archived_runs()
    audit_repeated_summaries()
    audit_generated_outputs()

    print()
    print("Evidence checked:")
    print("  3/3 archived full benchmark executions")
    print("  48/48 archived JSON result files")
    print("  4/4 repeated summary CSVs")
    print("  repeated-run report")
    print("  4/4 repeated-run charts")
    print()
    print("✅ REPEATED BENCHMARK EVIDENCE AUDIT PASSED")


if __name__ == "__main__":
    main()
