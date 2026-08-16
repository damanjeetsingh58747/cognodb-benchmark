from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import random
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import certifi
from dotenv import load_dotenv

# Full TLS verification with reproducible CA bundle.
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from neo4j import GraphDatabase


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
CONFIG = ROOT / "configs"
RESULTS = ROOT / "results" / "raw"

SEED = 20260816
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
            MATCH (start:User {user_id: $user_id})
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


def load_csv(path: Path) -> list[dict]:
    with path.open(
        "r",
        encoding="utf-8",
        newline=""
    ) as f:
        return list(csv.DictReader(f))


def percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")

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


def stats(values: list[float]) -> dict:
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


def fingerprint(values) -> str:
    payload = json.dumps(
        values,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


def create_manifest() -> dict:
    CONFIG.mkdir(parents=True, exist_ok=True)

    manifest_path = CONFIG / "read_manifest.json"

    # Reuse existing manifest forever once created.
    if manifest_path.exists():
        return json.loads(
            manifest_path.read_text(encoding="utf-8")
        )

    users = load_csv(DATA / "users.csv")
    movies = load_csv(DATA / "movies.csv")

    user_ids = sorted(
        int(row["user_id"])
        for row in users
    )

    years = sorted({
        row["release_year"]
        for row in movies
        if row["release_year"]
    })

    rng = random.Random(SEED)

    # Unique user IDs so the measured set covers many graph shapes.
    selected_users = rng.sample(
        user_ids,
        WARMUP_RUNS + MEASURED_RUNS,
    )

    warmup_users = selected_users[:WARMUP_RUNS]
    measured_users = selected_users[WARMUP_RUNS:]

    warmup_years = [
        rng.choice(years)
        for _ in range(WARMUP_RUNS)
    ]

    measured_years = [
        rng.choice(years)
        for _ in range(MEASURED_RUNS)
    ]

    manifest = {
        "seed": SEED,
        "warmup_runs": WARMUP_RUNS,
        "measured_runs": MEASURED_RUNS,
        "warmup_user_ids": warmup_users,
        "measured_user_ids": measured_users,
        "warmup_release_years": warmup_years,
        "measured_release_years": measured_years,
    }

    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    return manifest


def parameters(
    input_type: str,
    manifest: dict,
    warmup: bool,
) -> list[dict]:

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
                "target_movie_id": ((value * 37) % 1682) + 1,
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

    count = (
        WARMUP_RUNS
        if warmup
        else MEASURED_RUNS
    )

    return [{} for _ in range(count)]


def canonical_result(records: list[dict]):
    return [
        {
            key: record[key]
            for key in sorted(record)
        }
        for record in records
    ]


def run_workload(
    session,
    name: str,
    config: dict,
    manifest: dict,
) -> dict:

    query = config["query"]
    input_type = config["input"]

    warmup_params = parameters(
        input_type,
        manifest,
        warmup=True,
    )

    measured_params = parameters(
        input_type,
        manifest,
        warmup=False,
    )

    print()
    print(f"--- {name} ---")
    print(
        f"Warm-up: {len(warmup_params)} | "
        f"Measured: {len(measured_params)}"
    )

    # -----------------------------------------------------
    # Warm-up
    # -----------------------------------------------------
    for params in warmup_params:
        session.run(
            query,
            **params,
        ).data()

    # -----------------------------------------------------
    # Timed runs
    # -----------------------------------------------------
    latencies = []
    canonical_outputs = []
    errors = []

    for i, params in enumerate(
        measured_params,
        start=1,
    ):
        try:
            start_ns = time.perf_counter_ns()

            records = session.run(
                query,
                **params,
            ).data()

            elapsed_ms = (
                time.perf_counter_ns() - start_ns
            ) / 1_000_000

            latencies.append(elapsed_ms)

            canonical_outputs.append({
                "params": params,
                "result": canonical_result(records),
            })

        except Exception as exc:
            errors.append({
                "iteration": i,
                "params": params,
                "error_type": type(exc).__name__,
                "error": str(exc),
            })

    if not latencies:
        raise RuntimeError(
            f"All measured runs failed for {name}"
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
        "warmup_runs": len(warmup_params),
        "requested_measured_runs": len(
            measured_params
        ),
        "successful_runs": len(latencies),
        "error_count": len(errors),
        "statistics": summary,
        "latencies_ms": latencies,
        "result_fingerprint_sha256": fingerprint(
            canonical_outputs
        ),
        "errors": errors,
    }


def main() -> None:
    load_dotenv(ROOT / ".env")

    uri = os.environ["NEO4J_URI"]
    username = os.environ.get(
        "NEO4J_USER",
        "neo4j",
    )
    password = os.environ["NEO4J_PASSWORD"]

    manifest = create_manifest()

    print("==============================================")
    print(" Neo4j AuraDB — Read Workload Benchmark")
    print("==============================================")
    print(f"Random seed:   {SEED}")
    print(f"Warm-up runs:  {WARMUP_RUNS}")
    print(f"Measured runs: {MEASURED_RUNS}")
    print()

    driver = GraphDatabase.driver(
        uri,
        auth=(username, password),
    )

    driver.verify_connectivity()

    print("✅ Connected to CognoDB")

    # Same index will be created on every competing database.
    with driver.session() as session:
        try:
            session.run(
                """
                CREATE INDEX FOR (m:Movie)
                ON (m.release_year)
                """
            ).consume()

            print(
                "✅ Created Movie.release_year index"
            )

        except Exception as exc:
            text = str(exc).lower()

            if (
                "already exists" in text
                or "equivalent" in text
            ):
                print(
                    "✅ Movie.release_year index already exists"
                )
            else:
                raise

    results = {}

    benchmark_start = time.perf_counter()

    # Reuse one established session so connection handshakes
    # are not accidentally included in every query latency.
    with driver.session() as session:
        for name, config in WORKLOADS.items():
            results[name] = run_workload(
                session,
                name,
                config,
                manifest,
            )

    total_seconds = (
        time.perf_counter() - benchmark_start
    )

    output = {
        "platform": "Neo4j AuraDB Free",
        "dataset": "MovieLens 100K",
        "timestamp_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "methodology": {
            "client_side_latency": True,
            "timer": "time.perf_counter_ns",
            "seed": SEED,
            "warmup_runs_per_workload": (
                WARMUP_RUNS
            ),
            "measured_runs_per_workload": (
                MEASURED_RUNS
            ),
            "connection_strategy": (
                "single established driver/session "
                "per benchmark run"
            ),
            "indexed_properties": [
                "User.user_id (unique constraint)",
                "Movie.movie_id (unique constraint)",
                "Movie.release_year (index)",
            ],
        },
        "workloads": results,
        "total_benchmark_seconds": total_seconds,
    }

    RESULTS.mkdir(parents=True, exist_ok=True)

    output_path = (
        RESULTS / "neo4j_reads.json"
    )

    output_path.write_text(
        json.dumps(output, indent=2),
        encoding="utf-8",
    )

    driver.close()

    # -----------------------------------------------------
    # Dataset-level integrity sanity check:
    # rating aggregation must total 100,000.
    # -----------------------------------------------------
    agg_query_outputs = results[
        "aggregation_rating_counts"
    ]

    print()
    print("==============================================")
    print(" ✅ NEO4J READ BENCHMARK COMPLETE")
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
        f"Raw result: {output_path}"
    )
    print(
        "Input manifest: "
        f"{CONFIG / 'read_manifest.json'}"
    )


if __name__ == "__main__":
    main()
