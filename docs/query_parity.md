# Query and Index Parity

## Purpose

This document makes the cross-platform workload mapping explicit.

CognoDB, Neo4j, FalkorDB and Memgraph use Cypher-compatible workloads. ArangoDB uses AQL, so parity is defined by equivalent logical operations rather than identical query syntax.

Parity means:

- same canonical graph
- same deterministic input values
- same traversal direction
- same hop count
- same result meaning
- equivalent lookup indexes where applicable

## Canonical graph

```text
(User)-[:RATED {rating, timestamp}]->(Movie)
```

Dataset:

- 943 User nodes
- 1,682 Movie nodes
- 2,625 total nodes
- 100,000 RATED relationships

## Shared benchmark inputs

All platforms use the same deterministic manifest:

```text
seed = 20260816
warm-up executions = 20
measured executions = 120
```

The same user IDs, release-year values and target movie IDs are reused across all platforms.

For the bounded 3-hop workload:

```text
target_movie_id = ((user_id * 37) % 1682) + 1
```

# Workload parity

## 1. Point lookup

Logical operation: find one User by `user_id` and return the user's age.

### Cypher

```cypher
MATCH (u:User {user_id: $user_id})
RETURN u.age AS value
```

### ArangoDB AQL

```aql
FOR u IN users
    FILTER u.user_id == @user_id
    LIMIT 1
    RETURN { value: u.age }
```

Index: `User.user_id`.

## 2. Indexed lookup

Logical operation: count movies having the supplied release year.

### Cypher

```cypher
MATCH (m:Movie {release_year: $release_year})
RETURN count(m) AS value
```

### ArangoDB AQL

```aql
LET matches = (
    FOR m IN movies
        FILTER m.release_year == @release_year
        RETURN 1
)
RETURN { value: LENGTH(matches) }
```

Index: `Movie.release_year`.

The final benchmark creates an equivalent release-year index for every platform.

## 3. One-hop traversal

Logical operation: `User -> Movie`. Count movies rated by the selected user.

### Cypher

```cypher
MATCH (:User {user_id: $user_id})
      -[:RATED]->(m:Movie)
RETURN count(m) AS value
```

### ArangoDB AQL

```aql
FOR start IN users
    FILTER start.user_id == @user_id
    LIMIT 1

    LET reached = (
        FOR m IN 1..1 OUTBOUND start._id ratings
            RETURN 1
    )

    RETURN { value: LENGTH(reached) }
```

## 4. Two-hop traversal

Logical operation: `User -> Movie <- Other User`. Count distinct other users who rated at least one movie also rated by the starting user.

### Cypher

```cypher
MATCH (:User {user_id: $user_id})
      -[:RATED]->(:Movie)
      <-[:RATED]-(other:User)
WHERE other.user_id <> $user_id
RETURN count(DISTINCT other) AS value
```

### ArangoDB AQL

```aql
FOR start IN users
    FILTER start.user_id == @user_id
    LIMIT 1

    LET others = (
        FOR m IN 1..1 OUTBOUND start._id ratings
            FOR other IN 1..1 INBOUND m._id ratings
                FILTER other.user_id != @user_id
                RETURN DISTINCT other.user_id
    )

    RETURN { value: LENGTH(others) }
```

## 5. Three-hop traversal

Logical operation:

```text
Start User -> Movie <- Other User -> Target Movie
```

The target movie is deterministic and at most one result is returned.

### Cypher

```cypher
MATCH (start:User {user_id: $user_id})
      -[:RATED]->(:Movie)
      <-[:RATED]-(other:User)
      -[:RATED]->(target:Movie {movie_id: $target_movie_id})
WHERE other.user_id <> $user_id
RETURN target.movie_id AS value
LIMIT 1
```

### ArangoDB AQL

```aql
FOR start IN users
    FILTER start.user_id == @user_id
    LIMIT 1

    LET found = FIRST(
        FOR m IN 1..1 OUTBOUND start._id ratings
            FOR other IN 1..1 INBOUND m._id ratings
                FILTER other.user_id != @user_id

                FOR target IN 1..1 OUTBOUND other._id ratings
                    FILTER target.movie_id == @target_movie_id
                    RETURN target.movie_id
    )

    FILTER found != null
    RETURN { value: found }
```

### Why the final 3-hop workload is bounded

An earlier CognoDB pilot used an exhaustive 3-hop expansion and exceeded the service execution deadline. That result is retained in `docs/pilot_3hop_timeout.md`.

The bounded deterministic workload was selected before competitor production measurements and then used across every platform.

## 6. Aggregation

Logical operation: group all RATED relationships by rating value and count each group.

### Cypher

```cypher
MATCH ()-[r:RATED]->()
RETURN r.rating AS rating,
       count(*) AS count
ORDER BY rating
```

### ArangoDB AQL

```aql
FOR r IN ratings
    COLLECT rating = r.rating
    WITH COUNT INTO count
    SORT rating
    RETURN {
        rating: rating,
        count: count
    }
```

# Index parity

| Property | Purpose |
|---|---|
| `User.user_id` | Point lookup and traversal start |
| `Movie.movie_id` | Relationship loading and target lookup |
| `Movie.release_year` | Indexed release-year lookup |

Implementations differ by database:

- CognoDB / Neo4j: uniqueness constraints plus release-year index
- FalkorDB: property indexes
- Memgraph: supported Cypher constraints/indexes
- ArangoDB: persistent indexes

The objective is equivalent lookup capability, not identical DDL syntax.

# Timing parity

Read latency is measured client-side using:

```python
time.perf_counter_ns()
```

The measured interval includes the complete request/response path. Reported latency can therefore include database execution, query planner/runtime behavior, network latency, protocol overhead and managed-service overhead.

The benchmark intentionally reports client-observed managed-service latency.

# Interpretation

Query parity means that each database performs the same logical operation on the same graph with the same deterministic inputs.

It does not imply identical query planners, execution engines, protocols or storage implementations. Those differences are part of what this managed-service benchmark measures.
