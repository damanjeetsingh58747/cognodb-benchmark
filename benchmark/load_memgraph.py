from __future__ import annotations

import csv
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import certifi
from dotenv import load_dotenv

# Keep full TLS verification enabled using a reproducible CA bundle.
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from neo4j import GraphDatabase


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
RESULTS = ROOT / "results" / "raw"

BATCH_SIZE = 1000


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def batches(rows: list[dict], size: int):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def main() -> None:
    load_dotenv(ROOT / ".env")

    uri = os.environ["MEMGRAPH_URI"]
    user = os.environ.get("MEMGRAPH_USER", "")
    password = os.environ["MEMGRAPH_PASSWORD"]

    print("==============================================")
    print(" Memgraph Cloud — MovieLens 100K Ingest Benchmark")
    print("==============================================")
    print(f"Batch size: {BATCH_SIZE}")
    print()

    users = read_csv(DATA / "users.csv")
    movies = read_csv(DATA / "movies.csv")
    ratings = read_csv(DATA / "ratings.csv")

    print("Dataset loaded locally:")
    print(f"  Users:         {len(users):,}")
    print(f"  Movies:        {len(movies):,}")
    print(f"  Relationships: {len(ratings):,}")
    print()

    driver = GraphDatabase.driver(
        uri,
        auth=(user, password),
    )

    driver.verify_connectivity()
    print("✅ Connected to CognoDB")

    benchmark_start = time.perf_counter()

    # ---------------------------------------------------------
    # 1. RESET DATABASE
    # ---------------------------------------------------------
    print()
    print("[1/6] Resetting database...")

    reset_start = time.perf_counter()

    with driver.session() as session:
        session.run(
            "MATCH (n) DETACH DELETE n"
        ).consume()

    reset_seconds = time.perf_counter() - reset_start

    print(f"      Reset: {reset_seconds:.3f}s")

    # ---------------------------------------------------------
    # 2. CREATE SCHEMA
    # ---------------------------------------------------------
    print("[2/6] Creating constraints/indexes...")

    schema_start = time.perf_counter()

    with driver.session() as session:
        # Ignore errors only if the constraint already exists.
        schema_queries = [
            "CREATE CONSTRAINT ON (u:User) ASSERT u.user_id IS UNIQUE",
            "CREATE CONSTRAINT ON (m:Movie) ASSERT m.movie_id IS UNIQUE",
            "CREATE INDEX ON :User(user_id)",
            "CREATE INDEX ON :Movie(movie_id)",
        ]

        for query in schema_queries:
            try:
                session.run(query).consume()
            except Exception as exc:
                message = str(exc).lower()

                if (
                    "already exists" not in message
                    and "already indexed" not in message
                    and "already constrained" not in message
                ):
                    raise

    schema_seconds = time.perf_counter() - schema_start

    print(f"      Schema setup: {schema_seconds:.3f}s")

    # ---------------------------------------------------------
    # 3. LOAD USER NODES
    # ---------------------------------------------------------
    print("[3/6] Loading User nodes...")

    user_query = """
    UNWIND $rows AS row
    CREATE (:User {
        user_id: toInteger(row.user_id),
        age: toInteger(row.age),
        gender: row.gender,
        occupation: row.occupation,
        zip_code: row.zip_code
    })
    """

    user_start = time.perf_counter()

    with driver.session() as session:
        for batch in batches(users, BATCH_SIZE):
            session.run(
                user_query,
                rows=batch,
            ).consume()

    user_seconds = time.perf_counter() - user_start

    print(
        f"      {len(users):,} users in "
        f"{user_seconds:.3f}s "
        f"({len(users) / user_seconds:,.1f} nodes/s)"
    )

    # ---------------------------------------------------------
    # 4. LOAD MOVIE NODES
    # ---------------------------------------------------------
    print("[4/6] Loading Movie nodes...")

    movie_query = """
    UNWIND $rows AS row
    CREATE (:Movie {
        movie_id: toInteger(row.movie_id),
        title: row.title,
        release_date: row.release_date,
        release_year: row.release_year,
        genres: row.genres
    })
    """

    movie_start = time.perf_counter()

    with driver.session() as session:
        for batch in batches(movies, BATCH_SIZE):
            session.run(
                movie_query,
                rows=batch,
            ).consume()

    movie_seconds = time.perf_counter() - movie_start

    print(
        f"      {len(movies):,} movies in "
        f"{movie_seconds:.3f}s "
        f"({len(movies) / movie_seconds:,.1f} nodes/s)"
    )

    node_seconds = user_seconds + movie_seconds
    total_nodes = len(users) + len(movies)
    node_throughput = total_nodes / node_seconds

    # ---------------------------------------------------------
    # 5. LOAD RATED RELATIONSHIPS
    # ---------------------------------------------------------
    print("[5/6] Loading RATED relationships...")

    rating_query = """
    UNWIND $rows AS row
    MATCH (u:User {user_id: toInteger(row.user_id)})
    MATCH (m:Movie {movie_id: toInteger(row.movie_id)})
    CREATE (u)-[:RATED {
        rating: toInteger(row.rating),
        timestamp: toInteger(row.timestamp)
    }]->(m)
    """

    relationship_start = time.perf_counter()

    completed = 0

    with driver.session() as session:
        for batch in batches(ratings, BATCH_SIZE):
            session.run(
                rating_query,
                rows=batch,
            ).consume()

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

    with driver.session() as session:
        counts = session.run(
            """
            MATCH (n)
            WITH count(n) AS nodes
            MATCH ()-[r:RATED]->()
            RETURN nodes, count(r) AS relationships
            """
        ).single()

        user_count = session.run(
            "MATCH (u:User) RETURN count(u) AS count"
        ).single()["count"]

        movie_count = session.run(
            "MATCH (m:Movie) RETURN count(m) AS count"
        ).single()["count"]

    verify_seconds = time.perf_counter() - verify_start

    actual_nodes = counts["nodes"]
    actual_relationships = counts["relationships"]

    expected_nodes = 2625
    expected_relationships = 100000

    if user_count != 943:
        raise RuntimeError(
            f"Expected 943 User nodes, got {user_count}"
        )

    if movie_count != 1682:
        raise RuntimeError(
            f"Expected 1682 Movie nodes, got {movie_count}"
        )

    if actual_nodes != expected_nodes:
        raise RuntimeError(
            f"Expected {expected_nodes} nodes, "
            f"got {actual_nodes}"
        )

    if actual_relationships != expected_relationships:
        raise RuntimeError(
            f"Expected {expected_relationships} relationships, "
            f"got {actual_relationships}"
        )

    benchmark_seconds = (
        time.perf_counter() - benchmark_start
    )

    result = {
        "platform": "Memgraph Cloud Free Trial",
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
            "batch_size": BATCH_SIZE,
            "load_method": (
                "Neo4j Python driver + parameterized "
                "UNWIND batches"
            ),
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
            "relationships_per_second": (
                relationship_throughput
            ),
        },
        "verification": {
            "users": user_count,
            "movies": movie_count,
            "nodes": actual_nodes,
            "relationships": actual_relationships,
            "passed": True,
        },
    }

    RESULTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    output = RESULTS / "memgraph_ingest.json"

    output.write_text(
        json.dumps(
            result,
            indent=2,
        ),
        encoding="utf-8",
    )

    driver.close()

    print()
    print("==============================================")
    print(" ✅ MEMGRAPH INGEST BENCHMARK PASSED")
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
