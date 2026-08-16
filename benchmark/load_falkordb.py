from __future__ import annotations

import csv
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from falkordb import FalkorDB


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
RESULTS = ROOT / "results" / "raw"

GRAPH_NAME = "wexa_benchmark"
BATCH_SIZE = 1000


def read_users():
    rows = []
    with (DATA / "users.csv").open(
        "r", encoding="utf-8", newline=""
    ) as f:
        for row in csv.DictReader(f):
            rows.append({
                "user_id": int(row["user_id"]),
                "age": int(row["age"]),
                "gender": row["gender"],
                "occupation": row["occupation"],
                "zip_code": row["zip_code"],
            })
    return rows


def read_movies():
    rows = []
    with (DATA / "movies.csv").open(
        "r", encoding="utf-8", newline=""
    ) as f:
        for row in csv.DictReader(f):
            rows.append({
                "movie_id": int(row["movie_id"]),
                "title": row["title"],
                "release_date": row["release_date"],
                "release_year": row["release_year"],
                "genres": row["genres"],
            })
    return rows


def read_ratings():
    rows = []
    with (DATA / "ratings.csv").open(
        "r", encoding="utf-8", newline=""
    ) as f:
        for row in csv.DictReader(f):
            rows.append({
                "user_id": int(row["user_id"]),
                "movie_id": int(row["movie_id"]),
                "rating": int(row["rating"]),
                "timestamp": int(row["timestamp"]),
            })
    return rows


