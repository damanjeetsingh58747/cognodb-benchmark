from __future__ import annotations

import json
import os
import random
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv
from falkordb import FalkorDB
from arango import ArangoClient


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "raw"
CONFIG = ROOT / "configs"

CONCURRENCY_LEVELS = [1, 10, 40]
WARMUP_SECONDS = 5
MEASURE_SECONDS = 20
WRITE_EVERY = 10


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


def finalize_result(
    concurrency,
    elapsed,
    completed,
    reads,
    writes,
    errors,
    all_latencies,
    read_latencies,
    write_latencies,
):
    return {
        "concurrency": concurrency,
        "duration_seconds": elapsed,
        "completed_queries": completed,
        "read_queries": reads,
        "write_queries": writes,
        "errors": errors,
        "qps": completed / elapsed,
        "read_qps": reads / elapsed,
        "write_qps": writes / elapsed,
        "all_latency": latency_stats(
            all_latencies
        ),
        "read_latency": latency_stats(
            read_latencies
        ),
        "write_latency": latency_stats(
            write_latencies
        ),
    }


# ============================================================
# FalkorDB
# ============================================================

FALKOR_READ = """
MATCH (u:User {user_id: $user_id})
RETURN u.age AS value
"""

FALKOR_WRITE = """
CREATE (:BenchmarkWrite {
    id: $id,
    value: $value,
    created_at: $created_at
})
"""


def falkor_connection():
    db = FalkorDB(
        host=os.environ["FALKORDB_HOST"],
        port=int(os.environ["FALKORDB_PORT"]),
        username=os.environ["FALKORDB_USER"],
        password=os.environ["FALKORDB_PASSWORD"],
    )

    return db.select_graph(
        "wexa_benchmark"
    )


def falkor_cleanup():
    graph = falkor_connection()

    graph.query(
        """
        MATCH (n:BenchmarkWrite)
        DELETE n
        """
    )


def run_falkor_phase(
    user_ids,
    concurrency,
    seconds,
    measured,
):
    lock = threading.Lock()

    totals = {
        "completed": 0,
        "reads": 0,
        "writes": 0,
        "errors": 0,
        "all_latencies": [],
        "read_latencies": [],
        "write_latencies": [],
    }

    start_holder = {}

    barrier = threading.Barrier(
        concurrency + 1,
        action=lambda: start_holder.update(
            start=time.perf_counter()
        ),
    )

    def worker(worker_id):
        graph = falkor_connection()

        rng = random.Random(
            20260816
            + worker_id
            + concurrency * 1000
        )

        local_completed = 0
        local_reads = 0
        local_writes = 0
        local_errors = 0

        all_lat = []
        read_lat = []
        write_lat = []

        operation = 0

        barrier.wait()

        stop_time = (
            start_holder["start"]
            + seconds
        )

        while time.perf_counter() < stop_time:
            operation += 1

            is_write = (
                operation % WRITE_EVERY == 0
            )

            try:
                start_ns = (
                    time.perf_counter_ns()
                )

                if is_write:
                    graph.query(
                        FALKOR_WRITE,
                        {
                            "id": (
                                f"{concurrency}-"
                                f"{worker_id}-"
                                f"{operation}-"
                                f"{time.time_ns()}"
                            ),
                            "value": operation,
                            "created_at":
                                time.time_ns(),
                        },
                    )

                else:
                    graph.query(
                        FALKOR_READ,
                        {
                            "user_id":
                                rng.choice(
                                    user_ids
                                )
                        },
                    )

                elapsed_ms = (
                    time.perf_counter_ns()
                    - start_ns
                ) / 1_000_000

                local_completed += 1
                all_lat.append(elapsed_ms)

                if is_write:
                    local_writes += 1
                    write_lat.append(
                        elapsed_ms
                    )
                else:
                    local_reads += 1
                    read_lat.append(
                        elapsed_ms
                    )

            except Exception:
                local_errors += 1

        if measured:
            with lock:
                totals["completed"] += (
                    local_completed
                )
                totals["reads"] += local_reads
                totals["writes"] += local_writes
                totals["errors"] += local_errors

                totals[
                    "all_latencies"
                ].extend(all_lat)

                totals[
                    "read_latencies"
                ].extend(read_lat)

                totals[
                    "write_latencies"
                ].extend(write_lat)

    with ThreadPoolExecutor(
        max_workers=concurrency
    ) as executor:

        futures = [
            executor.submit(
                worker,
                worker_id,
            )
            for worker_id
            in range(concurrency)
        ]

        barrier.wait()

        for future in futures:
            future.result()

    elapsed = (
        time.perf_counter()
        - start_holder["start"]
    )

    if not measured:
        return None

    return finalize_result(
        concurrency,
        elapsed,
        totals["completed"],
        totals["reads"],
        totals["writes"],
        totals["errors"],
        totals["all_latencies"],
        totals["read_latencies"],
        totals["write_latencies"],
    )


