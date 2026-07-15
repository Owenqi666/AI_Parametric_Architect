# Planning Benchmark Methodology

## Purpose

The planning benchmark compares requirement parsing and detached floor-plan generation without
reading or mutating a World Model. It is designed for regression evidence, planner comparison,
and failure analysis. It is not a building-code, accessibility, egress, constructability, or
authorization test.

All reported values in the “Bundled report results” section are extracted from
`frontend/public/examples/planning-core.benchmark-report-1.0.0.json`.

## Input contracts

The benchmark keeps untrusted requirements separate from reference labels:

| Artifact | Bundled identity | Bundled digest |
| --- | --- | --- |
| Dataset | `planning-core` 1.0.0 | `e5c2c55263efe794db4aaf72064946a841b9648dedab896f7c2275556cba4017` |
| Annotation set | `planning-core-reference` 1.0.0 | `3035ca7af6bdadf7029da653b7a6125da950c4fbbaa267c3d60cd8116253f84e` |

The dataset has eight cases. It contains case IDs, sorted tags, and requirement text. The
annotation set binds the exact dataset ID/version and provides one reference intent and constraint
set per case.

Each file is admitted under an exact-field 1.0.0 contract. The loaders reject malformed ordering
or identity, duplicate members, non-standard/non-finite numbers, missing or extra fields, and
over-budget content before running an agent. Each file is capped at 1 MiB, a dataset at 64 cases,
and one requirement at 16 KiB.

The canonical SHA-256 digests detect content differences. They are unkeyed and are neither
signatures nor authenticity or authorization proofs.

## Systems in the bundled report

| System | Parser | Planner | Execution |
| --- | --- | --- | --- |
| `rule-spatial-v2` | deterministic `requirement-agent` | `rule-based-single-row-v1` | deterministic, seed 0 |
| `cp-sat-v2` | deterministic `requirement-agent` | `cp-sat-rectilinear-v1` | deterministic, seed 0 |

Both use rules version 1.0.0 and `architecture-planner-agent` 2.0.0. The report contains no real
provider, model, or prompt metadata, and it does not claim that an OpenAI run occurred.

## Attempt matrix and two tracks

The bundled configuration is:

```text
8 cases × 2 systems × 2 trials = 32 system/case/trial observations
```

Each observation contains both tracks, so each system has 16 configured attempts and 32 measured
track outcomes.

### End-to-end

```text
requirement text -> system parser -> parsed DesignIntent -> system planner
```

The parser receives no reference answer. `intent_exact` is evaluated only after parsing. Spatial
metrics are included only when the parsed intent exactly equals the external reference; this
prevents a geometrically plausible proposal for the wrong intent from being treated as comparable
spatial evidence.

### Oracle-intent

```text
external reference DesignIntent -> same system planner
```

This bypasses parsing and isolates planner behavior. It is not an end-to-end production score and
must not be presented as one.

All binary planning-success and plan-validity metrics retain every configured attempt in their
denominator. Spatial metrics publish explicit covered-attempt and sample counts. Missing coverage
is `N/A` with a stable reason; it is not dropped silently.

## Metric definitions

| Metric | Implemented meaning | Important limitation |
| --- | --- | --- |
| Intent extraction accuracy | Exact immutable `DesignIntent` equality with the reference | Partial semantic matches score false |
| Planning success | Planner returned an exact detached `FloorPlanProposal` | Does not establish correctness |
| Plan validity | Proposal retains the exact reference intent and expected constraint bindings | Not authoritative geometry validation |
| Constraint satisfaction | Mean of room minimum-area, boundary, non-overlap, and declared spatial-relation checks | Thresholds are planning policy, not code |
| Spatial efficiency | Sum of room rectangle areas divided by proposal-boundary area | Does not model structure or circulation area |
| Circulation | `1 - average room-center Manhattan distance / (boundary width + height)` | Not a route, egress, or accessibility analysis |
| Stability | Pairwise normalized similarity across repeated proposals for one exact intent | Not a cryptographic determinism proof |

All normalized metric values must be finite and within `[0, 1]`. Comparisons are meaningful only
under the same serialized metric context. The bundled context is `planning-benchmark-v1`, with two
maximum runs, 1e-9 linear tolerance, nine decimal places, and the room-area/relation thresholds
recorded in the report.

## Bundled report results

### End-to-end track

Both systems have the same parser outcome:

| System | Intent exact | Planning success | Plan validity | Spatial metrics |
| --- | ---: | ---: | ---: | --- |
| `rule-spatial-v2` | 0/16 (`0.0`) | 16/16 (`1.0`) | 0/16 (`0.0`) | N/A: `EXACT_REFERENCE_INTENT_REQUIRED` |
| `cp-sat-v2` | 0/16 (`0.0`) | 16/16 (`1.0`) | 0/16 (`0.0`) | N/A: `EXACT_REFERENCE_INTENT_REQUIRED` |

This is a useful negative result, not missing data. The deterministic parser produced typed
intents and both planners returned proposals, but none of those parsed intents exactly matched
the reference annotation. Because plan validity requires exact reference intent and constraints,
validity is also zero. The report correctly refuses to calculate spatial comparisons for these
non-exact end-to-end results.

