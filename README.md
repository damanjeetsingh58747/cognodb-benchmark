# Managed Graph Database Cloud Benchmark

**CognoDB vs Neo4j AuraDB vs FalkorDB vs Memgraph vs ArangoDB**

> A reproducible benchmark of five managed graph database configurations using one canonical dataset, deterministic query inputs, client-observed latency, percentile reporting, and explicit fairness caveats.

---

## TL;DR

Five graph database services were benchmarked using the same **MovieLens 100K** graph:

- **943 User nodes**
- **1,682 Movie nodes**
- **2,625 total nodes**
- **100,000 `RATED` relationships**

Every final ingest run verified the expected graph counts before its measurements were accepted.

Read workloads used:

- 20 warm-up executions
- 120 measured executions
- deterministic seed `20260816`
- identical start-node IDs
- identical lookup values
- identical target movie IDs

Mixed read/write tests used:

- **90% reads / 10% writes**
- concurrency **1 / 10 / 40**
- 5-second warm-up
- 20-second measured interval

**Important:** this is a managed free/trial-tier comparison, not a strict hardware-normalized engine benchmark. Resource allocations and regions were not identical across providers.

---

## Why this benchmark exists

Graph database benchmarks are easy to make misleading.

Changing datasets, query inputs, indexes, warm-up policy, regions or client behavior can make a database appear faster without actually demonstrating a meaningful architectural advantage.

This project therefore focuses on:

1. **reproducibility**
2. **same logical workloads**
3. **deterministic inputs**
4. **percentile latency instead of averages alone**
5. **raw result preservation**
6. **explicit disclosure of resource and region mismatches**

---

## Platforms

| Platform | Configuration used | Observed resources | Region | Query interface |
|---|---|---|---|---|
| CognoDB | Free c0 | 512 MB RAM, burst to 0.5 vCPU, 1 GiB storage | N. Virginia / us-east4 | Cypher / Bolt |
| Neo4j AuraDB | Free | RAM/vCPU not exposed | Not captured | Cypher / Bolt |
| FalkorDB | Free | 100 MB RAM | AWS us-east-1 | Cypher / FalkorDB client |
| Memgraph | 14-day Cloud trial | 2 GB RAM, 2 CPU | Not captured | Cypher / Bolt |
| ArangoDB | 14-day managed trial | RAM/vCPU not exposed | GCP Iowa | AQL / HTTPS |

See [`docs/fairness.md`](docs/fairness.md) for the full resource-parity discussion.

---

## Dataset

The benchmark uses the public **MovieLens 100K** dataset.

Canonical graph model:

```text
(User)-[:RATED {rating, timestamp}]->(Movie)
```

The upstream dataset is downloaded by script rather than redistributed inside this repository.

After download, the source is normalized once into:

```text
data/processed/users.csv
data/processed/movies.csv
data/processed/ratings.csv
data/processed/manifest.json
```

The processed files are SHA-256 fingerprinted so that every database can be shown to consume the same canonical input.

---

## Benchmark workloads

### Read workloads

| Workload | Logical operation |
|---|---|
| Point lookup | Fetch one user by ID |
| Indexed lookup | Filter/count movies by indexed release year |
| 1-hop | User → rated movies |
| 2-hop | User → movie ← other users |
| 3-hop | User → movie ← user → deterministic target movie |
| Aggregation | Group/count `RATED` relationships by rating value |

### Mixed workload

The mixed workload uses approximately:

```text
90% reads
10% writes
```

with client concurrency:

```text
1 → 10 → 40
```

Temporary benchmark-write records are removed between phases.

---

# Results

## Repeated-trial summary

Three separate full benchmark executions were archived to measure run-to-run variability. Aggregate values are reported as mean +/- sample standard deviation of the per-run metrics; latency percentiles are not pooled across runs.

See [`results/REPEATED_RUNS.md`](results/REPEATED_RUNS.md) for the full three-run analysis and repeated-run charts.

One Neo4j concurrency-40 execution showed a pronounced throughput/latency degradation. It is retained and included in the aggregate rather than discarded as an outlier.

![Repeated mixed QPS](charts/repeated_mixed_qps_mean_std.png)

The tables below show the latest individual execution; use the repeated-run report for variability-aware interpretation.

---

## 1. Relationship ingest throughput