def benchmark_falkor(user_ids):
    print()
    print("==============================================")
    print(" FalkorDB Cloud — Mixed Workload")
    print("==============================================")
    print("Mix: 90% reads / 10% writes")

    results = []

    for concurrency in CONCURRENCY_LEVELS:

        falkor_cleanup()

        print()
        print(
            f"Concurrency {concurrency}: "
            f"{WARMUP_SECONDS}s warm-up..."
        )

        run_falkor_phase(
            user_ids,
            concurrency,
            WARMUP_SECONDS,
            False,
        )

        falkor_cleanup()

        print(
            f"Concurrency {concurrency}: "
            f"{MEASURE_SECONDS}s measured..."
        )

        result = run_falkor_phase(
            user_ids,
            concurrency,
            MEASURE_SECONDS,
            True,
        )

        results.append(result)

        print(
            f"  QPS={result['qps']:.2f} | "
            f"p50="
            f"{result['all_latency']['p50_ms']:.2f} ms | "
            f"p95="
            f"{result['all_latency']['p95_ms']:.2f} ms | "
            f"errors={result['errors']}"
        )

    falkor_cleanup()

    output = {
        "platform":
            "FalkorDB Cloud Free",
        "mix": {
            "reads_percent": 90,
            "writes_percent": 10,
        },
        "warmup_seconds":
            WARMUP_SECONDS,
        "measurement_seconds":
            MEASURE_SECONDS,
        "concurrency_levels":
            CONCURRENCY_LEVELS,
        "results":
            results,
    }

    path = (
        RESULTS /
        "falkordb_mixed.json"
    )

    path.write_text(
        json.dumps(
            output,
            indent=2,
        ),
        encoding="utf-8",
    )

    return results


# ============================================================
# ArangoDB
# ============================================================

ARANGO_READ = """
FOR u IN users
    FILTER u.user_id == @user_id
    LIMIT 1
    RETURN u.age
"""

ARANGO_WRITE = """
INSERT {
    value: @value,
    worker: @worker,
    created_at: @created_at
}
INTO benchmark_writes
"""


def arango_connection():
    client = ArangoClient(
        hosts=os.environ["ARANGO_URL"]
    )

    db = client.db(
        os.environ.get(
            "ARANGO_DATABASE",
            "wexa_benchmark",
        ),
        username=os.environ[
            "ARANGO_USER"
        ],
        password=os.environ[
            "ARANGO_PASSWORD"
        ],
    )

    return client, db


def arango_prepare():
    _, db = arango_connection()

    if not db.has_collection(
        "benchmark_writes"
    ):
        db.create_collection(
            "benchmark_writes"
        )

    db.collection(
        "benchmark_writes"
    ).truncate()


