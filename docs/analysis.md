# Benchmark Analysis

This section interprets the measured results without assuming that managed-service latency differences are caused solely by database-engine implementation.

## Executive findings

- **Neo4j AuraDB recorded the highest relationship ingest throughput in this run** at 4,934.0 relationships/s.
- **Neo4j AuraDB also recorded the highest 40-client mixed-workload throughput**, at 466.19 QPS.
- All five final mixed-workload runs completed with **zero recorded errors** at concurrency 1, 10 and 40.
- Control-query measurements show that network, protocol and managed-service overhead account for a substantial part of simple-query latency on several platforms.
- Because free/trial resource allocations and regions were not identical, these results are best interpreted as a **managed-tier comparison**, not an isolated engine benchmark.

## Ingest

| Platform | Nodes/s | Relationships/s | Relationship load (s) |
|---|---:|---:|---:|
| CognoDB | 1,216.6 | 1,740.7 | 57.447 |
| Neo4j AuraDB | 3,269.2 | 4,934.0 | 20.268 |
| FalkorDB | 1,086.9 | 2,666.4 | 37.504 |
| Memgraph | 1,035.6 | 2,546.6 | 39.268 |
| ArangoDB | 1,056.5 | 1,959.8 | 51.026 |

Neo4j AuraDB produced the highest ingest throughput in this specific run. This should not be treated as an engine-only speedup because the managed tiers expose different and, in some cases, undisclosed compute allocations.

## Control-query latency

A trivial `RETURN 1` query was measured using the same 20-warm-up / 120-measured policy. It does not represent pure network RTT, but provides a useful client-observed latency floor.

| Platform | Control p50 | Control p95 |
|---|---:|---:|
| CognoDB | 289.187 ms | 614.049 ms |
| Neo4j AuraDB | 74.646 ms | 87.390 ms |
| FalkorDB | 253.554 ms | 556.694 ms |
| Memgraph | 263.045 ms | 613.748 ms |
| ArangoDB | 307.703 ms | 614.528 ms |

## Read workloads

| Platform | Point | Indexed | 1-hop | 2-hop | 3-hop | Aggregation |
|---|---:|---:|---:|---:|---:|---:|
| CognoDB | 306.998 | 532.953 | 308.471 | 592.112 | 388.921 | 614.403 |
| Neo4j AuraDB | 79.618 | 79.392 | 79.724 | 85.396 | 81.843 | 100.862 |
| FalkorDB | 307.488 | 308.171 | 293.643 | 274.535 | 306.233 | 301.775 |
| Memgraph | 342.475 | 321.955 | 308.950 | 321.364 | 294.509 | 326.837 |
| ArangoDB | 304.518 | 302.443 | 298.557 | 1663.782 | 544.969 | 429.638 |

For CognoDB, Neo4j and ArangoDB, point-lookup p50 was very close to each platform's control-query p50. This indicates that simple-query results are heavily influenced by the client-to-service path rather than query complexity alone.

ArangoDB's 2-hop and 3-hop workloads moved substantially above its control latency floor, reaching 1663.782 ms and 544.969 ms p50 respectively. In this run, traversal complexity therefore had a clearly observable impact beyond baseline service latency.

CognoDB's production 3-hop workload completed successfully, but the earlier exhaustive 3-hop pilot exceeded the service execution deadline. That pilot failure is intentionally retained in `docs/pilot_3hop_timeout.md`.

## Mixed 90/10 workload

| Platform | QPS @1 | QPS @10 | QPS @40 |
|---|---:|---:|---:|
| CognoDB | 3.14 | 33.41 | 136.41 |
| Neo4j AuraDB | 12.27 | 124.10 | 466.19 |
| FalkorDB | 3.40 | 39.86 | 155.08 |
| Memgraph | 3.31 | 36.85 | 149.80 |
| ArangoDB | 3.00 | 25.82 | 103.04 |

Every platform increased aggregate throughput as client concurrency rose from 1 to 40. Neo4j AuraDB reached the highest measured value at 466.19 QPS. FalkorDB, Memgraph and CognoDB formed the next group, while ArangoDB reached 103.04 QPS.

## What these numbers do — and do not — prove

The benchmark demonstrates how these **actual managed configurations** behaved under one reproducible workload.

It does not establish that one underlying database engine is universally faster than another. Differences in CPU, RAM, service throttling, network region, protocol, cloud provider and query language all remain possible contributors.

For that reason, control-query latency is shown as context but is **not subtracted** from workload latency to manufacture an 'engine-only' number.