| Platform | Nodes/s | Relationships/s | Relationship load | End-to-end |
|---|---:|---:|---:|---:|
| CognoDB | 1,220.0 | 2,463.1 | 40.599 s | 47.483 s |
| Neo4j AuraDB | 2,623.6 | 4,878.8 | 20.497 s | 27.460 s |
| FalkorDB | 1,399.4 | 2,444.9 | 40.901 s | 45.327 s |
| Memgraph | 1,493.5 | 2,585.8 | 38.672 s | 43.209 s |
| ArangoDB | 933.2 | 1,896.9 | 52.717 s | 73.441 s |

![Relationship ingest throughput](charts/ingest_relationship_throughput.png)

In this run, **Neo4j AuraDB recorded the highest relationship ingest throughput**. This is a managed-tier result and should not be treated as proof of an engine-only speed advantage because underlying resource allocations differ.

---

## 2. Read latency — p50

| Platform | Point | Indexed | 1-hop | 2-hop | 3-hop | Aggregation |
|---|---:|---:|---:|---:|---:|---:|
| CognoDB | 275.712 ms | 275.953 ms | 344.946 ms | 566.059 ms | 307.629 ms | 541.324 ms |
| Neo4j AuraDB | 80.413 ms | 81.852 ms | 79.832 ms | 87.550 ms | 81.337 ms | 105.991 ms |
| FalkorDB | 258.640 ms | 257.165 ms | 273.917 ms | 293.834 ms | 299.896 ms | 310.019 ms |
| Memgraph | 263.029 ms | 263.300 ms | 282.350 ms | 296.922 ms | 289.694 ms | 299.541 ms |
| ArangoDB | 286.704 ms | 301.638 ms | 297.726 ms | 1474.932 ms | 437.303 ms | 340.151 ms |

![Read p50 latency](charts/read_p50_ms.png)

---

## 3. Read latency — p95

| Platform | Point | Indexed | 1-hop | 2-hop | 3-hop | Aggregation |
|---|---:|---:|---:|---:|---:|---:|
| CognoDB | 547.725 ms | 585.150 ms | 614.840 ms | 1012.647 ms | 872.171 ms | 795.258 ms |
| Neo4j AuraDB | 92.560 ms | 91.661 ms | 91.243 ms | 101.677 ms | 92.278 ms | 120.334 ms |
| FalkorDB | 606.903 ms | 398.104 ms | 447.115 ms | 522.399 ms | 614.268 ms | 606.251 ms |
| Memgraph | 399.174 ms | 387.141 ms | 614.249 ms | 613.917 ms | 612.502 ms | 612.840 ms |
| ArangoDB | 463.150 ms | 604.774 ms | 612.580 ms | 3731.032 ms | 2625.616 ms | 568.149 ms |

![Read p95 latency](charts/read_p95_ms.png)

---

## 4. Mixed workload throughput

| Platform | C=1 | C=10 | C=40 |
|---|---:|---:|---:|
| CognoDB | 3.38 QPS | 35.86 QPS | 137.57 QPS |
| Neo4j AuraDB | 12.81 QPS | 101.64 QPS | 462.18 QPS |
| FalkorDB | 3.77 QPS | 39.57 QPS | 158.92 QPS |
| Memgraph | 3.51 QPS | 38.20 QPS | 149.51 QPS |
| ArangoDB | 3.14 QPS | 31.44 QPS | 111.20 QPS |

![Mixed QPS scaling](charts/mixed_qps_scaling.png)

All 15 final concurrency points completed with **zero recorded query errors**.

---

## 5. Mixed workload p95 latency

![Mixed workload p95 latency](charts/mixed_p95_latency.png)

---

## 6. Control-query latency

A trivial `RETURN 1` query was measured using the same 20 warm-up / 120 measured policy.

This is **not pure network RTT**, but it helps expose the baseline client-to-managed-service cost before graph work becomes significant.

| Platform | Control p50 | Control p95 |
|---|---:|---:|
| CognoDB | 285.905 ms | 480.437 ms |
| Neo4j AuraDB | 74.486 ms | 88.983 ms |
| FalkorDB | 270.245 ms | 571.603 ms |
| Memgraph | 266.269 ms | 539.151 ms |
| ArangoDB | 294.692 ms | 523.225 ms |

### Why this matters

Control-query latency varied materially across platforms and should be treated as contextual client-to-service overhead rather than a subtractable engine baseline.

For example:

- CognoDB control p50: **285.905 ms**
- CognoDB point lookup p50: **275.712 ms**

- Neo4j control p50: **74.486 ms**
- Neo4j point lookup p50: **80.413 ms**

That makes it unsafe to attribute the entire observed query latency to the graph engine itself.

The control value is therefore shown as context but **not subtracted** from workload latency.

---

## Key observations

### Neo4j AuraDB

