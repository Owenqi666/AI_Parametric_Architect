# Case Study: Constraint-Aware Planning Without Implicit Authority

## Question

Can a natural-language architectural request be converted into inspectable constraint-planning
evidence while keeping every coordinate outside the authoritative World Model?

The bundled showcase answers this with three recorded cases: a successful family house, a
same-intent planner comparison for a compact apartment, and a deliberately infeasible spatial
request. All values below come from
`frontend/public/examples/planning-showcase.preview-1.0.0.json`; no metric has been estimated.

## Execution identity

The artifact identifies itself as:

| Field | Recorded value |
| --- | --- |
| Artifact | `detached_floor_plan_showcase` 1.0.0 |
| Execution mode | `deterministic_offline_replay` |
| Intent parser | `recorded-mock-llm-requirement-parser` 1.0.0 |
| Planning agent | `architecture-planner-agent` 2.0.0 |
| Planner strategy | `cp-sat-rectilinear-v1` |
| Rules | 1.0.0 |
| Random seed | 0 |

The recorded Mock path uses the same typed `LLMRequirementParser` and `RequirementAgent`
contracts as a provider-backed parser, but it performs no network call and makes no claim about
real OpenAI output.

For this three-scenario replay, `SHOWCASE_OPTIMIZATION` retains utilization (40), target-area
(12), orientation (20), and optional-constraint (30) objective weights while setting compactness
and circulation objective weights to zero. This lets the five-room fixture prove optimality
quickly without changing hard constraints. The metric evaluator still measures circulation
independently. Therefore the showcase circulation value is evaluation evidence, not a claim that
this replay profile optimized that metric. The bundled planning benchmark uses the standard
`PlanningRules` configuration instead.

## Case 1: South-facing family house

### Requirement

> Design a 120 sqm south-facing family house with three bedrooms, a living room and a kitchen.
> Keep the kitchen adjacent to the living room.

The recorded typed intent preserves:

- `building_type`: `house`;
- `area`: 120 m²;
- `orientation`: `south`;
- rooms: three `bedroom`, one `living`, and one `kitchen`; and
- one required `kitchen adjacent_to living` constraint.

### Detached result

CP-SAT produced a `FloorPlanProposal 2.0.0` with five placed rooms inside a 13.5 m × 10 m
proposal boundary. The proposal digest is:

```text
79997c60ceafb22cf04e0765dfb0c3370d32464aaca9e156120fa91e01167a1b
```

The digest fingerprints the serialized proposal; it is not a signature, World Model ID, or
commit credential.

### Recorded metric evidence

| Metric | Value | Scope |
| --- | ---: | --- |
| Constraint satisfaction | 1.0000000000 | One proposal |
| Spatial efficiency | 0.8888888889 | One proposal |
| Circulation proxy | 0.7106382979 | One proposal |
| Stability | N/A | `REPEATED_PLANS_REQUIRED` |

Constraint satisfaction includes minimum-area, boundary, non-overlap, and declared spatial
checks under metric context `planning-showcase-v1`. Spatial efficiency is room area divided by
proposal-boundary area. Circulation is a normalized room-center Manhattan-distance proxy; it is
not a route, accessibility, or egress analysis.

Stability is correctly absent because the scenario artifact retains one proposal. It does not
invent a repeatability score.

## Case 2: Compact apartment planner tradeoff

### Requirement

> Design a compact 72 sqm apartment with one bedroom, one bathroom, a living room and a kitchen.
> Keep circulation efficient.

Both systems receive the same immutable intent: a 72 m² apartment with the four requested room
types and no representable explicit spatial constraint. The phrase “Keep circulation efficient”
is not silently converted into a hard constraint that the current `DesignIntent` cannot express.

### Recorded comparison

| System | Strategy | Constraint satisfaction | Spatial efficiency | Circulation proxy | Stability |
| --- | --- | ---: | ---: | ---: | --- |
| `rule-spatial-v2` | `rule-based-single-row-v1` | 1.0000000000 | 1.0000000000 | 0.6590909091 | N/A |
| `cp-sat-v2` | `cp-sat-rectilinear-v1` | 1.0000000000 | 0.8571428571 | 0.8198198198 | N/A |

The CP-SAT proposal uses a 10.5 m × 8 m boundary and has digest:

```text
38453a8de65cf1d9cb4a636c26b8de12730ba91291d0fff41efd70e87db8676f
```

The result demonstrates a tradeoff in this metric context: the single-row baseline fills its
boundary completely, while the CP-SAT arrangement has a higher circulation proxy. It does not
establish that either proposal is better for code compliance, constructability, accessibility,
cost, daylight, or actual circulation paths.

## Case 3: Infeasible constraints fail closed

### Requirement

> Design a 40 sqm house with one bedroom and one bathroom. Require the bedroom to be both north
> and south of the bathroom.

The generator supplies a valid typed intent containing two required and jointly incompatible
relations:

- `bedroom north_of bathroom`; and
- `bedroom south_of bathroom`.

The intent reaches CP-SAT. Because only an `OPTIMAL` solver result is accepted, the infeasible
model produces the stable failure:

```json
{
  "stage": "plan",
  "code": "PLANNING_SOLVER_FAILED",
  "path": "/problem"
}
```

The serialized scenario retains the already parsed `DesignIntent` so the UI can show that intent
extraction succeeded and planning failed. It retains no proposal, proposal digest, or metric
evidence. No constraint is dropped, and no fallback rectangle is fabricated.

## What the browser proves

The Design Studio makes the following evidence observable:

- the exact untrusted requirement text;
- the typed intent whenever intent extraction succeeded, including the plan-stage failure;
- proposal room rectangles and declared spatial constraints;
- the versioned execution identity and proposal digest;
- normalized detached metrics; and
- stable fail-closed status for the infeasible case.

It does not prove that the planning click ran CP-SAT live. The browser replays the bundled output
that the generator produced with the actual typed parser and planner pipeline.

## What remains authoritative

The World Model shown beside the proposal is a different artifact:

| Field | World Model sample |
| --- | --- |
| Model ID | `mdl_showcase_house` |
| Revision | 7 |
| Schema | 1.0.0 |
| Render IR | 1.0.0 |
| Floors | 2 |
| Render objects | 26 |

That Three.js scene is derived from `examples/showcase_house.json`, not from any planning
proposal in this case study. The proposal cannot be passed to the Render IR projector. This
separation prevents a compelling preview from being mistaken for committed geometry.

## Decision boundary

If a future product chooses to realize one proposal, it still needs a separately designed typed
realization contract and authorization review. Any resulting candidate must follow the existing
write path:

```text
PatchProposal
  -> authorization
  -> patch a defensive JSON copy
  -> schema + semantic + geometry validation
  -> affected-entity verification
  -> revision CAS
  -> trusted audit event
```

The showcase does not perform any of those steps. A proposal score, solver status, provider
output, or digest cannot substitute for them.

## Outcome

The cases establish the intended product posture:

- successful constraint planning is visible and inspectable;
- different planners can be compared on one intent;
- contradictory hard constraints produce no geometry; and
- neither success nor presentation quality changes World Model authority.

For the broader two-track evaluation, see
[BENCHMARK_METHODOLOGY.md](BENCHMARK_METHODOLOGY.md).
