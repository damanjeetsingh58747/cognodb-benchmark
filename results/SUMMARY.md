# Benchmark Results

Generated automatically from the raw JSON benchmark outputs.

## Ingest throughput

| Platform | Nodes/s | Relationships/s | Relationship load (s) | End-to-end (s) |
| --- | --- | --- | --- | --- |
| CognoDB | 1220.0 | 2463.14 | 40.599 | 47.483 |
| Neo4j AuraDB | 2623.64 | 4878.75 | 20.497 | 27.46 |
| FalkorDB | 1399.35 | 2444.94 | 40.901 | 45.327 |
| Memgraph | 1493.48 | 2585.82 | 38.672 | 43.209 |
| ArangoDB | 933.22 | 1896.92 | 52.717 | 73.441 |

## Read latency — p50 (ms)

| Platform | Point | Indexed | 1-hop | 2-hop | 3-hop | Aggregation |
| --- | --- | --- | --- | --- | --- | --- |
| CognoDB | 275.712 | 275.953 | 344.946 | 566.059 | 307.629 | 541.324 |
| Neo4j AuraDB | 80.413 | 81.852 | 79.832 | 87.55 | 81.337 | 105.991 |
| FalkorDB | 258.64 | 257.165 | 273.917 | 293.834 | 299.896 | 310.019 |
| Memgraph | 263.029 | 263.3 | 282.35 | 296.922 | 289.694 | 299.541 |
| ArangoDB | 286.704 | 301.638 | 297.726 | 1474.932 | 437.303 | 340.151 |

## Read latency — p95 (ms)

| Platform | Point | Indexed | 1-hop | 2-hop | 3-hop | Aggregation |
| --- | --- | --- | --- | --- | --- | --- |
| CognoDB | 547.725 | 585.15 | 614.84 | 1012.647 | 872.171 | 795.258 |
| Neo4j AuraDB | 92.56 | 91.661 | 91.243 | 101.677 | 92.278 | 120.334 |
| FalkorDB | 606.903 | 398.104 | 447.115 | 522.399 | 614.268 | 606.251 |
| Memgraph | 399.174 | 387.141 | 614.249 | 613.917 | 612.502 | 612.84 |
| ArangoDB | 463.15 | 604.774 | 612.58 | 3731.032 | 2625.616 | 568.149 |

## Mixed workload throughput (QPS)

| Platform | C=1 | C=10 | C=40 |
| --- | --- | --- | --- |
| CognoDB | 3.38 | 35.86 | 137.57 |
| Neo4j AuraDB | 12.81 | 101.64 | 462.18 |
| FalkorDB | 3.77 | 39.57 | 158.92 |
| Memgraph | 3.51 | 38.2 | 149.51 |
| ArangoDB | 3.14 | 31.44 | 111.2 |
