from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from falkordb import FalkorDB


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs"
RESULTS = ROOT / "results" / "raw"

GRAPH_NAME = "wexa_benchmark"

WARMUP_RUNS = 20
MEASURED_RUNS = 120


WORKLOADS = {
    "point_lookup": {
        "query": """
            MATCH (u:User {user_id: $user_id})
            RETURN u.age AS value
        """,
        "input": "user",
    },

    "indexed_lookup": {
        "query": """
            MATCH (m:Movie {release_year: $release_year})
            RETURN count(m) AS value
        """,
        "input": "year",
    },

    "traversal_1hop": {
        "query": """
            MATCH (:User {user_id: $user_id})
                  -[:RATED]->(m:Movie)
            RETURN count(m) AS value
        """,
        "input": "user",
    },

    "traversal_2hop": {
        "query": """
            MATCH (:User {user_id: $user_id})
                  -[:RATED]->(:Movie)
                  <-[:RATED]-(other:User)
            WHERE other.user_id <> $user_id
            RETURN count(DISTINCT other) AS value
        """,
        "input": "user",
    },

    "traversal_3hop": {
        "query": """
            MATCH (:User {user_id: $user_id})
                  -[:RATED]->(:Movie)
                  <-[:RATED]-(other:User)
                  -[:RATED]->(target:Movie {
                      movie_id: $target_movie_id
                  })
            WHERE other.user_id <> $user_id
            RETURN target.movie_id AS value
            LIMIT 1
        """,
        "input": "user_target",
    },

    "aggregation_rating_counts": {
        "query": """
            MATCH ()-[r:RATED]->()
            RETURN r.rating AS rating,
                   count(*) AS count
            ORDER BY rating
        """,
        "input": "none",
    },
}


def percentile(values, p):
    values = sorted(values)

    if len(values) == 1:
        return values[0]

    k = (len(values) - 1) * p

    lower = math.floor(k)
    upper = math.ceil(k)

    if lower == upper:
        return values[lower]

    return (
        values[lower] * (upper - k)
        + values[upper] * (k - lower)
    )


def stats(values):
    return {
        "n": len(values),
        "mean_ms": statistics.mean(values),
        "stdev_ms": (
            statistics.stdev(values)
            if len(values) > 1
            else 0.0
        ),
        "min_ms": min(values),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "p99_ms": percentile(values, 0.99),
        "max_ms": max(values),
    }