Neo4j recorded the lowest client-observed latency across most workloads and the highest mixed-workload throughput in this particular run.

Its control-query latency was also dramatically lower than the other services, indicating that service/network path differences are likely a significant part of the observed advantage.

### CognoDB

CognoDB successfully loaded and queried the complete 100,000-edge graph on the small c0 free tier.

Its control-query p50 was higher than its point-lookup p50 in this run, showing that managed-service latency was noisy. The control measurement is therefore used only as context, not as an engine-time baseline.

An earlier exhaustive 3-hop pilot exceeded CognoDB's execution deadline. That result was retained rather than hidden; see [`docs/pilot_3hop_timeout.md`](docs/pilot_3hop_timeout.md).

### FalkorDB

FalkorDB completed the full dataset despite the free tier's much smaller 100 MB memory allocation and scaled strongly as concurrency increased.

### Memgraph

Memgraph also scaled strongly under the mixed workload, but its 2 GB / 2 CPU trial allocation is materially larger than CognoDB c0 and must be considered when interpreting the comparison.

### ArangoDB

ArangoDB's simple requests remained near its control latency floor, but its 2-hop and 3-hop traversal latencies increased substantially. ArangoDB used equivalent AQL rather than Cypher.

---

## Methodology

### Deterministic inputs

A fixed manifest is generated once:

```text
configs/read_manifest.json
```

It contains the warm-up and measured IDs/values used by every platform.

### Client-side timing

Latency is measured with:

```python
time.perf_counter_ns()
```

The timer surrounds the complete client request/response path, so the results intentionally represent **client-observed managed-service latency**.

### Warm-up

Every read workload receives 20 warm-up executions before 120 measured executions.

### Percentiles

The benchmark records:

- p50
- p95
- p99
- mean
- standard deviation
- minimum
- maximum

### Data integrity

Every ingest result is accepted only after verifying:

```text
943 User nodes
1,682 Movie nodes
2,625 total nodes
100,000 relationships
```

ArangoDB additionally checks edge endpoint integrity.

---

## Fairness and limitations

The largest limitation is **hardware/resource parity**.

Managed free and trial tiers did not expose equivalent RAM, CPU, storage or regions.

Therefore the results answer:

> **How did these actual managed free/trial configurations behave for this reproducible workload from this client?**

They do **not** answer:

> **Which underlying graph engine is universally fastest on identical hardware?**

Full discussion:

- [`docs/fairness.md`](docs/fairness.md)
- [`docs/query_parity.md`](docs/query_parity.md)
- [`docs/analysis.md`](docs/analysis.md)
- [`docs/pilot_3hop_timeout.md`](docs/pilot_3hop_timeout.md)

---

## Reproducing the benchmark

### 1. Clone

```bash
git clone https://github.com/damanjeetsingh58747/cognodb-benchmark.git
cd cognodb-benchmark
```

### 2. Create Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### 3. Configure credentials

```bash
cp .env.example .env
```

Fill in your own service credentials.

**Never commit `.env`.**

### 4. Download dataset

```bash
./scripts/download_dataset.sh
```

### 5. Prepare canonical graph

```bash
python benchmark/prepare_dataset.py
```

Platform-specific loaders and workload runners live under `benchmark/`.

A single orchestration script is provided in `scripts/run_all.sh`.

---

## Repository layout

```text
benchmark/
  prepare_dataset.py
  load_cognodb.py
  load_neo4j.py
  load_falkordb.py
  load_memgraph.py
  load_arangodb.py
  run_*_reads.py
  run_*_mixed.py
  build_results.py
  build_analysis.py

configs/
  read_manifest.json
  platform_specs.json

docs/
  fairness.md
  query_parity.md
  analysis.md
  pilot_3hop_timeout.md

results/
  raw/
  summary_ingest.csv
  summary_reads.csv
  summary_mixed.csv
  SUMMARY.md

charts/
```

---

## Security

Credentials are read exclusively from environment variables.

The repository intentionally excludes:

- database passwords
- private connection credentials
- `.env`

Only `.env.example` is committed.

---

## Raw results

The final tables and charts are generated from the raw JSON outputs rather than manually transcribed benchmark values.

This makes it possible to audit the reported results and reduces the risk of documentation drift.

---

## Full analysis

See **[`docs/analysis.md`](docs/analysis.md)** for interpretation of the measurements and **[`docs/fairness.md`](docs/fairness.md)** for the benchmarking limitations.

---

## Author

**Damanjeet Singh**

Backend / AI / ML engineering

---

*Benchmark conducted on 16 August 2026.*