def batches(rows, size):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def main():
    load_dotenv(ROOT / ".env")

    db = FalkorDB(
        host=os.environ["FALKORDB_HOST"],
        port=int(os.environ["FALKORDB_PORT"]),
        username=os.environ["FALKORDB_USER"],
        password=os.environ["FALKORDB_PASSWORD"],
    )

    users = read_users()
    movies = read_movies()
    ratings = read_ratings()

    print("==============================================")
    print(" FalkorDB — MovieLens 100K Ingest Benchmark")
    print("==============================================")
    print(f"Graph: {GRAPH_NAME}")
    print(f"Batch size: {BATCH_SIZE}")
    print()
    print("Dataset loaded locally:")
    print(f"  Users:         {len(users):,}")
    print(f"  Movies:        {len(movies):,}")
    print(f"  Relationships: {len(ratings):,}")
    print()

    graph = db.select_graph(GRAPH_NAME)

    # Connectivity sanity check.
    graph.query("RETURN 1 AS connection_test")
    print("✅ Connected to FalkorDB")

    benchmark_start = time.perf_counter()

    # ---------------------------------------------------------
    # 1. RESET GRAPH
    # ---------------------------------------------------------
    print()
    print("[1/6] Resetting graph...")

    reset_start = time.perf_counter()

    try:
        graph.delete()
    except Exception:
        # Graph may not exist yet.
        pass

    graph = db.select_graph(GRAPH_NAME)

    reset_seconds = time.perf_counter() - reset_start
    print(f"      Reset: {reset_seconds:.3f}s")

    # ---------------------------------------------------------
    # 2. CREATE INDEXES
    # ---------------------------------------------------------
    print("[2/6] Creating indexes...")

    schema_start = time.perf_counter()

    graph.query(
        "CREATE INDEX FOR (u:User) ON (u.user_id)"
    )

    graph.query(
        "CREATE INDEX FOR (m:Movie) ON (m.movie_id)"
    )

    graph.query(
        "CREATE INDEX FOR (m:Movie) ON (m.release_year)"
    )

    schema_seconds = time.perf_counter() - schema_start
    print(f"      Schema setup: {schema_seconds:.3f}s")

    # ---------------------------------------------------------
    # 3. USERS
    # ---------------------------------------------------------
    print("[3/6] Loading User nodes...")

    user_query = """
    UNWIND $rows AS row
    CREATE (:User {
        user_id: row.user_id,
        age: row.age,
        gender: row.gender,
        occupation: row.occupation,
        zip_code: row.zip_code
    })
    """

    user_start = time.perf_counter()

    for batch in batches(users, BATCH_SIZE):
        graph.query(user_query, {"rows": batch})

    user_seconds = time.perf_counter() - user_start

    print(
        f"      {len(users):,} users in "
        f"{user_seconds:.3f}s "
        f"({len(users) / user_seconds:,.1f} nodes/s)"
    )

    # ---------------------------------------------------------
    # 4. MOVIES
    # ---------------------------------------------------------
    print("[4/6] Loading Movie nodes...")

    movie_query = """
    UNWIND $rows AS row
    CREATE (:Movie {
        movie_id: row.movie_id,
        title: row.title,
        release_date: row.release_date,
        release_year: row.release_year,
        genres: row.genres
    })
    """

    movie_start = time.perf_counter()

    for batch in batches(movies, BATCH_SIZE):
        graph.query(movie_query, {"rows": batch})

    movie_seconds = time.perf_counter() - movie_start

    print(
        f"      {len(movies):,} movies in "
        f"{movie_seconds:.3f}s "
        f"({len(movies) / movie_seconds:,.1f} nodes/s)"
    )

    total_nodes = len(users) + len(movies)
    node_seconds = user_seconds + movie_seconds
    node_throughput = total_nodes / node_seconds

    # ---------------------------------------------------------
    # 5. RELATIONSHIPS
    # ---------------------------------------------------------
    print("[5/6] Loading RATED relationships...")

    rating_query = """
    UNWIND $rows AS row
    MATCH (u:User {user_id: row.user_id})
    MATCH (m:Movie {movie_id: row.movie_id})
    CREATE (u)-[:RATED {
        rating: row.rating,
        timestamp: row.timestamp
    }]->(m)
    """

    relationship_start = time.perf_counter()
    completed = 0

    for batch in batches(ratings, BATCH_SIZE):
        graph.query(rating_query, {"rows": batch})

        completed += len(batch)

        if (
            completed % 10000 == 0
            or completed == len(ratings)
        ):
            print(
                f"      Loaded "
                f"{completed:,}/{len(ratings):,}"
            )

    relationship_seconds = (
        time.perf_counter() - relationship_start
    )

    relationship_throughput = (
        len(ratings) / relationship_seconds
    )

    # ---------------------------------------------------------
    # 6. VERIFY
    # ---------------------------------------------------------
    print("[6/6] Verifying graph integrity...")

    verify_start = time.perf_counter()

    node_result = graph.query(
        "MATCH (n) RETURN count(n)"
    )

    relationship_result = graph.query(
        "MATCH ()-[r:RATED]->() RETURN count(r)"
    )

    user_result = graph.query(
        "MATCH (u:User) RETURN count(u)"
    )

    movie_result = graph.query(
        "MATCH (m:Movie) RETURN count(m)"
    )

    actual_nodes = node_result.result_set[0][0]
    actual_relationships = relationship_result.result_set[0][0]
    user_count = user_result.result_set[0][0]
    movie_count = movie_result.result_set[0][0]

    verify_seconds = time.perf_counter() - verify_start

    if user_count != 943:
        raise RuntimeError(
            f"Expected 943 users, got {user_count}"
        )

    if movie_count != 1682:
        raise RuntimeError(
            f"Expected 1682 movies, got {movie_count}"
        )

    if actual_nodes != 2625:
        raise RuntimeError(
            f"Expected 2625 nodes, got {actual_nodes}"
        )

    if actual_relationships != 100000:
        raise RuntimeError(
            "Expected 100000 relationships, "
            f"got {actual_relationships}"
        )

    benchmark_seconds = (
        time.perf_counter() - benchmark_start
    )

    result = {
        "platform": "FalkorDB Cloud Free",
        "dataset": "MovieLens 100K",
        "timestamp_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "client": {
            "python": sys.version.split()[0],
            "os": platform.platform(),
            "machine": platform.machine(),
        },
        "configuration": {
            "graph_name": GRAPH_NAME,
            "batch_size": BATCH_SIZE,
            "load_method": (
                "FalkorDB Python client + "
                "parameterized UNWIND batches"
            ),
            "cloud": "AWS",
            "region": "us-east-1",
        },
        "dataset_counts": {
            "users": len(users),
            "movies": len(movies),
            "nodes": total_nodes,
            "relationships": len(ratings),
        },
        "timings_seconds": {
            "reset": reset_seconds,
            "schema": schema_seconds,
            "user_nodes": user_seconds,
            "movie_nodes": movie_seconds,
            "all_nodes": node_seconds,
            "relationships": relationship_seconds,
            "verification": verify_seconds,
            "end_to_end": benchmark_seconds,
        },
        "throughput": {
            "nodes_per_second": node_throughput,
            "relationships_per_second":
                relationship_throughput,
        },
        "verification": {
            "users": user_count,
            "movies": movie_count,
            "nodes": actual_nodes,
            "relationships": actual_relationships,
            "passed": True,
        },
    }

    RESULTS.mkdir(parents=True, exist_ok=True)

    output = RESULTS / "falkordb_ingest.json"

    output.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    print()
    print("==============================================")
    print(" ✅ FALKORDB INGEST BENCHMARK PASSED")
    print("==============================================")
    print(f"Nodes:             {actual_nodes:,}")
    print(
        f"Relationships:     "
        f"{actual_relationships:,}"
    )
    print()
    print(
        f"Node throughput:   "
        f"{node_throughput:,.1f} nodes/s"
    )
    print(
        f"Rel throughput:    "
        f"{relationship_throughput:,.1f} rels/s"
    )
    print(
        f"Relationship time: "
        f"{relationship_seconds:.3f}s"
    )
    print(
        f"End-to-end time:   "
        f"{benchmark_seconds:.3f}s"
    )
    print()
    print(f"Raw result: {output}")


if __name__ == "__main__":
    main()
