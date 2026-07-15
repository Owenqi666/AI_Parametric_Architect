# Planning benchmark artifacts

`datasets/planning-core-1.0.0.json` contains only case identifiers, sorted tags,
and untrusted natural-language requirements. It is an input corpus, not World
Model state.

`annotations/planning-core-reference-1.0.0.json` is a separate reference-label
artifact keyed by the same case identifiers. Its expected intents and constraints
are evaluation evidence only. They are never revisions, authorization evidence,
or committed geometry.

Both artifacts use strict standard JSON and schema version `1.0.0`. Load them
through `load_benchmark_dataset` and `load_benchmark_annotations`; the latter can
bind the annotation set to a loaded dataset and require exact one-to-one coverage.
Canonical SHA-256 digests are calculated from the normalized immutable contracts,
not treated as World Model identities.

Relation clauses use positional references after an explicit room list. This keeps
the deterministic parser's supported room grammar unambiguous while still testing
the known boundary that it does not extract spatial constraints. The end-to-end
track therefore isolates requirement-understanding quality; the oracle-intent
track compares planners against the same external reference intent.
