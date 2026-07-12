## Ordering guarantees

A message MUST be delivered at least once. A message MUST be delivered in order per partition. A message MUST NOT be delivered before its dependencies.

Each guarantee is stated separately and on purpose; do not merge them.
