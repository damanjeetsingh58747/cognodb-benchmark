#!/usr/bin/env bash
set -euo pipefail

echo "================================================"
echo " Managed Graph Database Benchmark"
echo "================================================"
echo

if [ ! -f ".env" ]; then
    echo "ERROR: .env not found."
    echo "Run: cp .env.example .env"
    echo "Then add your database credentials."
    exit 1
fi

echo "[1/13] Downloading/verifying MovieLens 100K..."
./scripts/download_dataset.sh

echo
echo "[2/13] Preparing canonical dataset..."
python benchmark/prepare_dataset.py

echo
echo "[3/13] Benchmarking CognoDB..."
python benchmark/load_cognodb.py
python benchmark/run_cognodb_reads.py

echo
echo "[4/13] Benchmarking Neo4j AuraDB..."
python benchmark/load_neo4j.py
python benchmark/run_neo4j_reads.py

echo
echo "[5/13] Benchmarking FalkorDB..."
python benchmark/load_falkordb.py
python benchmark/run_falkordb_reads.py

echo
echo "[6/13] Benchmarking Memgraph..."
python benchmark/load_memgraph.py
python benchmark/run_memgraph_reads.py

echo
echo "[7/13] Benchmarking ArangoDB..."
python benchmark/load_arangodb.py
python benchmark/run_arangodb_reads.py

echo
echo "[8/13] Running Bolt mixed workloads..."
python benchmark/run_bolt_mixed.py

echo
echo "[9/13] Running native mixed workloads..."
python benchmark/run_native_mixed.py

echo
echo "[10/13] Measuring control latency..."
python benchmark/run_control_latency.py

echo
echo "[11/13] Building result tables and charts..."
python benchmark/build_results.py

echo
echo "[12/13] Building analysis..."
python benchmark/build_analysis.py

echo
echo "[13/13] Building README..."
python benchmark/build_readme.py

echo
echo "================================================"
echo " ✅ FULL BENCHMARK COMPLETE"
echo "================================================"
echo
echo "Results: results/"
echo "Charts:  charts/"
echo "Report:  README.md"
