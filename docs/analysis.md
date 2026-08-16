# Benchmark Analysis

This section interprets the measured results without assuming that managed-service latency differences are caused solely by database-engine implementation.

## Executive findings

- **Neo4j AuraDB recorded the highest relationship ingest throughput in this run** at 4,878.8 relationships/s.
- **Neo4j AuraDB also recorded the highest 40-client mixed-workload throughput**, at 462.18 QPS.
- All five final mixed-workload runs completed with **zero recorded errors** at concurrency 1, 10 and 40.
- Control-query measurements show that network, protocol and managed-service overhead account for a substantial part of simple-query latency on several platforms.
- Because free/trial resource allocations and regions were not identical, these results are best interpreted as a **managed-tier comparison**, not an isolated engine benchmark.

## Ingest

| Platform | Nodes/s | Relationships/s | Relationship load (s) |
|---|---:|---:|---:|
| CognoDB | 1,220.0 | 2,463.1 | 40.599 |
| Neo4j AuraDB | 2,623.6 | 4,878.8 | 20.497 |
| FalkorDB | 1,399.4 | 2,444.9 | 40.901 |
| Memgraph | 1,493.5 | 2,585.8 | 38.672 |
| ArangoDB | 933.2 | 1,896.9 | 52.717 |

Neo4j AuraDB produced the highest ingest throughput in this specific run. This should not be treated as an engine-only speedup because the managed tiers expose different and, in some cases, undisclosed compute allocations.

## Control-query latency

A trivial `RETURN 1` query was measured using the same 20-warm-up / 120-measured policy. It does not represent pure network RTT and is treated only as a client-observed reference measurement.

| Platform | Control p50 | Control p95 |
|---|---:|---:|
| CognoDB | 285.905 ms | 480.437 ms |
| Neo4j AuraDB | 74.486 ms | 88.983 ms |
| FalkorDB | 270.245 ms | 571.603 ms |
| Memgraph | 266.269 ms | 539.151 ms |
| ArangoDB | 294.692 ms | 523.225 ms |

## Read workloads

| Platform | Point | Indexed | 1-hop | 2-hop | 3-hop | Aggregation |
|---|---:|---:|---:|---:|---:|---:|
| CognoDB | 275.712 | 275.953 | 344.946 | 566.059 | 307.629 | 541.324 |
| Neo4j AuraDB | 80.413 | 81.852 | 79.832 | 87.550 | 81.337 | 105.991 |
| FalkorDB | 258.640 | 257.165 | 273.917 | 293.834 | 299.896 | 310.019 |
| Memgraph | 263.029 | 263.300 | 282.350 | 296.922 | 289.694 | 299.541 |
| ArangoDB | 286.704 | 301.638 | 297.726 | 1474.932 | 437.303 | 340.151 |

Neo4j's point-lookup p50 was close to its control-query p50. CognoDB and ArangoDB showed larger differences, demonstrating that the control measurement itself can vary materially. The control results are therefore treated as context rather than values to subtract from workload latency.

ArangoDB's 2-hop workload moved substantially above its control reference, while its bounded 3-hop p50 remained much closer to the control p50. This contrast reinforces that traversal cost and managed-service overhead interact differently across query shapes.

CognoDB's production 3-hop workload completed successfully, but the earlier exhaustive 3-hop pilot exceeded the service execution deadline. That pilot failure is intentionally retained in `docs/pilot_3hop_timeout.md`.

## Mixed 90/10 workload

| Platform | QPS @1 | QPS @10 | QPS @40 |
|---|---:|---:|---:|
| CognoDB | 3.38 | 35.86 | 137.57 |
| Neo4j AuraDB | 12.81 | 101.64 | 462.18 |
| FalkorDB | 3.77 | 39.57 | 158.92 |
| Memgraph | 3.51 | 38.20 | 149.51 |
| ArangoDB | 3.14 | 31.44 | 111.20 |

Every platform increased aggregate throughput as client concurrency rose from 1 to 40. Neo4j AuraDB reached the highest measured value at 462.18 QPS. FalkorDB, Memgraph and CognoDB formed the next group, while ArangoDB reached 111.20 QPS.

## What these numbers do — and do not — prove

The benchmark demonstrates how these **actual managed configurations** behaved under one reproducible workload.

It does not establish that one underlying database engine is universally faster than another. Differences in CPU, RAM, service throttling, network region, protocol, cloud provider and query language all remain possible contributors.

For that reason, control-query latency is shown as context but is **not subtracted** from workload latency to manufacture an 'engine-only' number.
