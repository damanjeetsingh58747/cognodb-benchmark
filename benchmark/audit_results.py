from __future__ import annotations

import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results" / "raw"
RESULTS = ROOT / "results"

PLATFORMS = [
    "cognodb",
    "neo4j",
    "falkordb",
    "memgraph",
    "arangodb",
]

WORKLOADS = [
    "point_lookup",
    "indexed_lookup",
    "traversal_1hop",
    "traversal_2hop",
    "traversal_3hop",
    "aggregation_rating_counts",
]

EXPECTED_NODES = 2625
EXPECTED_RELATIONSHIPS = 100000
EXPECTED_READ_RUNS = 120
EXPECTED_CONCURRENCY = [1, 10, 40]


def load_json(path: Path):
    if not path.exists():
        raise AssertionError(f"Missing required file: {path}")

    return json.loads(path.read_text(encoding="utf-8"))


def finite_positive(value, label):
    if not isinstance(value, (int, float)):
        raise AssertionError(f"{label}: not numeric")

    if not math.isfinite(value) or value <= 0:
        raise AssertionError(f"{label}: invalid value {value}")


def audit_ingest(platform):
    data = load_json(RAW / f"{platform}_ingest.json")

    verification = data["verification"]

    assert verification["passed"] is True
    assert verification["nodes"] == EXPECTED_NODES
    assert (
        verification["relationships"]
        == EXPECTED_RELATIONSHIPS
    )

    finite_positive(
        data["throughput"]["nodes_per_second"],
        f"{platform} nodes/s",
    )

    finite_positive(
        data["throughput"]["relationships_per_second"],
        f"{platform} relationships/s",
    )


def audit_reads(platform):
    data = load_json(RAW / f"{platform}_reads.json")

    for workload in WORKLOADS:
        result = data["workloads"][workload]

        assert result["warmup_runs"] == 20
        assert result["successful_runs"] == EXPECTED_READ_RUNS
        assert result["error_count"] == 0

        stats = result["statistics"]

        assert stats["n"] == EXPECTED_READ_RUNS

        for metric in [
            "p50_ms",
            "p95_ms",
            "p99_ms",
            "mean_ms",
        ]:
            finite_positive(
                stats[metric],
                f"{platform}/{workload}/{metric}",
            )

        assert stats["p50_ms"] <= stats["p95_ms"]
        assert stats["p95_ms"] <= stats["p99_ms"]


def audit_mixed(platform):
    data = load_json(RAW / f"{platform}_mixed.json")

    assert data["mix"]["reads_percent"] == 90
    assert data["mix"]["writes_percent"] == 10

    results = data["results"]

    assert [
        row["concurrency"]
        for row in results
    ] == EXPECTED_CONCURRENCY

    for row in results:
        assert row["errors"] == 0

        finite_positive(
            row["qps"],
            f"{platform}/mixed/C{row['concurrency']}/qps",
        )

        finite_positive(
            row["all_latency"]["p50_ms"],
            f"{platform}/mixed/C{row['concurrency']}/p50",
        )

        finite_positive(
            row["all_latency"]["p95_ms"],
            f"{platform}/mixed/C{row['concurrency']}/p95",
        )


def audit_control():
    data = load_json(RAW / "control_latency.json")

    for platform in PLATFORMS:
        result = data[platform]

        assert result["runs"] == EXPECTED_READ_RUNS

        finite_positive(
            result["p50_ms"],
            f"{platform}/control/p50",
        )

        finite_positive(
            result["p95_ms"],
            f"{platform}/control/p95",
        )

        assert result["p50_ms"] <= result["p95_ms"]


def audit_summary_csvs():
    expected = {
        "summary_ingest.csv": 5,
        "summary_reads.csv": 30,
        "summary_mixed.csv": 15,
    }

    for filename, expected_rows in expected.items():
        path = RESULTS / filename

        assert path.exists(), f"Missing {path}"

        with path.open(
            newline="",
            encoding="utf-8",
        ) as handle:
            rows = list(csv.DictReader(handle))

        assert len(rows) == expected_rows, (
            f"{filename}: expected {expected_rows} rows, "
            f"found {len(rows)}"
        )


def main():
    print("Benchmark evidence audit")
    print("=" * 44)

    for platform in PLATFORMS:
        audit_ingest(platform)
        audit_reads(platform)
        audit_mixed(platform)

        print(f"✅ {platform}")

    audit_control()
    print("✅ control latency")

    audit_summary_csvs()
    print("✅ generated CSV summaries")

    print()
    print("Evidence checked:")
    print("  5/5 ingest result files")
    print("  30/30 read workload sets")
    print("  15/15 mixed concurrency points")
    print("  5/5 control-latency result sets")
    print("  3/3 summary CSVs")
    print()
    print("✅ BENCHMARK EVIDENCE AUDIT PASSED")


if __name__ == "__main__":
    main()
