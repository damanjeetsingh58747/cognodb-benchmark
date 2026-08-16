# Benchmark Results

Generated automatically from the raw JSON benchmark outputs.

## Ingest throughput

| Platform | Nodes/s | Relationships/s | Relationship load (s) | End-to-end (s) |
| --- | --- | --- | --- | --- |
| CognoDB | 1062.59 | 1787.99 | 55.929 | 64.471 |
| Neo4j AuraDB | 3438.62 | 5157.63 | 19.389 | 25.099 |
| FalkorDB | 817.37 | 2383.87 | 41.949 | 47.922 |
| Memgraph | 1067.37 | 1923.99 | 51.975 | 58.367 |
| ArangoDB | 768.31 | 1236.69 | 80.861 | 104.752 |

## Read latency — p50 (ms)

| Platform | Point | Indexed | 1-hop | 2-hop | 3-hop | Aggregation |
| --- | --- | --- | --- | --- | --- | --- |
| CognoDB | 308.228 | 440.36 | 313.198 | 614.349 | 371.635 | 566.398 |
| Neo4j AuraDB | 80.658 | 83.81 | 82.044 | 88.12 | 84.382 | 102.925 |
| FalkorDB | 262.098 | 308.268 | 343.397 | 374.313 | 413.784 | 320.136 |
| Memgraph | 592.626 | 613.4 | 327.553 | 308.238 | 588.236 | 553.521 |
| ArangoDB | 445.098 | 523.421 | 613.743 | 1536.09 | 614.38 | 566.317 |

## Read latency — p95 (ms)

| Platform | Point | Indexed | 1-hop | 2-hop | 3-hop | Aggregation |
| --- | --- | --- | --- | --- | --- | --- |
| CognoDB | 630.696 | 615.559 | 614.092 | 1159.762 | 750.491 | 769.827 |
| Neo4j AuraDB | 97.373 | 100.976 | 98.754 | 99.808 | 101.485 | 119.293 |
| FalkorDB | 425.545 | 615.247 | 623.801 | 615.695 | 615.625 | 615.592 |
| Memgraph | 615.409 | 625.189 | 615.6 | 615.129 | 629.366 | 620.881 |
| ArangoDB | 616.16 | 624.698 | 616.235 | 3663.503 | 2767.919 | 709.675 |

## Mixed workload throughput (QPS)

| Platform | C=1 | C=10 | C=40 |
| --- | --- | --- | --- |
| CognoDB | 2.12 | 22.19 | 86.9 |
| Neo4j AuraDB | 12.09 | 126.47 | 465.27 |
| FalkorDB | 2.76 | 25.75 | 91.31 |
| Memgraph | 2.28 | 24.77 | 110.41 |
| ArangoDB | 1.94 | 18.23 | 75.28 |
