from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "ml-100k"
OUT = ROOT / "data" / "processed"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_genres() -> list[str]:
    genres = {}

    with (RAW / "u.genre").open(
        "r",
        encoding="latin-1"
    ) as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            name, idx = line.split("|")
            genres[int(idx)] = name

    return [genres[i] for i in sorted(genres)]


def prepare_users() -> list[dict]:
    users = []

    with (RAW / "u.user").open(
        "r",
        encoding="latin-1"
    ) as f:
        reader = csv.reader(f, delimiter="|")

        for row in reader:
            user_id, age, gender, occupation, zip_code = row

            users.append({
                "user_id": int(user_id),
                "age": int(age),
                "gender": gender,
                "occupation": occupation,
                "zip_code": zip_code,
            })

    users.sort(key=lambda x: x["user_id"])
    return users


def prepare_movies(genres: list[str]) -> list[dict]:
    movies = []

    with (RAW / "u.item").open(
        "r",
        encoding="latin-1"
    ) as f:
        reader = csv.reader(f, delimiter="|")

        for row in reader:
            movie_id = int(row[0])
            title = row[1]
            release_date = row[2]

            flags = row[5:]

            active_genres = [
                genres[i]
                for i, flag in enumerate(flags)
                if i < len(genres) and flag == "1"
            ]

            release_year = ""
            if release_date and len(release_date) >= 4:
                release_year = release_date[-4:]

            movies.append({
                "movie_id": movie_id,
                "title": title,
                "release_date": release_date,
                "release_year": release_year,
                "genres": ";".join(active_genres),
            })

    movies.sort(key=lambda x: x["movie_id"])
    return movies


def prepare_ratings() -> list[dict]:
    ratings = []

    with (RAW / "u.data").open(
        "r",
        encoding="latin-1"
    ) as f:
        reader = csv.reader(f, delimiter="\t")

        for row in reader:
            user_id, movie_id, rating, timestamp = row

            ratings.append({
                "user_id": int(user_id),
                "movie_id": int(movie_id),
                "rating": int(rating),
                "timestamp": int(timestamp),
            })

    # Fixed ordering means every database receives the same ingest sequence.
    ratings.sort(
        key=lambda x: (
            x["user_id"],
            x["movie_id"],
            x["timestamp"]
        )
    )

    return ratings


def write_csv(
    path: Path,
    rows: list[dict],
    fieldnames: list[str]
) -> None:

    with path.open(
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(rows)


def validate(
    users: list[dict],
    movies: list[dict],
    ratings: list[dict]
) -> None:

    assert len(users) == 943, (
        f"Expected 943 users, got {len(users)}"
    )

    assert len(movies) == 1682, (
        f"Expected 1682 movies, got {len(movies)}"
    )

    assert len(ratings) == 100000, (
        f"Expected 100000 ratings, got {len(ratings)}"
    )

    user_ids = {u["user_id"] for u in users}
    movie_ids = {m["movie_id"] for m in movies}

    assert len(user_ids) == len(users), "Duplicate user IDs detected"
    assert len(movie_ids) == len(movies), "Duplicate movie IDs detected"

    for rating in ratings:

        assert rating["user_id"] in user_ids, (
            f"Unknown user {rating['user_id']}"
        )

        assert rating["movie_id"] in movie_ids, (
            f"Unknown movie {rating['movie_id']}"
        )

        assert 1 <= rating["rating"] <= 5, (
            f"Invalid rating {rating['rating']}"
        )


def main() -> None:

    if not RAW.exists():
        raise SystemExit(
            "Dataset not found. Run ./scripts/download_dataset.sh first."
        )

    OUT.mkdir(parents=True, exist_ok=True)

    print("Preparing canonical graph dataset...")

    genres = load_genres()
    users = prepare_users()
    movies = prepare_movies(genres)
    ratings = prepare_ratings()

    print("Validating source data...")
    validate(users, movies, ratings)

    users_file = OUT / "users.csv"
    movies_file = OUT / "movies.csv"
    ratings_file = OUT / "ratings.csv"

    write_csv(
        users_file,
        users,
        [
            "user_id",
            "age",
            "gender",
            "occupation",
            "zip_code",
        ]
    )

    write_csv(
        movies_file,
        movies,
        [
            "movie_id",
            "title",
            "release_date",
            "release_year",
            "genres",
        ]
    )

    write_csv(
        ratings_file,
        ratings,
        [
            "user_id",
            "movie_id",
            "rating",
            "timestamp",
        ]
    )

    manifest = {
        "dataset": "MovieLens 100K",
        "source": (
            "https://files.grouplens.org/"
            "datasets/movielens/ml-100k.zip"
        ),
        "graph_model": (
            "(User)-[:RATED {rating, timestamp}]->(Movie)"
        ),
        "counts": {
            "users": len(users),
            "movies": len(movies),
            "nodes_total": len(users) + len(movies),
            "relationships": len(ratings),
        },
        "ordering": {
            "users": "user_id ascending",
            "movies": "movie_id ascending",
            "ratings": (
                "user_id, movie_id, timestamp ascending"
            ),
        },
        "source_sha256": {
            "u.user": sha256(RAW / "u.user"),
            "u.item": sha256(RAW / "u.item"),
            "u.data": sha256(RAW / "u.data"),
        },
        "processed_sha256": {
            "users.csv": sha256(users_file),
            "movies.csv": sha256(movies_file),
            "ratings.csv": sha256(ratings_file),
        },
    }

    manifest_file = OUT / "manifest.json"

    manifest_file.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True
        ),
        encoding="utf-8"
    )

    print()
    print("✅ Canonical dataset ready")
    print(f"Users:          {len(users):,}")
    print(f"Movies:         {len(movies):,}")
    print(f"Total nodes:    {len(users) + len(movies):,}")
    print(f"Relationships:  {len(ratings):,}")
    print()

    print("SHA-256 fingerprints:")
    print(
        "users.csv:   ",
        manifest["processed_sha256"]["users.csv"]
    )
    print(
        "movies.csv:  ",
        manifest["processed_sha256"]["movies.csv"]
    )
    print(
        "ratings.csv: ",
        manifest["processed_sha256"]["ratings.csv"]
    )

    print()
    print(f"Manifest: {manifest_file}")


if __name__ == "__main__":
    main()
