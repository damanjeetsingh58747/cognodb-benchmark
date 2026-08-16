from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results" / "raw"
RESULTS = ROOT / "results"
CHARTS = ROOT / "charts"

PLATFORMS = [
    ("cognodb", "CognoDB"),
    ("neo4j", "Neo4j AuraDB"),
    ("falkordb", "FalkorDB"),
    ("memgraph", "Memgraph"),
    ("arangodb", "ArangoDB"),
]

WORKLOADS = [
    "point_lookup",
    "indexed_lookup",
    "traversal_1hop",
    "traversal_2hop",
    "traversal_3hop",
    "aggregation_rating_counts",
]


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Missing result: {path}")

    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)


def markdown_table(headers, rows):
    output = []

    output.append(
        "| " + " | ".join(headers) + " |"
    )

    output.append(
        "| " + " | ".join(
            ["---"] * len(headers)
        ) + " |"
    )

    for row in rows:
        output.append(
            "| " + " | ".join(
                str(value) for value in row
            ) + " |"
        )

    return "\n".join(output)


def main():
    RESULTS.mkdir(exist_ok=True)
    CHARTS.mkdir(exist_ok=True)

    ingest_data = {}
    read_data = {}
    mixed_data = {}

    print("==============================================")
    print(" Validating benchmark result files")
    print("==============================================")

    for key, name in PLATFORMS:
        ingest = load_json(
            RAW / f"{key}_ingest.json"
        )

        reads = load_json(
            RAW / f"{key}_reads.json"
        )

        mixed = load_json(
            RAW / f"{key}_mixed.json"
        )

        # -----------------------------------------
        # Integrity checks
        # -----------------------------------------

        verification = ingest["verification"]

        assert verification["passed"] is True
        assert verification["nodes"] == 2625
        assert verification["relationships"] == 100000

        for workload in WORKLOADS:
            result = reads["workloads"][workload]

            assert result["error_count"] == 0, (
                f"{name}: errors in {workload}"
            )

            assert result["successful_runs"] == 120, (
                f"{name}: incomplete {workload}"
            )

        for point in mixed["results"]:
            assert point["errors"] == 0, (
                f"{name}: mixed errors at "
                f"C={point['concurrency']}"
            )

        ingest_data[key] = ingest
        read_data[key] = reads
        mixed_data[key] = mixed

        print(f"✅ {name}")

    # =====================================================
    # INGEST CSV
    # =====================================================

    ingest_rows = []

    for key, name in PLATFORMS:
        d = ingest_data[key]

        ingest_rows.append({
            "platform": name,
            "nodes_per_second":
                round(
                    d["throughput"]
                    ["nodes_per_second"],
                    2,
                ),
            "relationships_per_second":
                round(
                    d["throughput"]
                    ["relationships_per_second"],
                    2,
                ),
            "relationship_load_seconds":
                round(
                    d["timings_seconds"]
                    ["relationships"],
                    3,
                ),
            "end_to_end_seconds":
                round(
                    d["timings_seconds"]
                    ["end_to_end"],
                    3,
                ),
        })

    write_csv(
        RESULTS / "summary_ingest.csv",
        [
            "platform",
            "nodes_per_second",
            "relationships_per_second",
            "relationship_load_seconds",
            "end_to_end_seconds",
        ],
        ingest_rows,
    )

    # =====================================================
    # READ CSV
    # =====================================================

    read_rows = []

    for key, name in PLATFORMS:
        for workload in WORKLOADS:
            statistics = (
                read_data[key]
                ["workloads"]
                [workload]
                ["statistics"]
            )

            read_rows.append({
                "platform": name,
                "workload": workload,
                "p50_ms": round(
                    statistics["p50_ms"],
                    3,
                ),
                "p95_ms": round(
                    statistics["p95_ms"],
                    3,
                ),
                "p99_ms": round(
                    statistics["p99_ms"],
                    3,
                ),
                "mean_ms": round(
                    statistics["mean_ms"],
                    3,
                ),
                "stdev_ms": round(
                    statistics["stdev_ms"],
                    3,
                ),
            })

    write_csv(
        RESULTS / "summary_reads.csv",
        [
            "platform",
            "workload",
            "p50_ms",
            "p95_ms",
            "p99_ms",
            "mean_ms",
            "stdev_ms",
        ],
        read_rows,
    )

    # =====================================================
    # MIXED CSV
    # =====================================================

    mixed_rows = []

    for key, name in PLATFORMS:
        for result in mixed_data[key]["results"]:
            mixed_rows.append({
                "platform": name,
                "concurrency":
                    result["concurrency"],
                "qps":
                    round(result["qps"], 3),
                "read_qps":
                    round(
                        result["read_qps"],
                        3,
                    ),
                "write_qps":
                    round(
                        result["write_qps"],
                        3,
                    ),
                "p50_ms":
                    round(
                        result["all_latency"]
                        ["p50_ms"],
                        3,
                    ),
                "p95_ms":
                    round(
                        result["all_latency"]
                        ["p95_ms"],
                        3,
                    ),
                "errors":
                    result["errors"],
            })

    write_csv(
        RESULTS / "summary_mixed.csv",
        [
            "platform",
            "concurrency",
            "qps",
            "read_qps",
            "write_qps",
            "p50_ms",
            "p95_ms",
            "errors",
        ],
        mixed_rows,
    )

    # =====================================================
    # CHART 1 — Relationship ingest throughput
    # =====================================================

    names = [
        name
        for _, name in PLATFORMS
    ]

    rel_throughput = [
        ingest_data[key]
        ["throughput"]
        ["relationships_per_second"]
        for key, _ in PLATFORMS
    ]

    plt.figure(figsize=(10, 6))

    plt.bar(
        names,
        rel_throughput,
    )

    plt.ylabel("Relationships / second")
    plt.title(
        "MovieLens 100K Relationship Ingest Throughput"
    )

    plt.xticks(rotation=20)

    plt.tight_layout()

    plt.savefig(
        CHARTS /
        "ingest_relationship_throughput.png",
        dpi=180,
    )

    plt.close()

    # =====================================================
    # CHART 2/3 — Read latency
    # =====================================================

    for percentile_name in [
        "p50_ms",
        "p95_ms",
    ]:

        plt.figure(figsize=(13, 7))

        x = list(range(len(WORKLOADS)))

        width = 0.15

        for platform_index, (key, name) in enumerate(
            PLATFORMS
        ):
            values = [
                read_data[key]
                ["workloads"]
                [workload]
                ["statistics"]
                [percentile_name]
                for workload in WORKLOADS
            ]

            offsets = [
                value
                + (
                    platform_index
                    - 2
                ) * width
                for value in x
            ]

            plt.bar(
                offsets,
                values,
                width=width,
                label=name,
            )

        plt.xticks(
            x,
            [
                "Point",
                "Indexed",
                "1-hop",
                "2-hop",
                "3-hop",
                "Aggregation",
            ],
        )

        plt.ylabel("Latency (ms)")

        plt.title(
            "Read Workload "
            + percentile_name
            .replace("_", " ")
            .upper()
        )

        plt.legend()
        plt.tight_layout()

        plt.savefig(
            CHARTS /
            f"read_{percentile_name}.png",
            dpi=180,
        )

        plt.close()

    # =====================================================
    # CHART 4 — Mixed QPS scaling
    # =====================================================

    plt.figure(figsize=(10, 6))

    for key, name in PLATFORMS:
        results = mixed_data[key]["results"]

        plt.plot(
            [
                row["concurrency"]
                for row in results
            ],
            [
                row["qps"]
                for row in results
            ],
            marker="o",
            label=name,
        )

    plt.xlabel("Concurrent clients")
    plt.ylabel("Queries / second")
    plt.title(
        "90/10 Mixed Read/Write Throughput"
    )

    plt.xticks([1, 10, 40])

    plt.legend()
    plt.tight_layout()

    plt.savefig(
        CHARTS /
        "mixed_qps_scaling.png",
        dpi=180,
    )

    plt.close()

    # =====================================================
    # CHART 5 — Mixed p95
    # =====================================================

    plt.figure(figsize=(10, 6))

    for key, name in PLATFORMS:
        results = mixed_data[key]["results"]

        plt.plot(
            [
                row["concurrency"]
                for row in results
            ],
            [
                row["all_latency"]
                ["p95_ms"]
                for row in results
            ],
            marker="o",
            label=name,
        )

    plt.xlabel("Concurrent clients")
    plt.ylabel("p95 latency (ms)")
    plt.title(
        "90/10 Mixed Workload p95 Latency"
    )

    plt.xticks([1, 10, 40])

    plt.legend()
    plt.tight_layout()

    plt.savefig(
        CHARTS /
        "mixed_p95_latency.png",
        dpi=180,
    )

    plt.close()

    # =====================================================
    # MARKDOWN SUMMARY
    # =====================================================

    md = []

    md.append("# Benchmark Results\n")

    md.append(
        "Generated automatically from the raw JSON "
        "benchmark outputs.\n"
    )

    md.append("## Ingest throughput\n")

    md.append(
        markdown_table(
            [
                "Platform",
                "Nodes/s",
                "Relationships/s",
                "Relationship load (s)",
                "End-to-end (s)",
            ],
            [
                [
                    row["platform"],
                    row["nodes_per_second"],
                    row[
                        "relationships_per_second"
                    ],
                    row[
                        "relationship_load_seconds"
                    ],
                    row[
                        "end_to_end_seconds"
                    ],
                ]
                for row in ingest_rows
            ],
        )
    )

    md.append("\n## Read latency — p50 (ms)\n")

    p50_rows = []

    for key, name in PLATFORMS:
        p50_rows.append(
            [
                name,
                *[
                    round(
                        read_data[key]
                        ["workloads"]
                        [workload]
                        ["statistics"]
                        ["p50_ms"],
                        3,
                    )
                    for workload in WORKLOADS
                ],
            ]
        )

    md.append(
        markdown_table(
            [
                "Platform",
                "Point",
                "Indexed",
                "1-hop",
                "2-hop",
                "3-hop",
                "Aggregation",
            ],
            p50_rows,
        )
    )

    md.append("\n## Read latency — p95 (ms)\n")

    p95_rows = []

    for key, name in PLATFORMS:
        p95_rows.append(
            [
                name,
                *[
                    round(
                        read_data[key]
                        ["workloads"]
                        [workload]
                        ["statistics"]
                        ["p95_ms"],
                        3,
                    )
                    for workload in WORKLOADS
                ],
            ]
        )

    md.append(
        markdown_table(
            [
                "Platform",
                "Point",
                "Indexed",
                "1-hop",
                "2-hop",
                "3-hop",
                "Aggregation",
            ],
            p95_rows,
        )
    )

    md.append(
        "\n## Mixed workload throughput (QPS)\n"
    )

    qps_rows = []

    for key, name in PLATFORMS:
        lookup = {
            item["concurrency"]:
                round(item["qps"], 2)
            for item in mixed_data[key]["results"]
        }

        qps_rows.append([
            name,
            lookup[1],
            lookup[10],
            lookup[40],
        ])

    md.append(
        markdown_table(
            [
                "Platform",
                "C=1",
                "C=10",
                "C=40",
            ],
            qps_rows,
        )
    )

    summary_path = (
        RESULTS /
        "SUMMARY.md"
    )

    summary_path.write_text(
        "\n".join(md) + "\n",
        encoding="utf-8",
    )

    print()
    print("==============================================")
    print(" ✅ MASTER RESULTS GENERATED")
    print("==============================================")
    print("Validation:")
    print("  5/5 ingest integrity checks passed")
    print("  30/30 read workload sets passed")
    print("  15/15 mixed concurrency points had 0 errors")
    print()
    print("Generated:")
    print("  results/summary_ingest.csv")
    print("  results/summary_reads.csv")
    print("  results/summary_mixed.csv")
    print("  results/SUMMARY.md")
    print()
    print("Charts:")
    print("  charts/ingest_relationship_throughput.png")
    print("  charts/read_p50_ms.png")
    print("  charts/read_p95_ms.png")
    print("  charts/mixed_qps_scaling.png")
    print("  charts/mixed_p95_latency.png")


if __name__ == "__main__":
    main()
