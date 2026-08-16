#!/usr/bin/env bash

set -euo pipefail

DATA_DIR="data"
ZIP_FILE="$DATA_DIR/ml-100k.zip"
EXTRACTED_DIR="$DATA_DIR/ml-100k"
URL="https://files.grouplens.org/datasets/movielens/ml-100k.zip"

mkdir -p "$DATA_DIR"

echo "========================================"
echo " MovieLens 100K Dataset Setup"
echo "========================================"

if [ ! -f "$ZIP_FILE" ]; then
    echo "[1/4] Downloading MovieLens 100K..."
    curl -L "$URL" -o "$ZIP_FILE"
else
    echo "[1/4] Dataset archive already exists."
fi

if [ ! -d "$EXTRACTED_DIR" ]; then
    echo "[2/4] Extracting..."
    unzip -q "$ZIP_FILE" -d "$DATA_DIR"
else
    echo "[2/4] Dataset already extracted."
fi

echo "[3/4] Verifying dataset..."

RATINGS=$(wc -l < "$EXTRACTED_DIR/u.data" | tr -d ' ')
USERS=$(wc -l < "$EXTRACTED_DIR/u.user" | tr -d ' ')
MOVIES=$(wc -l < "$EXTRACTED_DIR/u.item" | tr -d ' ')

if [ "$RATINGS" -ne 100000 ]; then
    echo "ERROR: Expected 100000 ratings, found $RATINGS"
    exit 1
fi

if [ "$USERS" -ne 943 ]; then
    echo "ERROR: Expected 943 users, found $USERS"
    exit 1
fi

if [ "$MOVIES" -ne 1682 ]; then
    echo "ERROR: Expected 1682 movies, found $MOVIES"
    exit 1
fi

echo "[4/4] Dataset verified successfully."
echo
echo "Users:         $USERS"
echo "Movies:        $MOVIES"
echo "Relationships: $RATINGS"
echo
echo "Graph model:"
echo "(User)-[:RATED {rating, timestamp}]->(Movie)"
