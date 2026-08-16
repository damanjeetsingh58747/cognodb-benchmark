from __future__ import annotations

import json
import math
import os
import statistics
import time
from pathlib import Path

import certifi
from dotenv import load_dotenv
from neo4j import GraphDatabase
from falkordb import FalkorDB
from arango import ArangoClient


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "raw"

os.environ.setdefault("SSL_CERT_FILE", certifi.where())

WARMUP = 20
RUNS = 120


def percentile(values, p):
    values = sorted(values)

    pos = (len(values) - 1) * p
    lower = math.floor(pos)
    upper = math.ceil(pos)

    if lower == upper:
        return values[lower]

    return (
        values[lower] * (upper - pos)
        + values[upper] * (pos - lower)
    )


def summarize(values):
    return {
        "runs": len(values),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "p99_ms": percentile(values, 0.99),
        "mean_ms": statistics.mean(values),
        "stdev_ms": statistics.stdev(values),
        "min_ms": min(values),
        "max_ms": max(values),
    }


def benchmark_bolt(name, uri, user, password):
    driver = GraphDatabase.driver(
        uri,
        auth=(user, password),
    )

    driver.verify_connectivity()

    with driver.session() as session:

        for _ in range(WARMUP):
            session.run("RETURN 1 AS value").consume()

        latencies = []

        for _ in range(RUNS):
            start = time.perf_counter_ns()

            session.run(
                "RETURN 1 AS value"
            ).consume()

            latencies.append(
                (
                    time.perf_counter_ns()
                    - start
                ) / 1_000_000
            )

    driver.close()

    return summarize(latencies)


def benchmark_falkor():
    client = FalkorDB(
        host=os.environ["FALKORDB_HOST"],
        port=int(os.environ["FALKORDB_PORT"]),
        username=os.environ["FALKORDB_USER"],
        password=os.environ["FALKORDB_PASSWORD"],
    )

    graph = client.select_graph(
        "wexa_benchmark"
    )

    for _ in range(WARMUP):
        graph.query("RETURN 1")

    latencies = []

    for _ in range(RUNS):
        start = time.perf_counter_ns()

        graph.query("RETURN 1")

        latencies.append(
            (
                time.perf_counter_ns()
                - start
            ) / 1_000_000
        )

    return summarize(latencies)


def benchmark_arango():
    client = ArangoClient(
        hosts=os.environ["ARANGO_URL"]
    )

    db = client.db(
        os.environ.get(
            "ARANGO_DATABASE",
            "wexa_benchmark",
        ),
        username=os.environ["ARANGO_USER"],
        password=os.environ["ARANGO_PASSWORD"],
    )

    for _ in range(WARMUP):
        list(
            db.aql.execute(
                "RETURN 1"
            )
        )

    latencies = []

    for _ in range(RUNS):
        start = time.perf_counter_ns()

        list(
            db.aql.execute(
                "RETURN 1"
            )
        )

        latencies.append(
            (
                time.perf_counter_ns()
                - start
            ) / 1_000_000
        )

    return summarize(latencies)


def main():
    load_dotenv(ROOT / ".env")

    print("==============================================")
    print(" Control / Baseline Latency Benchmark")
    print("==============================================")
    print(f"Warm-up:  {WARMUP}")
    print(f"Measured: {RUNS}")
    print()

    results = {}

    results["cognodb"] = benchmark_bolt(
        "CognoDB",
        os.environ["COGNODB_URI"],
        os.environ["COGNODB_USER"],
        os.environ["COGNODB_PASSWORD"],
    )

    print("✅ CognoDB")

    results["neo4j"] = benchmark_bolt(
        "Neo4j",
        os.environ["NEO4J_URI"],
        os.environ["NEO4J_USER"],
        os.environ["NEO4J_PASSWORD"],
    )

    print("✅ Neo4j")

    results["memgraph"] = benchmark_bolt(
        "Memgraph",
        os.environ["MEMGRAPH_URI"],
        os.environ["MEMGRAPH_USER"],
        os.environ["MEMGRAPH_PASSWORD"],
    )

    print("✅ Memgraph")

    results["falkordb"] = benchmark_falkor()

    print("✅ FalkorDB")

    results["arangodb"] = benchmark_arango()

    print("✅ ArangoDB")

    output = RESULTS / "control_latency.json"

    output.write_text(
        json.dumps(
            results,
            indent=2,
        ),
        encoding="utf-8",
    )

    names = {
        "cognodb": "CognoDB",
        "neo4j": "Neo4j AuraDB",
        "falkordb": "FalkorDB",
        "memgraph": "Memgraph",
        "arangodb": "ArangoDB",
    }

    print()
    print("==============================================")
    print(" ✅ CONTROL LATENCY COMPLETE")
    print("==============================================")

    for key in [
        "cognodb",
        "neo4j",
        "falkordb",
        "memgraph",
        "arangodb",
    ]:
        s = results[key]

        print(
            f"{names[key]:16s} "
            f"p50={s['p50_ms']:8.3f} ms | "
            f"p95={s['p95_ms']:8.3f} ms"
        )

    print()
    print(f"Raw result: {output}")


if __name__ == "__main__":
    main()
