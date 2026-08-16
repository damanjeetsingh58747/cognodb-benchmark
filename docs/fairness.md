# Fairness, Resource Parity, and Benchmark Limitations

## Scope

This benchmark compares the managed free or trial configurations that were
actually available to the candidate on 16 August 2026.

It should therefore be interpreted as a **managed-tier benchmark**, not as a
strict hardware-isolated comparison of database engines.

The same dataset, client machine, logical workload, input manifest, warm-up
policy, measurement code, and iteration counts were used wherever possible.

## Dataset parity

Every platform received the same canonical MovieLens 100K graph:

- 943 User nodes
- 1,682 Movie nodes
- 2,625 total nodes
- 100,000 RATED relationships

The canonical processed dataset was generated once and fingerprinted with
SHA-256 before platform-specific loading began.

Every ingest benchmark independently verified the final node and relationship
counts before its result was accepted.

## Workload parity

All platforms used the same logical workloads:

- point lookup
- indexed/filtered lookup
- 1-hop traversal
- 2-hop traversal
- 3-hop traversal
- aggregation
- 90% read / 10% write mixed workload

Read benchmarks used:

- deterministic seed: 20260816
- 20 warm-up executions
- 120 measured executions
- identical user IDs
- identical release-year values
- identical target movie IDs

Mixed workloads used:

- concurrency: 1, 10, 40 clients
- 5-second warm-up
- 20-second measured interval
- approximately 90% reads / 10% writes

## Resource parity

Exact hardware parity was **not achievable across the managed free/trial
tiers**.

| Platform | Tier | RAM | CPU | Region | Parity note |
|---|---|---:|---:|---|---|
| CognoDB | Free c0 | 512 MB | burst to 0.5 vCPU | N. Virginia / us-east4 | Baseline configuration |
| Neo4j AuraDB | Free | Not observable | Not observable | Not captured | Allocation hidden |
| FalkorDB | Free | 100 MB | Not observable | AWS us-east-1 | Less RAM than CognoDB |
| Memgraph | 14-day trial | 2 GB | 2 CPU | Not captured | More resources than CognoDB |
| ArangoDB | 14-day trial | Not observable | Not observable | GCP Iowa | Allocation hidden |

The assignment document described CognoDB c0 as 256 MB RAM. The actual
CognoDB provisioning console on the benchmark date exposed 512 MB RAM,
burstable 0.5 vCPU, 1 GiB storage, and 200 connections. The observed runtime
configuration is used in this report.

Because of these differences, the benchmark does **not** claim that latency or
throughput differences are caused solely by database-engine implementation.

Measured results include the combined effects of:

- database engine
- managed-service configuration
- available CPU and memory
- cloud provider
- network path and region
- service-level throttling
- query-language/runtime implementation

## Region and network caveat

The benchmark client remained the same, but all managed services could not be
provisioned in one identical cloud region.

Therefore client-side latency includes Internet/network round-trip time.

This is particularly important when interpreting low-complexity queries:
network and managed-service overhead may dominate execution time.

## Query-language parity

CognoDB, Neo4j, FalkorDB and Memgraph were queried using equivalent Cypher
workloads.

ArangoDB uses AQL. Its workloads were translated to preserve the same logical
operation and benchmark inputs.

The translation is documented in the source code rather than treating the
query strings themselves as identical.

## Failed/pilot workload disclosure

The initial CognoDB pilot used an exhaustive 3-hop workload that expanded and
deduplicated a large reachable neighborhood. It exceeded CognoDB's execution
deadline during warm-up.

The failure was retained in `docs/pilot_3hop_timeout.md`.

Before any competitor was benchmarked, the production workload was replaced
with a bounded deterministic three-edge point-to-point traversal. That final
workload was then used for every platform.

## Interpretation rule

The results answer:

> "How did these actual managed free/trial configurations behave for this
> reproducible workload from this client?"

They do **not** answer:

> "Which database engine is universally fastest on identical hardware?"

Raw measurements are preserved so future runs can repeat the harness under
more tightly controlled infrastructure.
