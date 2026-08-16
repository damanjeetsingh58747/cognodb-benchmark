from __future__ import annotations

import csv
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from arango import ArangoClient
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
RESULTS = ROOT / "results" / "raw"

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

    client = ArangoClient(
        hosts=os.environ["ARANGO_URL"]
    )

    db = client.db(
        os.environ.get(
            "ARANGO_DATABASE",
            "wexa_benchmark"
        ),
        username=os.environ["ARANGO_USER"],
        password=os.environ["ARANGO_PASSWORD"],
    )

    print("==============================================")
    print(" ArangoDB — MovieLens 100K Ingest Benchmark")
    print("==============================================")
    print(f"Batch size: {BATCH_SIZE}")
    print()

    users = read_users()
    movies = read_movies()
    ratings = read_ratings()

    print("Dataset loaded locally:")
    print(f"  Users:         {len(users):,}")
    print(f"  Movies:        {len(movies):,}")
    print(f"  Relationships: {len(ratings):,}")
    print()

    # Connectivity test.
    list(db.aql.execute("RETURN 1"))
    print("✅ Connected to ArangoDB")

    benchmark_start = time.perf_counter()

    # ---------------------------------------------------------
    # 1. RESET
    # ---------------------------------------------------------
    print()
    print("[1/6] Resetting benchmark collections...")

    reset_start = time.perf_counter()

    for collection_name in [
        "ratings",
        "users",
        "movies",
    ]:
        if db.has_collection(collection_name):
            db.delete_collection(collection_name)

    reset_seconds = (
        time.perf_counter() - reset_start
    )

    print(f"      Reset: {reset_seconds:.3f}s")

    # ---------------------------------------------------------
    # 2. CREATE COLLECTIONS + INDEXES
    # ---------------------------------------------------------
    print("[2/6] Creating collections/indexes...")

    schema_start = time.perf_counter()

    users_col = db.create_collection("users")
    movies_col = db.create_collection("movies")

    # Edge collection represents RATED relationships.
    ratings_col = db.create_collection(
        "ratings",
        edge=True,
    )

    users_col.add_persistent_index(
        fields=["user_id"],
        unique=True,
    )

    movies_col.add_persistent_index(
        fields=["movie_id"],
        unique=True,
    )

    schema_seconds = (
        time.perf_counter() - schema_start
    )

    print(
        f"      Schema setup: "
        f"{schema_seconds:.3f}s"
    )

    # ---------------------------------------------------------
    # 3. LOAD USERS
    # ---------------------------------------------------------
    print("[3/6] Loading User documents...")

    user_query = """
    FOR row IN @rows
        INSERT {
            _key: TO_STRING(row.user_id),
            user_id: row.user_id,
            age: row.age,
            gender: row.gender,
            occupation: row.occupation,
            zip_code: row.zip_code
        }
        INTO users
    """

    user_start = time.perf_counter()

    for batch in batches(users, BATCH_SIZE):
        list(
            db.aql.execute(
                user_query,
                bind_vars={
                    "rows": batch
                },
            )
        )

    user_seconds = (
        time.perf_counter() - user_start
    )

    print(
        f"      {len(users):,} users in "
        f"{user_seconds:.3f}s "
        f"({len(users) / user_seconds:,.1f} nodes/s)"
    )

    # ---------------------------------------------------------
    # 4. LOAD MOVIES
    # ---------------------------------------------------------
    print("[4/6] Loading Movie documents...")

    movie_query = """
    FOR row IN @rows
        INSERT {
            _key: TO_STRING(row.movie_id),
            movie_id: row.movie_id,
            title: row.title,
            release_date: row.release_date,
            release_year: row.release_year,
            genres: row.genres
        }
        INTO movies
    """

    movie_start = time.perf_counter()

    for batch in batches(movies, BATCH_SIZE):
        list(
            db.aql.execute(
                movie_query,
                bind_vars={
                    "rows": batch
                },
            )
        )

    movie_seconds = (
        time.perf_counter() - movie_start
    )

    print(
        f"      {len(movies):,} movies in "
        f"{movie_seconds:.3f}s "
        f"({len(movies) / movie_seconds:,.1f} nodes/s)"
    )

    node_seconds = (
        user_seconds + movie_seconds
    )

    total_nodes = (
        len(users) + len(movies)
    )

    node_throughput = (
        total_nodes / node_seconds
    )

    # ---------------------------------------------------------
    # 5. LOAD RATED EDGES
    # ---------------------------------------------------------
    print("[5/6] Loading RATED relationships...")

    rating_query = """
    FOR row IN @rows
        INSERT {
            _from: CONCAT(
                "users/",
                TO_STRING(row.user_id)
            ),
            _to: CONCAT(
                "movies/",
                TO_STRING(row.movie_id)
            ),
            rating: row.rating,
            timestamp: row.timestamp
        }
        INTO ratings
    """

    relationship_start = time.perf_counter()

    completed = 0

    for batch in batches(
        ratings,
        BATCH_SIZE,
    ):
        list(
            db.aql.execute(
                rating_query,
                bind_vars={
                    "rows": batch
                },
            )
        )

        completed += len(batch)

        if (
            completed % 10000 == 0
            or completed == len(ratings)
        ):
            print(
                f"      Loaded "
                f"{completed:,}/"
                f"{len(ratings):,}"
            )

    relationship_seconds = (
        time.perf_counter()
        - relationship_start
    )

    relationship_throughput = (
        len(ratings)
        / relationship_seconds
    )

    # ---------------------------------------------------------
    # 6. VERIFY
    # ---------------------------------------------------------
    print("[6/6] Verifying graph integrity...")

    verify_start = time.perf_counter()

    user_count = users_col.count()
    movie_count = movies_col.count()
    relationship_count = ratings_col.count()

    node_count = (
        user_count + movie_count
    )

    # Referential integrity:
    # every edge must point to an existing user/movie.
    missing_endpoints = list(
        db.aql.execute(
            """
            RETURN LENGTH(
                FOR r IN ratings
                    FILTER
                        DOCUMENT(r._from) == null
                        OR DOCUMENT(r._to) == null
                    RETURN 1
            )
            """
        )
    )[0]

    verify_seconds = (
        time.perf_counter() - verify_start
    )

    if user_count != 943:
        raise RuntimeError(
            f"Expected 943 users, "
            f"got {user_count}"
        )

    if movie_count != 1682:
        raise RuntimeError(
            f"Expected 1682 movies, "
            f"got {movie_count}"
        )

    if node_count != 2625:
        raise RuntimeError(
            f"Expected 2625 nodes, "
            f"got {node_count}"
        )

    if relationship_count != 100000:
        raise RuntimeError(
            "Expected 100000 relationships, "
            f"got {relationship_count}"
        )

    if missing_endpoints != 0:
        raise RuntimeError(
            "Referential integrity failed: "
            f"{missing_endpoints} bad edges"
        )

    benchmark_seconds = (
        time.perf_counter()
        - benchmark_start
    )

    result = {
        "platform":
            "ArangoDB Managed Platform Trial",
        "dataset":
            "MovieLens 100K",
        "timestamp_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),
        "client": {
            "python":
                sys.version.split()[0],
            "os":
                platform.platform(),
            "machine":
                platform.machine(),
        },
        "configuration": {
            "batch_size":
                BATCH_SIZE,
            "load_method":
                (
                    "python-arango + "
                    "parameterized AQL batches"
                ),
            "query_language":
                "AQL",
            "cloud":
                "Google Cloud Platform",
            "region":
                "Iowa, USA",
            "server_version":
                db.version(),
        },
        "dataset_counts": {
            "users":
                len(users),
            "movies":
                len(movies),
            "nodes":
                total_nodes,
            "relationships":
                len(ratings),
        },
        "timings_seconds": {
            "reset":
                reset_seconds,
            "schema":
                schema_seconds,
            "user_nodes":
                user_seconds,
            "movie_nodes":
                movie_seconds,
            "all_nodes":
                node_seconds,
            "relationships":
                relationship_seconds,
            "verification":
                verify_seconds,
            "end_to_end":
                benchmark_seconds,
        },
        "throughput": {
            "nodes_per_second":
                node_throughput,
            "relationships_per_second":
                relationship_throughput,
        },
        "verification": {
            "users":
                user_count,
            "movies":
                movie_count,
            "nodes":
                node_count,
            "relationships":
                relationship_count,
            "missing_endpoints":
                missing_endpoints,
            "passed":
                True,
        },
    }

    RESULTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    output = (
        RESULTS /
        "arangodb_ingest.json"
    )

    output.write_text(
        json.dumps(
            result,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("==============================================")
    print(" ✅ ARANGODB INGEST BENCHMARK PASSED")
    print("==============================================")
    print(
        f"Nodes:             "
        f"{node_count:,}"
    )
    print(
        f"Relationships:     "
        f"{relationship_count:,}"
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
    print(
        f"Raw result: {output}"
    )


if __name__ == "__main__":
    main()
