# Benchmark Analysis

This section interprets the measured results without assuming that managed-service latency differences are caused solely by database-engine implementation.

## Executive findings

- **Neo4j AuraDB recorded the highest relationship ingest throughput in this run** at 5,157.6 relationships/s.
- **Neo4j AuraDB also recorded the highest 40-client mixed-workload throughput**, at 465.27 QPS.
- All five final mixed-workload runs completed with **zero recorded errors** at concurrency 1, 10 and 40.
- Control-query measurements show that network, protocol and managed-service overhead account for a substantial part of simple-query latency on several platforms.
- Because free/trial resource allocations and regions were not identical, these results are best interpreted as a **managed-tier comparison**, not an isolated engine benchmark.

## Ingest

| Platform | Nodes/s | Relationships/s | Relationship load (s) |
|---|---:|---:|---:|
| CognoDB | 1,062.6 | 1,788.0 | 55.929 |
| Neo4j AuraDB | 3,438.6 | 5,157.6 | 19.389 |
| FalkorDB | 817.4 | 2,383.9 | 41.949 |
| Memgraph | 1,067.4 | 1,924.0 | 51.975 |
| ArangoDB | 768.3 | 1,236.7 | 80.861 |

Neo4j AuraDB produced the highest ingest throughput in this specific run. This should not be treated as an engine-only speedup because the managed tiers expose different and, in some cases, undisclosed compute allocations.

## Control-query latency

A trivial `RETURN 1` query was measured using the same 20-warm-up / 120-measured policy. It does not represent pure network RTT, but provides a useful client-observed latency floor.

| Platform | Control p50 | Control p95 |
|---|---:|---:|
| CognoDB | 613.511 ms | 615.354 ms |
| Neo4j AuraDB | 77.829 ms | 84.867 ms |
| FalkorDB | 307.972 ms | 615.044 ms |
| Memgraph | 313.135 ms | 615.312 ms |
| ArangoDB | 613.849 ms | 616.552 ms |

## Read workloads

| Platform | Point | Indexed | 1-hop | 2-hop | 3-hop | Aggregation |
|---|---:|---:|---:|---:|---:|---:|
| CognoDB | 308.228 | 440.360 | 313.198 | 614.349 | 371.635 | 566.398 |
| Neo4j AuraDB | 80.658 | 83.810 | 82.044 | 88.120 | 84.382 | 102.925 |
| FalkorDB | 262.098 | 308.268 | 343.397 | 374.313 | 413.784 | 320.136 |
| Memgraph | 592.626 | 613.400 | 327.553 | 308.238 | 588.236 | 553.521 |
| ArangoDB | 445.098 | 523.421 | 613.743 | 1536.090 | 614.380 | 566.317 |

For CognoDB, Neo4j and ArangoDB, point-lookup p50 was very close to each platform's control-query p50. This indicates that simple-query results are heavily influenced by the client-to-service path rather than query complexity alone.

ArangoDB's 2-hop and 3-hop workloads moved substantially above its control latency floor, reaching 1536.090 ms and 614.380 ms p50 respectively. In this run, traversal complexity therefore had a clearly observable impact beyond baseline service latency.

CognoDB's production 3-hop workload completed successfully, but the earlier exhaustive 3-hop pilot exceeded the service execution deadline. That pilot failure is intentionally retained in `docs/pilot_3hop_timeout.md`.

## Mixed 90/10 workload

| Platform | QPS @1 | QPS @10 | QPS @40 |
|---|---:|---:|---:|
| CognoDB | 2.12 | 22.19 | 86.90 |
| Neo4j AuraDB | 12.09 | 126.47 | 465.27 |
| FalkorDB | 2.76 | 25.75 | 91.31 |
| Memgraph | 2.28 | 24.77 | 110.41 |
| ArangoDB | 1.94 | 18.23 | 75.28 |

Every platform increased aggregate throughput as client concurrency rose from 1 to 40. Neo4j AuraDB reached the highest measured value at 465.27 QPS. FalkorDB, Memgraph and CognoDB formed the next group, while ArangoDB reached 75.28 QPS.

## What these numbers do — and do not — prove

The benchmark demonstrates how these **actual managed configurations** behaved under one reproducible workload.

It does not establish that one underlying database engine is universally faster than another. Differences in CPU, RAM, service throttling, network region, protocol, cloud provider and query language all remain possible contributors.

For that reason, control-query latency is shown as context but is **not subtracted** from workload latency to manufacture an 'engine-only' number.
