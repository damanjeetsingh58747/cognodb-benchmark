# Pilot workload finding

During the initial CognoDB read benchmark, the exhaustive 3-hop workload:

MATCH (:User {user_id: $user_id})
      -[:RATED]->(:Movie)
      <-[:RATED]-(other:User)
      -[:RATED]->(m2:Movie)
WHERE other.user_id <> $user_id
RETURN count(DISTINCT m2) AS value

hit:

Neo.TransientError.General.OutOfTimeError
context deadline exceeded

during warm-up.

This pilot result was preserved rather than hidden.

The production 3-hop benchmark was changed before benchmarking any
competitor to a bounded point-to-point three-edge traversal. The revised
logical query is then used identically for every platform.
