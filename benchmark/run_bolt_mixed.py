from __future__ import annotations

import json
import os
import random
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import certifi
from dotenv import load_dotenv

os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from neo4j import GraphDatabase


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "raw"
CONFIG = ROOT / "configs"

CONCURRENCY_LEVELS = [1, 10, 40]
WARMUP_SECONDS = 5
MEASURE_SECONDS = 20
WRITE_EVERY = 10  # exactly ~10% writes


PLATFORMS = {
    "cognodb": {
        "name": "CognoDB Cloud",
        "uri": "COGNODB_URI",
        "user": "COGNODB_USER",
        "password": "COGNODB_PASSWORD",
        "default_user": "cognodb",
    },
    "neo4j": {
        "name": "Neo4j AuraDB Free",
        "uri": "NEO4J_URI",
        "user": "NEO4J_USER",
        "password": "NEO4J_PASSWORD",
        "default_user": "neo4j",
    },
    "memgraph": {
        "name": "Memgraph Cloud Free Trial",
        "uri": "MEMGRAPH_URI",
        "user": "MEMGRAPH_USER",
        "password": "MEMGRAPH_PASSWORD",
        "default_user": "",
    },
}


READ_QUERY = """
MATCH (u:User {user_id: $user_id})
RETURN u.age AS value
"""

WRITE_QUERY = """
CREATE (:BenchmarkWrite {
    id: $id,
    value: $value,
    created_at: $created_at
})
"""


def percentile(values, p):
    if not values:
        return None

    values = sorted(values)

    if len(values) == 1:
        return values[0]

    pos = (len(values) - 1) * p
    low = int(pos)
    high = min(low + 1, len(values) - 1)
    fraction = pos - low

    return (
        values[low] * (1 - fraction)
        + values[high] * fraction
    )


def latency_stats(values):
    if not values:
        return {
            "p50_ms": None,
            "p95_ms": None,
            "mean_ms": None,
        }

    return {
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "mean_ms": statistics.mean(values),
    }


def cleanup(driver):
    with driver.session() as session:
        session.run(
            "MATCH (n:BenchmarkWrite) DETACH DELETE n"
        ).consume()


def run_phase(
    driver,
    user_ids,
    concurrency,
    seconds,
    measured,
):
    stop_time = time.perf_counter() + seconds

    lock = threading.Lock()

    totals = {
        "completed": 0,
        "reads": 0,
        "writes": 0,
        "errors": 0,
        "latencies_ms": [],
        "read_latencies_ms": [],
        "write_latencies_ms": [],
    }

    def worker(worker_id):
        rng = random.Random(
            20260816 + worker_id + concurrency * 1000
        )

        local_completed = 0
        local_reads = 0
        local_writes = 0
        local_errors = 0

        local_all_lat = []
        local_read_lat = []
        local_write_lat = []

        operation = 0

        with driver.session() as session:
            while time.perf_counter() < stop_time:
                operation += 1

                # Every 10th operation is a write.
                is_write = operation % WRITE_EVERY == 0

                try:
                    start_ns = time.perf_counter_ns()

                    if is_write:
                        session.run(
                            WRITE_QUERY,
                            id=(
                                f"{concurrency}-"
                                f"{worker_id}-"
                                f"{operation}-"
                                f"{time.time_ns()}"
                            ),
                            value=operation,
                            created_at=time.time_ns(),
                        ).consume()

                    else:
                        user_id = rng.choice(user_ids)

                        session.run(
                            READ_QUERY,
                            user_id=user_id,
                        ).consume()

                    elapsed_ms = (
                        time.perf_counter_ns() - start_ns
                    ) / 1_000_000

                    local_completed += 1
                    local_all_lat.append(elapsed_ms)

                    if is_write:
                        local_writes += 1
                        local_write_lat.append(elapsed_ms)
                    else:
                        local_reads += 1
                        local_read_lat.append(elapsed_ms)

                except Exception:
                    local_errors += 1

        if measured:
            with lock:
                totals["completed"] += local_completed
                totals["reads"] += local_reads
                totals["writes"] += local_writes
                totals["errors"] += local_errors

                totals["latencies_ms"].extend(
                    local_all_lat
                )

                totals["read_latencies_ms"].extend(
                    local_read_lat
                )

                totals["write_latencies_ms"].extend(
                    local_write_lat
                )

    start = time.perf_counter()

    with ThreadPoolExecutor(
        max_workers=concurrency
    ) as executor:

        futures = [
            executor.submit(worker, worker_id)
            for worker_id in range(concurrency)
        ]

        for future in futures:
            future.result()

    elapsed = time.perf_counter() - start

    if not measured:
        return None

    return {
        "concurrency": concurrency,
        "duration_seconds": elapsed,
        "completed_queries": totals["completed"],
        "read_queries": totals["reads"],
        "write_queries": totals["writes"],
        "errors": totals["errors"],
        "qps": totals["completed"] / elapsed,
        "read_qps": totals["reads"] / elapsed,
        "write_qps": totals["writes"] / elapsed,
        "all_latency": latency_stats(
            totals["latencies_ms"]
        ),
        "read_latency": latency_stats(
            totals["read_latencies_ms"]
        ),
        "write_latency": latency_stats(
            totals["write_latencies_ms"]
        ),
    }