def fingerprint(values):
    payload = json.dumps(
        values,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


def parameters(input_type, manifest, warmup):
    if input_type == "user":
        key = (
            "warmup_user_ids"
            if warmup
            else "measured_user_ids"
        )

        return [
            {"user_id": value}
            for value in manifest[key]
        ]

    if input_type == "user_target":
        key = (
            "warmup_user_ids"
            if warmup
            else "measured_user_ids"
        )

        return [
            {
                "user_id": value,
                "target_movie_id":
                    ((value * 37) % 1682) + 1,
            }
            for value in manifest[key]
        ]

    if input_type == "year":
        key = (
            "warmup_release_years"
            if warmup
            else "measured_release_years"
        )

        return [
            {"release_year": value}
            for value in manifest[key]
        ]

    count = WARMUP_RUNS if warmup else MEASURED_RUNS
    return [{} for _ in range(count)]


def run_workload(graph, name, config, manifest):
    query = config["query"]
    input_type = config["input"]

    warmups = parameters(
        input_type,
        manifest,
        True,
    )

    measured = parameters(
        input_type,
        manifest,
        False,
    )

    print()
    print(f"--- {name} ---")
    print(
        f"Warm-up: {len(warmups)} | "
        f"Measured: {len(measured)}"
    )

    # Warm-up.
    for params in warmups:
        graph.query(query, params)

    latencies = []
    outputs = []
    errors = []

    for i, params in enumerate(measured, 1):
        try:
            start_ns = time.perf_counter_ns()

            result = graph.query(
                query,
                params,
            )

            elapsed_ms = (
                time.perf_counter_ns() - start_ns
            ) / 1_000_000

            latencies.append(elapsed_ms)

            outputs.append({
                "params": params,
                "result": result.result_set,
            })

        except Exception as exc:
            errors.append({
                "iteration": i,
                "params": params,
                "error_type":
                    type(exc).__name__,
                "error": str(exc),
            })

    if not latencies:
        raise RuntimeError(
            f"All measured runs failed: {name}"
        )

    summary = stats(latencies)

    print(
        f"p50={summary['p50_ms']:.3f} ms | "
        f"p95={summary['p95_ms']:.3f} ms | "
        f"p99={summary['p99_ms']:.3f} ms"
    )

    print(
        f"mean={summary['mean_ms']:.3f} ms | "
        f"std={summary['stdev_ms']:.3f} ms | "
        f"errors={len(errors)}"
    )

    return {
        "query": " ".join(query.split()),
        "warmup_runs": len(warmups),
        "requested_measured_runs":
            len(measured),
        "successful_runs":
            len(latencies),
        "error_count":
            len(errors),
        "statistics":
            summary,
        "latencies_ms":
            latencies,
        "result_fingerprint_sha256":
            fingerprint(outputs),
        "errors":
            errors,
    }


def main():
    load_dotenv(ROOT / ".env")

    manifest_path = (
        CONFIG / "read_manifest.json"
    )

    if not manifest_path.exists():
        raise SystemExit(
            "read_manifest.json missing. "
            "Do not regenerate it."
        )

    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    db = FalkorDB(
        host=os.environ["FALKORDB_HOST"],
        port=int(
            os.environ["FALKORDB_PORT"]
        ),
        username=os.environ[
            "FALKORDB_USER"
        ],
        password=os.environ[
            "FALKORDB_PASSWORD"
        ],
    )

    graph = db.select_graph(
        GRAPH_NAME
    )

    print("==============================================")
    print(" FalkorDB — Read Workload Benchmark")
    print("==============================================")
    print(
        f"Random seed:   "
        f"{manifest['seed']}"
    )
    print(
        f"Warm-up runs:  "
        f"{WARMUP_RUNS}"
    )
    print(
        f"Measured runs: "
        f"{MEASURED_RUNS}"
    )
    print()

    graph.query(
        "RETURN 1 AS connection_test"
    )

    print("✅ Connected to FalkorDB")

    # Required filtered/indexed lookup index.
    try:
        graph.query(
            "CREATE INDEX FOR (m:Movie) "
            "ON (m.release_year)"
        )

        print(
            "✅ Created Movie.release_year index"
        )

    except Exception as exc:
        message = str(exc).lower()

        if (
            "already indexed" in message
            or "already exists" in message
        ):
            print(
                "✅ Movie.release_year index "
                "already exists"
            )
        else:
            raise

    results = {}

    benchmark_start = time.perf_counter()

    for name, config in WORKLOADS.items():
        results[name] = run_workload(
            graph,
            name,
            config,
            manifest,
        )

    total_seconds = (
        time.perf_counter()
        - benchmark_start
    )

    output = {
        "platform":
            "FalkorDB Cloud Free",
        "dataset":
            "MovieLens 100K",
        "timestamp_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),
        "methodology": {
            "client_side_latency":
                True,
            "timer":
                "time.perf_counter_ns",
            "seed":
                manifest["seed"],
            "warmup_runs_per_workload":
                WARMUP_RUNS,
            "measured_runs_per_workload":
                MEASURED_RUNS,
            "indexed_properties": [
                "User.user_id",
                "Movie.movie_id",
                "Movie.release_year",
            ],
            "graph":
                GRAPH_NAME,
            "cloud":
                "AWS",
            "region":
                "us-east-1",
        },
        "workloads":
            results,
        "total_benchmark_seconds":
            total_seconds,
    }

    RESULTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        RESULTS /
        "falkordb_reads.json"
    )

    output_path.write_text(
        json.dumps(
            output,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("==============================================")
    print(" ✅ FALKORDB READ BENCHMARK COMPLETE")
    print("==============================================")

    for name, result in results.items():
        s = result["statistics"]

        print(
            f"{name:27s} "
            f"p50={s['p50_ms']:9.3f} ms | "
            f"p95={s['p95_ms']:9.3f} ms"
        )

    print()
    print(
        f"Total benchmark time: "
        f"{total_seconds:.2f}s"
    )
    print(
        f"Raw result: "
        f"{output_path}"
    )
    print(
        f"Input manifest: "
        f"{manifest_path}"
    )


if __name__ == "__main__":
    main()