def run_arango_phase(
    user_ids,
    concurrency,
    seconds,
    measured,
):
    lock = threading.Lock()

    totals = {
        "completed": 0,
        "reads": 0,
        "writes": 0,
        "errors": 0,
        "all_latencies": [],
        "read_latencies": [],
        "write_latencies": [],
    }

    start_holder = {}

    barrier = threading.Barrier(
        concurrency + 1,
        action=lambda: start_holder.update(
            start=time.perf_counter()
        ),
    )

    def worker(worker_id):
        # Separate client/session per worker.
        # This avoids sharing python-arango's
        # underlying HTTP session across threads.
        _, db = arango_connection()

        rng = random.Random(
            20260816
            + worker_id
            + concurrency * 1000
        )

        local_completed = 0
        local_reads = 0
        local_writes = 0
        local_errors = 0

        all_lat = []
        read_lat = []
        write_lat = []

        operation = 0

        barrier.wait()

        stop_time = (
            start_holder["start"]
            + seconds
        )

        while time.perf_counter() < stop_time:
            operation += 1

            is_write = (
                operation % WRITE_EVERY == 0
            )

            try:
                start_ns = (
                    time.perf_counter_ns()
                )

                if is_write:
                    list(
                        db.aql.execute(
                            ARANGO_WRITE,
                            bind_vars={
                                "value":
                                    operation,
                                "worker":
                                    worker_id,
                                "created_at":
                                    time.time_ns(),
                            },
                        )
                    )

                else:
                    list(
                        db.aql.execute(
                            ARANGO_READ,
                            bind_vars={
                                "user_id":
                                    rng.choice(
                                        user_ids
                                    )
                            },
                        )
                    )

                elapsed_ms = (
                    time.perf_counter_ns()
                    - start_ns
                ) / 1_000_000

                local_completed += 1
                all_lat.append(elapsed_ms)

                if is_write:
                    local_writes += 1
                    write_lat.append(
                        elapsed_ms
                    )
                else:
                    local_reads += 1
                    read_lat.append(
                        elapsed_ms
                    )

            except Exception:
                local_errors += 1

        if measured:
            with lock:
                totals["completed"] += (
                    local_completed
                )
                totals["reads"] += local_reads
                totals["writes"] += local_writes
                totals["errors"] += local_errors

                totals[
                    "all_latencies"
                ].extend(all_lat)

                totals[
                    "read_latencies"
                ].extend(read_lat)

                totals[
                    "write_latencies"
                ].extend(write_lat)

    with ThreadPoolExecutor(
        max_workers=concurrency
    ) as executor:

        futures = [
            executor.submit(
                worker,
                worker_id,
            )
            for worker_id
            in range(concurrency)
        ]

        barrier.wait()

        for future in futures:
            future.result()

    elapsed = (
        time.perf_counter()
        - start_holder["start"]
    )

    if not measured:
        return None

    return finalize_result(
        concurrency,
        elapsed,
        totals["completed"],
        totals["reads"],
        totals["writes"],
        totals["errors"],
        totals["all_latencies"],
        totals["read_latencies"],
        totals["write_latencies"],
    )


def benchmark_arango(user_ids):
    print()
    print("==============================================")
    print(" ArangoDB Cloud — Mixed Workload")
    print("==============================================")
    print("Mix: 90% reads / 10% writes")

    results = []

    for concurrency in CONCURRENCY_LEVELS:

        arango_prepare()

        print()
        print(
            f"Concurrency {concurrency}: "
            f"{WARMUP_SECONDS}s warm-up..."
        )

        run_arango_phase(
            user_ids,
            concurrency,
            WARMUP_SECONDS,
            False,
        )

        arango_prepare()

        print(
            f"Concurrency {concurrency}: "
            f"{MEASURE_SECONDS}s measured..."
        )

        result = run_arango_phase(
            user_ids,
            concurrency,
            MEASURE_SECONDS,
            True,
        )

        results.append(result)

        print(
            f"  QPS={result['qps']:.2f} | "
            f"p50="
            f"{result['all_latency']['p50_ms']:.2f} ms | "
            f"p95="
            f"{result['all_latency']['p95_ms']:.2f} ms | "
            f"errors={result['errors']}"
        )

    arango_prepare()

    output = {
        "platform":
            "ArangoDB Managed Platform Trial",
        "mix": {
            "reads_percent": 90,
            "writes_percent": 10,
        },
        "warmup_seconds":
            WARMUP_SECONDS,
        "measurement_seconds":
            MEASURE_SECONDS,
        "concurrency_levels":
            CONCURRENCY_LEVELS,
        "results":
            results,
    }

    path = (
        RESULTS /
        "arangodb_mixed.json"
    )

    path.write_text(
        json.dumps(
            output,
            indent=2,
        ),
        encoding="utf-8",
    )

    return results


def main():
    load_dotenv(ROOT / ".env")

    manifest = json.loads(
        (
            CONFIG /
            "read_manifest.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    user_ids = (
        manifest[
            "measured_user_ids"
        ]
    )

    RESULTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    falkor_results = (
        benchmark_falkor(
            user_ids
        )
    )

    arango_results = (
        benchmark_arango(
            user_ids
        )
    )

    print()
    print("==============================================")
    print(" ✅ NATIVE MIXED WORKLOADS COMPLETE")
    print("==============================================")

    print()
    print("FalkorDB Cloud")

    for result in falkor_results:
        print(
            f"  C={result['concurrency']:2d} | "
            f"QPS={result['qps']:8.2f} | "
            f"p95="
            f"{result['all_latency']['p95_ms']:8.2f} ms | "
            f"errors={result['errors']}"
        )

    print()
    print("ArangoDB Cloud")

    for result in arango_results:
        print(
            f"  C={result['concurrency']:2d} | "
            f"QPS={result['qps']:8.2f} | "
            f"p95="
            f"{result['all_latency']['p95_ms']:8.2f} ms | "
            f"errors={result['errors']}"
        )


if __name__ == "__main__":
    main()
