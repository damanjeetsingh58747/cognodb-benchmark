from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "results" / "runs"
RESULTS_DIR = ROOT / "results"
CHARTS_DIR = ROOT / "charts"

PLATFORMS = [
    ("cognodb", "CognoDB"),
    ("neo4j", "Neo4j AuraDB"),
    ("falkordb", "FalkorDB"),
    ("memgraph", "Memgraph"),
    ("arangodb", "ArangoDB"),
]

WORKLOADS = [
    ("point_lookup", "Point"),
    ("indexed_lookup", "Indexed"),
    ("traversal_1hop", "1-hop"),
    ("traversal_2hop", "2-hop"),
    ("traversal_3hop", "3-hop"),
    ("aggregation_rating_counts", "Aggregation"),
]

CONCURRENCY = [1, 10, 40]


def load_json(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Missing repeated-run evidence: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        raise ValueError("No values supplied")
    mean = statistics.mean(values)
    stdev = statistics.stdev(values) if len(values) > 1 else 0.0
    return mean, stdev


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    run_dirs = sorted(p for p in RUNS_DIR.glob("run_*") if p.is_dir())
    if len(run_dirs) < 3:
        raise SystemExit(
            "Need at least 3 archived runs under results/runs/run_XX. "
            f"Found {len(run_dirs)}."
        )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    ingest_rows: list[dict] = []
    read_rows: list[dict] = []
    mixed_rows: list[dict] = []
    control_rows: list[dict] = []

    ingest_plot: dict[str, tuple[float, float]] = {}
    read_plot: dict[str, list[tuple[float, float]]] = {}
    mixed_plot: dict[str, list[tuple[float, float]]] = {}
    control_plot: dict[str, tuple[float, float]] = {}

    for platform_key, platform_name in PLATFORMS:
        ingest_docs = [
            load_json(run / f"{platform_key}_ingest.json")
            for run in run_dirs
        ]
        nodes = [d["throughput"]["nodes_per_second"] for d in ingest_docs]
        rels = [d["throughput"]["relationships_per_second"] for d in ingest_docs]
        rel_load = [d["timings_seconds"]["relationships"] for d in ingest_docs]
        end_to_end = [d["timings_seconds"]["end_to_end"] for d in ingest_docs]

        nodes_mean, nodes_std = mean_std(nodes)
        rels_mean, rels_std = mean_std(rels)
        rel_load_mean, rel_load_std = mean_std(rel_load)
        end_mean, end_std = mean_std(end_to_end)

        ingest_rows.append(
            {
                "platform": platform_name,
                "runs": len(run_dirs),
                "nodes_per_second_mean": nodes_mean,
                "nodes_per_second_stdev": nodes_std,
                "relationships_per_second_mean": rels_mean,
                "relationships_per_second_stdev": rels_std,
                "relationship_load_seconds_mean": rel_load_mean,
                "relationship_load_seconds_stdev": rel_load_std,
                "end_to_end_seconds_mean": end_mean,
                "end_to_end_seconds_stdev": end_std,
            }
        )
        ingest_plot[platform_name] = (rels_mean, rels_std)

        read_docs = [
            load_json(run / f"{platform_key}_reads.json")
            for run in run_dirs
        ]
        read_plot[platform_name] = []

        for workload_key, workload_name in WORKLOADS:
            p50_values = [
                d["workloads"][workload_key]["statistics"]["p50_ms"]
                for d in read_docs
            ]
            p95_values = [
                d["workloads"][workload_key]["statistics"]["p95_ms"]
                for d in read_docs
            ]
            p99_values = [
                d["workloads"][workload_key]["statistics"]["p99_ms"]
                for d in read_docs
            ]

            p50_mean, p50_std = mean_std(p50_values)
            p95_mean, p95_std = mean_std(p95_values)
            p99_mean, p99_std = mean_std(p99_values)

            read_rows.append(
                {
                    "platform": platform_name,
                    "workload": workload_key,
                    "runs": len(run_dirs),
                    "p50_ms_mean": p50_mean,
                    "p50_ms_stdev": p50_std,
                    "p95_ms_mean": p95_mean,
                    "p95_ms_stdev": p95_std,
                    "p99_ms_mean": p99_mean,
                    "p99_ms_stdev": p99_std,
                }
            )
            read_plot[platform_name].append((p50_mean, p50_std))

        mixed_docs = [
            load_json(run / f"{platform_key}_mixed.json")
            for run in run_dirs
        ]
        mixed_plot[platform_name] = []

        for concurrency in CONCURRENCY:
            run_points = []
            for doc in mixed_docs:
                match = next(
                    row for row in doc["results"]
                    if row["concurrency"] == concurrency
                )
                run_points.append(match)

            qps_values = [row["qps"] for row in run_points]
            p50_values = [row["all_latency"]["p50_ms"] for row in run_points]
            p95_values = [row["all_latency"]["p95_ms"] for row in run_points]
            error_values = [row["errors"] for row in run_points]

            qps_mean, qps_std = mean_std(qps_values)
            p50_mean, p50_std = mean_std(p50_values)
            p95_mean, p95_std = mean_std(p95_values)

            mixed_rows.append(
                {
                    "platform": platform_name,
                    "concurrency": concurrency,
                    "runs": len(run_dirs),
                    "qps_mean": qps_mean,
                    "qps_stdev": qps_std,
                    "p50_ms_mean": p50_mean,
                    "p50_ms_stdev": p50_std,
                    "p95_ms_mean": p95_mean,
                    "p95_ms_stdev": p95_std,
                    "total_errors": sum(error_values),
                }
            )
            mixed_plot[platform_name].append((qps_mean, qps_std))

        control_docs = [
            load_json(run / "control_latency.json")
            for run in run_dirs
        ]
        p50_values = [d[platform_key]["p50_ms"] for d in control_docs]
        p95_values = [d[platform_key]["p95_ms"] for d in control_docs]
        p50_mean, p50_std = mean_std(p50_values)
        p95_mean, p95_std = mean_std(p95_values)

        control_rows.append(
            {
                "platform": platform_name,
                "runs": len(run_dirs),
                "p50_ms_mean": p50_mean,
                "p50_ms_stdev": p50_std,
                "p95_ms_mean": p95_mean,
                "p95_ms_stdev": p95_std,
            }
        )
        control_plot[platform_name] = (p50_mean, p50_std)

    write_csv(
        RESULTS_DIR / "repeated_summary_ingest.csv",
        list(ingest_rows[0].keys()),
        ingest_rows,
    )
    write_csv(
        RESULTS_DIR / "repeated_summary_reads.csv",
        list(read_rows[0].keys()),
        read_rows,
    )
    write_csv(
        RESULTS_DIR / "repeated_summary_mixed.csv",
        list(mixed_rows[0].keys()),
        mixed_rows,
    )
    write_csv(
        RESULTS_DIR / "repeated_summary_control.csv",
        list(control_rows[0].keys()),
        control_rows,
    )

    # Relationship ingest mean +/- sample standard deviation.
    names = list(ingest_plot)
    means = [ingest_plot[name][0] for name in names]
    errors = [ingest_plot[name][1] for name in names]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.bar(names, means, yerr=errors, capsize=5)
    ax.set_ylabel("Relationships / second")
    ax.set_title(f"Relationship ingest throughput across {len(run_dirs)} runs")
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "repeated_ingest_relationships_mean_std.png", dpi=180)
    plt.close(fig)

    # Read p50 mean +/- sample standard deviation for each workload.
    x = list(range(len(WORKLOADS)))
    fig, ax = plt.subplots(figsize=(11, 6))
    for platform_name, values in read_plot.items():
        means = [v[0] for v in values]
        errors = [v[1] for v in values]
        ax.errorbar(x, means, yerr=errors, marker="o", capsize=3, label=platform_name)
    ax.set_xticks(x, [label for _, label in WORKLOADS])
    ax.set_ylabel("Client-observed p50 latency (ms)")
    ax.set_title(f"Read p50 latency across {len(run_dirs)} runs")
    ax.legend()
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "repeated_read_p50_mean_std.png", dpi=180)
    plt.close(fig)

    # Mixed QPS scaling mean +/- sample standard deviation.
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for platform_name, values in mixed_plot.items():
        means = [v[0] for v in values]
        errors = [v[1] for v in values]
        ax.errorbar(CONCURRENCY, means, yerr=errors, marker="o", capsize=3, label=platform_name)
    ax.set_xlabel("Client concurrency")
    ax.set_ylabel("Sustained QPS")
    ax.set_title(f"Mixed 90/10 QPS scaling across {len(run_dirs)} runs")
    ax.set_xticks(CONCURRENCY)
    ax.legend()
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "repeated_mixed_qps_mean_std.png", dpi=180)
    plt.close(fig)

    # Control p50 mean +/- sample standard deviation.
    names = list(control_plot)
    means = [control_plot[name][0] for name in names]
    errors = [control_plot[name][1] for name in names]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.bar(names, means, yerr=errors, capsize=5)
    ax.set_ylabel("Control p50 latency (ms)")
    ax.set_title(f"Control-query variability across {len(run_dirs)} runs")
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "repeated_control_p50_mean_std.png", dpi=180)
    plt.close(fig)

    ingest_by_name = {row["platform"]: row for row in ingest_rows}
    control_by_name = {row["platform"]: row for row in control_rows}
    mixed_c40 = {
        row["platform"]: row
        for row in mixed_rows
        if row["concurrency"] == 40
    }

    md: list[str] = [
        "# Repeated Trial Analysis",
        "",
        f"This analysis aggregates **{len(run_dirs)} separate full benchmark executions**.",
        "",
        "Values below are reported as **mean +/- sample standard deviation across runs**. This is separate from the within-run latency standard deviation already preserved in each raw JSON result. For latency percentiles, each repeated value is computed from the per-run percentile values; the 360 measured observations are not pooled into one percentile calculation.",
        "",
        "The same canonical MovieLens 100K graph, deterministic read manifest, query definitions, client machine and benchmark harness were used for all archived runs.",
        "",
        "## Relationship ingest throughput",
        "",
        "| Platform | Relationships/s (mean +/- std) | Relationship load s (mean +/- std) |",
        "|---|---:|---:|",
    ]

    for _, name in PLATFORMS:
        row = ingest_by_name[name]
        md.append(
            f"| {name} | {row['relationships_per_second_mean']:.1f} +/- {row['relationships_per_second_stdev']:.1f} | "
            f"{row['relationship_load_seconds_mean']:.3f} +/- {row['relationship_load_seconds_stdev']:.3f} |"
        )

    md += [
        "",
        "![Repeated ingest throughput](../charts/repeated_ingest_relationships_mean_std.png)",
        "",
        "## Read p50 latency",
        "",
        "![Repeated read p50](../charts/repeated_read_p50_mean_std.png)",
        "",
        "Detailed run-level p50/p95/p99 mean and standard-deviation values are in `repeated_summary_reads.csv`.",
        "",
        "## Mixed workload at concurrency 40",
        "",
        "| Platform | QPS (mean +/- std) | p95 ms (mean +/- std) | Errors across runs |",
        "|---|---:|---:|---:|",
    ]

    for _, name in PLATFORMS:
        row = mixed_c40[name]
        md.append(
            f"| {name} | {row['qps_mean']:.2f} +/- {row['qps_stdev']:.2f} | "
            f"{row['p95_ms_mean']:.3f} +/- {row['p95_ms_stdev']:.3f} | {row['total_errors']} |"
        )

    md += [
        "",
        "![Repeated mixed QPS](../charts/repeated_mixed_qps_mean_std.png)",
        "",
        "## Control-query variability",
        "",
        "| Platform | Control p50 ms (mean +/- std) | Control p95 ms (mean +/- std) |",
        "|---|---:|---:|",
    ]

    for _, name in PLATFORMS:
        row = control_by_name[name]
        md.append(
            f"| {name} | {row['p50_ms_mean']:.3f} +/- {row['p50_ms_stdev']:.3f} | "
            f"{row['p95_ms_mean']:.3f} +/- {row['p95_ms_stdev']:.3f} |"
        )

    md += [
        "",
        "![Repeated control latency](../charts/repeated_control_p50_mean_std.png)",
        "",
        "## Interpretation",
        "",
        "Run-to-run variance is expected in public managed services because network conditions, provider scheduling, throttling and shared infrastructure can change between executions. Reporting multiple separate executions therefore makes the comparison more defensible than relying on one production run alone.",
        "",
        "These repeated measurements still do not turn the comparison into a hardware-normalized engine benchmark; the resource-parity caveats in `docs/fairness.md` continue to apply.",
        "",
        "## Evidence layout",
        "",
    ]

    for run in run_dirs:
        md.append(f"- `{run.relative_to(ROOT)}/` - archived raw JSON for {run.name}")

    (RESULTS_DIR / "REPEATED_RUNS.md").write_text(
        "\n".join(md) + "\n",
        encoding="utf-8",
    )

    print("==============================================")
    print(" REPEATED TRIAL ANALYSIS COMPLETE")
    print("==============================================")
    print(f"Runs aggregated: {len(run_dirs)}")
    print("Created:")
    print("  results/repeated_summary_ingest.csv")
    print("  results/repeated_summary_reads.csv")
    print("  results/repeated_summary_mixed.csv")
    print("  results/repeated_summary_control.csv")
    print("  results/REPEATED_RUNS.md")
    print("  charts/repeated_*_mean_std.png")


if __name__ == "__main__":
    main()
