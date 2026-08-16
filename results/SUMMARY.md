# Benchmark Results

Generated automatically from the raw JSON benchmark outputs.

## Ingest throughput

| Platform | Nodes/s | Relationships/s | Relationship load (s) | End-to-end (s) |
| --- | --- | --- | --- | --- |
| CognoDB | 1216.6 | 1740.74 | 57.447 | 63.282 |
| Neo4j AuraDB | 3269.23 | 4933.96 | 20.268 | 21.66 |
| FalkorDB | 1086.87 | 2666.39 | 37.504 | 42.701 |
| Memgraph | 1035.63 | 2546.62 | 39.268 | 44.845 |
| ArangoDB | 1056.53 | 1959.78 | 51.026 | 71.319 |

## Read latency — p50 (ms)

| Platform | Point | Indexed | 1-hop | 2-hop | 3-hop | Aggregation |
| --- | --- | --- | --- | --- | --- | --- |
| CognoDB | 306.998 | 532.953 | 308.471 | 592.112 | 388.921 | 614.403 |
| Neo4j AuraDB | 79.618 | 79.392 | 79.724 | 85.396 | 81.843 | 100.862 |
| FalkorDB | 307.488 | 308.171 | 293.643 | 274.535 | 306.233 | 301.775 |
| Memgraph | 342.475 | 321.955 | 308.95 | 321.364 | 294.509 | 326.837 |
| ArangoDB | 304.518 | 302.443 | 298.557 | 1663.782 | 544.969 | 429.638 |

## Read latency — p95 (ms)

| Platform | Point | Indexed | 1-hop | 2-hop | 3-hop | Aggregation |
| --- | --- | --- | --- | --- | --- | --- |
| CognoDB | 383.386 | 615.856 | 616.58 | 1189.455 | 976.476 | 920.949 |
| Neo4j AuraDB | 89.584 | 89.602 | 92.782 | 100.667 | 93.098 | 114.644 |
| FalkorDB | 633.059 | 615.256 | 547.334 | 614.962 | 614.574 | 356.453 |
| Memgraph | 639.254 | 622.396 | 615.521 | 615.778 | 615.605 | 614.997 |
| ArangoDB | 615.032 | 613.746 | 614.326 | 4347.129 | 3234.546 | 695.58 |

## Mixed workload throughput (QPS)

| Platform | C=1 | C=10 | C=40 |
| --- | --- | --- | --- |
| CognoDB | 3.14 | 33.41 | 136.41 |
| Neo4j AuraDB | 12.27 | 124.1 | 466.19 |
| FalkorDB | 3.4 | 39.86 | 155.08 |
| Memgraph | 3.31 | 36.85 | 149.8 |
| ArangoDB | 3.0 | 25.82 | 103.04 |