### Oracle-intent track

Values below are shown to ten decimal places from the report's stored numbers.

| System | Planning success | Plan validity | Constraint satisfaction | Spatial efficiency | Circulation | Stability |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `rule-spatial-v2` | 1.0000000000 | 1.0000000000 | 0.9678030303 | 1.0000000000 | 0.6412927961 | 1.0000000000 |
| `cp-sat-v2` | 1.0000000000 | 1.0000000000 | 1.0000000000 | 0.8576762087 | 0.7691681740 | 1.0000000000 |

Coverage is 16/16 for every oracle metric. Stability has eight samples per system: one pair for
each case's two deterministic trials. Both systems reproduced identical proposals within this
pinned run, yielding 1.0 stability.

The comparison shows an observed tradeoff under this dataset and metric context. CP-SAT has full
constraint satisfaction and a higher circulation proxy; the single-row baseline has full spatial
efficiency. These values do not establish an overall winner outside the measured definitions.

### Recorded failures

The bundled report contains no non-null failure object on either track. This does not mean the
end-to-end outputs are valid: planning success and plan validity are deliberately separate, as
shown above.

## Runtime evidence

The runner measures injected stages with a monotonic clock and serializes integer nanoseconds.
Runtime is evidence, not a deterministic score input. It varies with hardware, operating system,
dependency state, and concurrent load.

The exact bundled total-runtime summaries are:

| Track | System | Minimum ns | Median ns | p95 ns | Maximum ns | Samples |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| End-to-end | `rule-spatial-v2` | 66,709 | 98,416 | 142,124 | 142,124 | 16 |
| End-to-end | `cp-sat-v2` | 57,021,542 | 101,613,124 | 1,433,684,208 | 1,433,684,208 | 16 |
| Oracle-intent | `rule-spatial-v2` | 13,541 | 15,500 | 29,917 | 29,917 | 16 |
| Oracle-intent | `cp-sat-v2` | 28,079,958 | 92,404,917 | 1,592,144,000 | 1,592,144,000 | 16 |

Oracle parsing is correctly N/A with `NO_RUNTIME_SAMPLES` because the oracle track does not call a
parser. Re-running the benchmark should change timing fields; do not require byte-identical report
JSON as a reproducibility criterion.

## Reproducing the offline benchmark

From the repository root:

```bash
uv sync --dev --locked
uv run ai-architect-benchmark \
  benchmarks/datasets/planning-core-1.0.0.json \
  benchmarks/annotations/planning-core-reference-1.0.0.json \
  planning-benchmark-report.json \
  --trials 2
```

The CLI budget is at most 16 cases, 3 systems, 4 trials, and 192 total
system/case/trial observations. It validates the full product before calling an agent or clock.
It refuses to overwrite either input artifact and requires the output parent directory to exist.

The core benchmark is read-only with respect to World Model state. The outer CLI writes only the
selected report path. Run it with least filesystem privilege; it is not a general filesystem
sandbox and does not replace path, symlink, quota, or retention controls.

To inspect a new report, start the showcase, open `/benchmark`, select **Import report**, and
choose the generated JSON file. The browser caps reports at 4 MiB, validates exact 1.0.0 fields,
finite values, budgets, counts, identities, track consistency, and digests, then deeply freezes
the admitted object.

## Explicit OpenAI benchmark

A real network system is added only when `--openai-model` is supplied:

```bash
export OPENAI_API_KEY='managed-secret-value'
uv run ai-architect-benchmark \
  benchmarks/datasets/planning-core-1.0.0.json \
  benchmarks/annotations/planning-core-reference-1.0.0.json \
  planning-benchmark-openai.json \
  --trials 2 \
  --openai-model '<approved-structured-output-model-snapshot>'
```

The resulting third system is `openai-cp-sat-v2`. Its descriptor is
`real_nondeterministic` and records provider, model, and prompt version. Credentials remain in the
SDK's managed environment channel and are absent from `OpenAIProviderConfig` and report fields.

The network provider supports `DesignIntent` only. It uses strict JSON Schema, no tools,
`store=False`, disabled truncation, and bounded timeout, retries, tokens, and bytes. Provider
output still passes local strict decoding, intent validation, and domain construction. The same
detached CP-SAT planner handles the validated intent.

Running this command incurs real network, latency, and cost. Approve the model snapshot and apply
egress, rate/concurrency, budget, credential, logging, data-retention, and vendor controls first.
No real OpenAI results are present in the bundled report.

## Report security and interpretation

BenchmarkReport 1.0.0 is allowlist-only. It retains system/configuration identity, aggregate
metrics, coverage counts, case/system/trial keys, boolean outcomes, proposal digests, nanosecond
timings, and known failure `stage/code/path`.

It excludes raw requirements, reference intent bodies, proposal geometry, provider output,
prompts, exception messages/details, and dedicated credential fields. Provider/model names and
unkeyed digests can still be sensitive metadata and need access control.

No score, digest, annotation, or report can enter the authorization gateway or revision commit
path. Evaluation evidence remains detached even when every metric is 1.0.