def benchmark_platform(
    key,
    config,
    user_ids,
):
    uri = os.environ[config["uri"]]
    user = os.environ.get(
        config["user"],
        config["default_user"],
    )
    password = os.environ[config["password"]]

    driver = GraphDatabase.driver(
        uri,
        auth=(user, password),
        max_connection_pool_size=60,
    )

    driver.verify_connectivity()

    print()
    print("==============================================")
    print(f" {config['name']} — Mixed Workload")
    print("==============================================")
    print("Mix: 90% reads / 10% writes")

    results = []

    for concurrency in CONCURRENCY_LEVELS:

        cleanup(driver)

        print()
        print(
            f"Concurrency {concurrency}: "
            f"{WARMUP_SECONDS}s warm-up..."
        )

        run_phase(
            driver,
            user_ids,
            concurrency,
            WARMUP_SECONDS,
            measured=False,
        )

        cleanup(driver)

        print(
            f"Concurrency {concurrency}: "
            f"{MEASURE_SECONDS}s measured..."
        )

        result = run_phase(
            driver,
            user_ids,
            concurrency,
            MEASURE_SECONDS,
            measured=True,
        )

        results.append(result)

        print(
            f"  QPS={result['qps']:.2f} | "
            f"p50={result['all_latency']['p50_ms']:.2f} ms | "
            f"p95={result['all_latency']['p95_ms']:.2f} ms | "
            f"errors={result['errors']}"
        )

    cleanup(driver)
    driver.close()

    output = {
        "platform": config["name"],
        "mix": {
            "reads_percent": 90,
            "writes_percent": 10,
        },
        "warmup_seconds": WARMUP_SECONDS,
        "measurement_seconds": MEASURE_SECONDS,
        "concurrency_levels": CONCURRENCY_LEVELS,
        "results": results,
    }

    path = RESULTS / f"{key}_mixed.json"

    path.write_text(
        json.dumps(output, indent=2),
        encoding="utf-8",
    )

    return results


def main():
    load_dotenv(ROOT / ".env")

    manifest = json.loads(
        (
            CONFIG / "read_manifest.json"
        ).read_text(encoding="utf-8")
    )

    user_ids = manifest["measured_user_ids"]

    RESULTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    all_results = {}

    for key, config in PLATFORMS.items():
        all_results[key] = benchmark_platform(
            key,
            config,
            user_ids,
        )

    print()
    print("==============================================")
    print(" ✅ BOLT MIXED WORKLOADS COMPLETE")
    print("==============================================")

    for key, results in all_results.items():
        print()
        print(PLATFORMS[key]["name"])

        for result in results:
            print(
                f"  C={result['concurrency']:2d} | "
                f"QPS={result['qps']:8.2f} | "
                f"p95="
                f"{result['all_latency']['p95_ms']:8.2f} ms | "
                f"errors={result['errors']}"
            )


if __name__ == "__main__":
    main()
