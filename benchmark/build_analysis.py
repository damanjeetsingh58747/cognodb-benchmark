from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results" / "raw"
DOCS = ROOT / "docs"

PLATFORMS = [
    ("cognodb", "CognoDB"),
    ("neo4j", "Neo4j AuraDB"),
    ("falkordb", "FalkorDB"),
    ("memgraph", "Memgraph"),
    ("arangodb", "ArangoDB"),
]

WORKLOADS = [
    ("point_lookup", "Point lookup"),
    ("indexed_lookup", "Indexed lookup"),
    ("traversal_1hop", "1-hop"),
    ("traversal_2hop", "2-hop"),
    ("traversal_3hop", "3-hop"),
    ("aggregation_rating_counts", "Aggregation"),
]


def load(name):
    return json.loads(
        (RAW / name).read_text(encoding="utf-8")
    )


def main():
    control = load("control_latency.json")

    ingest = {
        key: load(f"{key}_ingest.json")
        for key, _ in PLATFORMS
    }

    reads = {
        key: load(f"{key}_reads.json")
        for key, _ in PLATFORMS
    }

    mixed = {
        key: load(f"{key}_mixed.json")
        for key, _ in PLATFORMS
    }

    lines = []

    lines.append("# Benchmark Analysis")
    lines.append("")
    lines.append(
        "This section interprets the measured results without "
        "assuming that managed-service latency differences are "
        "caused solely by database-engine implementation."
    )

    # --------------------------------------------------
    # Executive findings
    # --------------------------------------------------

    lines.append("")
    lines.append("## Executive findings")
    lines.append("")

    # ingest ranking
    ranking = sorted(
        PLATFORMS,
        key=lambda x: ingest[x[0]]["throughput"]
        ["relationships_per_second"],
        reverse=True,
    )

    best_key, best_name = ranking[0]
    best_ingest = ingest[best_key]["throughput"][
        "relationships_per_second"
    ]

    lines.append(
        f"- **{best_name} recorded the highest relationship "
        f"ingest throughput in this run** at "
        f"{best_ingest:,.1f} relationships/s."
    )

    # mixed C40 ranking
    def c40(key):
        return next(
            row for row in mixed[key]["results"]
            if row["concurrency"] == 40
        )

    mixed_ranking = sorted(
        PLATFORMS,
        key=lambda x: c40(x[0])["qps"],
        reverse=True,
    )

    top_mixed_key, top_mixed_name = mixed_ranking[0]

    lines.append(
        f"- **{top_mixed_name} also recorded the highest "
        f"40-client mixed-workload throughput**, at "
        f"{c40(top_mixed_key)['qps']:.2f} QPS."
    )

    lines.append(
        "- All five final mixed-workload runs completed with "
        "**zero recorded errors** at concurrency 1, 10 and 40."
    )

    lines.append(
        "- Control-query measurements show that network, protocol "
        "and managed-service overhead account for a substantial "
        "part of simple-query latency on several platforms."
    )

    lines.append(
        "- Because free/trial resource allocations and regions were "
        "not identical, these results are best interpreted as a "
        "**managed-tier comparison**, not an isolated engine benchmark."
    )

    # --------------------------------------------------
    # Ingest
    # --------------------------------------------------

    lines.append("")
    lines.append("## Ingest")
    lines.append("")
    lines.append(
        "| Platform | Nodes/s | Relationships/s | "
        "Relationship load (s) |"
    )
    lines.append("|---|---:|---:|---:|")

    for key, name in PLATFORMS:
        d = ingest[key]

        lines.append(
            f"| {name} | "
            f"{d['throughput']['nodes_per_second']:,.1f} | "
            f"{d['throughput']['relationships_per_second']:,.1f} | "
            f"{d['timings_seconds']['relationships']:.3f} |"
        )

    lines.append("")
    lines.append(
        "Neo4j AuraDB produced the highest ingest throughput in this "
        "specific run. This should not be treated as an engine-only "
        "speedup because the managed tiers expose different and, in "
        "some cases, undisclosed compute allocations."
    )

    # --------------------------------------------------
    # Control latency
    # --------------------------------------------------

    lines.append("")
    lines.append("## Control-query latency")
    lines.append("")
    lines.append(
        "A trivial `RETURN 1` query was measured using the same "
        "20-warm-up / 120-measured policy. It does not represent pure "
        "network RTT and is treated only as a client-observed reference "
        "measurement."
    )
    lines.append("")
    lines.append("| Platform | Control p50 | Control p95 |")
    lines.append("|---|---:|---:|")

    for key, name in PLATFORMS:
        s = control[key]

        lines.append(
            f"| {name} | {s['p50_ms']:.3f} ms | "
            f"{s['p95_ms']:.3f} ms |"
        )

    # --------------------------------------------------
    # Read latency
    # --------------------------------------------------

    lines.append("")
    lines.append("## Read workloads")
    lines.append("")
    lines.append(
        "| Platform | Point | Indexed | 1-hop | "
        "2-hop | 3-hop | Aggregation |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|")

    for key, name in PLATFORMS:
        values = []

        for workload, _ in WORKLOADS:
            values.append(
                reads[key]["workloads"][workload]
                ["statistics"]["p50_ms"]
            )

        lines.append(
            f"| {name} | "
            + " | ".join(f"{v:.3f}" for v in values)
            + " |"
        )

    lines.append("")
    lines.append(
        "Neo4j's point-lookup p50 was close to its control-query p50. "
        "CognoDB and ArangoDB showed larger differences, demonstrating "
        "that the control measurement itself can vary materially. The "
        "control results are therefore treated as context rather than "
        "values to subtract from workload latency."
    )

    lines.append("")
    lines.append(
        "ArangoDB's 2-hop workload moved substantially above its control "
        "reference, while its bounded 3-hop p50 remained much closer to "
        "the control p50. This contrast reinforces that traversal cost "
        "and managed-service overhead interact differently across query "
        "shapes."
    )

    lines.append("")
    lines.append(
        "CognoDB's production 3-hop workload completed successfully, "
        "but the earlier exhaustive 3-hop pilot exceeded the service "
        "execution deadline. That pilot failure is intentionally retained "
        "in `docs/pilot_3hop_timeout.md`."
    )

    # --------------------------------------------------
    # Mixed
    # --------------------------------------------------

    lines.append("")
    lines.append("## Mixed 90/10 workload")
    lines.append("")
    lines.append("| Platform | QPS @1 | QPS @10 | QPS @40 |")
    lines.append("|---|---:|---:|---:|")

    for key, name in PLATFORMS:
        lookup = {
            r["concurrency"]: r
            for r in mixed[key]["results"]
        }

        lines.append(
            f"| {name} | "
            f"{lookup[1]['qps']:.2f} | "
            f"{lookup[10]['qps']:.2f} | "
            f"{lookup[40]['qps']:.2f} |"
        )

    lines.append("")
    lines.append(
        "Every platform increased aggregate throughput as client "
        "concurrency rose from 1 to 40. Neo4j AuraDB reached the "
        f"highest measured value at {c40('neo4j')['qps']:.2f} QPS. "
        "FalkorDB, Memgraph and CognoDB formed the next group, while "
        f"ArangoDB reached {c40('arangodb')['qps']:.2f} QPS."
    )

    # --------------------------------------------------
    # Interpretation
    # --------------------------------------------------

    lines.append("")
    lines.append("## What these numbers do — and do not — prove")
    lines.append("")
    lines.append(
        "The benchmark demonstrates how these **actual managed "
        "configurations** behaved under one reproducible workload."
    )
    lines.append("")
    lines.append(
        "It does not establish that one underlying database engine is "
        "universally faster than another. Differences in CPU, RAM, "
        "service throttling, network region, protocol, cloud provider "
        "and query language all remain possible contributors."
    )
    lines.append("")
    lines.append(
        "For that reason, control-query latency is shown as context but "
        "is **not subtracted** from workload latency to manufacture an "
        "'engine-only' number."
    )

    DOCS.mkdir(exist_ok=True)

    output = DOCS / "analysis.md"

    output.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print("==============================================")
    print(" ✅ ANALYSIS GENERATED")
    print("==============================================")
    print(f"Created: {output}")


if __name__ == "__main__":
    main()
