# Architecture

## Goals and non-goals

The deterministic core proves the following paths:

```text
JSON document -> structural validation -> semantic/geometry validation -> SVG
validated JSON World Model -> immutable Render IR 1.0.0 -> strict frontend admission -> read-only Three.js scene
JSON revision -> patch a copy -> validate -> compare-and-swap commit -> audit
requirement JSON -> intent schema + semantics -> immutable DesignIntent
DesignIntent -> PlanningRules + CP-SAT -> detached spatial FloorPlanProposal -> semantic PatchProposal
ValidationIssue -> symbolic ConstraintResolutionPlan (no automatic edit)
typed LLM suggestion -> existing Agent ports -> proposal values only
untrusted requirement -> OpenAI strict output -> local DesignIntent validation -> existing CP-SAT detached proposal
Scenario -> Agent pipeline -> detached full validation -> evaluation metrics
versioned dataset + external annotations -> two-track benchmark -> redacted detached report
observable JSON boundaries -> tenant/domain HMAC + safe metadata -> AgentTrace
```

The provider-neutral LLM contract retains its deterministic Mock. Final Enhancement
Priority 2 adds an explicitly enabled OpenAI Responses infrastructure adapter for
DesignIntent extraction only; default composition remains deterministic and offline.
Priority 3 adds a World-Model/repository-read-only benchmark core and an offline-default
report-writing CLI; Priorities 1–3 do not add World Model editing, proposal realization,
automatic geometry correction, DXF, or IFC export.

## Architectural style

The system is a modular monolith using ports and adapters. This keeps deployment
simple while enforcing boundaries that can later be split if operational evidence
justifies it.

```text
CLI / FastAPI adapter
        |
application use cases
        |
intent / domain contracts and ports
   /          |          |          |          |          |          |          \
agents    planning   reasoning    policy     geometry   validation   editing   rendering
typed I/O  proposal   symbolic   authorize    adapter       rules     adapters    adapter
   ^                                 ^
typed LLM adapters          detached evaluation

agent_trace observes typed JSON boundaries by hash only; it is not in the write path

validated rendering path: renderer adapter -> Render IR -> frontend Three.js adapter

detached comparison path: benchmark CLI -> injected parsers/planners -> redacted report
```

Dependency rules:

1. Persisted JSON World Model revisions are authoritative for model state. Other
   persisted JSON artifacts, including benchmark fixtures/reports, retain detached
   identities and no World Model authority; runtime objects are disposable projections.
2. Domain contracts do not import FastAPI, Shapely, SVG, OpenAI, or IFC libraries.
3. Shapely objects stay inside the geometry engine boundary.
4. Validators and renderers are read-only and never normalize or repair input
   silently.
5. API and CLI adapters translate transport concerns only; orchestration belongs
   to application use cases.
6. World-Model-derived render/export output is reproducible from a model revision.
   Proposals, evaluations, and benchmarks instead use their own typed inputs and
   explicit version/rules/configuration identity; benchmark artifacts add canonical
   content digests.
7. One `StrictJsonTreeGuard` definition protects API, validation, editing, and
   evaluation boundaries. Only alias-free standard JSON trees may enter model
   snapshots, patch values, or audit details.
8. A revision commit atomically advances its snapshot, head, undo/redo state, and
   audit event under optimistic compare-and-swap control.
9. Design intents and plans are proposal values, never alternative persisted world
   states; agents cannot call repositories or mutate model documents.
10. Planner and Patch Agent output is independently constrained by an authorization
    policy and application gateway before the existing patch, validation, and CAS
    commit pipeline can run. Evaluation success confers no write authority.
11. LLM providers return only exact immutable proposal types and expose no repository,
    model-mutation, validation-bypass, or commit operation.
12. Evaluation applies patches only to defensive copies through ports, runs complete
    validation, and never commits a revision.
13. Agent traces retain tenant/domain-separated keyed digests and allowlisted metadata
    only; prompts, content, tool arguments/results, rationale, and chain-of-thought are
    prohibited. Trace fingerprints provide correlation, not anonymization.
14. Render IR is projected only after complete validation of an authoritative
    `ModelDocument`; it is never a repository snapshot, Patch input, or commit credential.
15. Three.js is confined to `frontend/`. Neutral Python domain and renderer code do not
    depend on it, and the frontend has no editing, authorization, repository, or commit client.
16. Planner, solver, and evaluation output cannot enter Render IR as authoritative geometry.
    A detached proposal must first pass a separately authorized realization, complete
    validation, and CAS commit before the committed JSON can be projected.
17. Vendor SDK and network imports are confined to `infrastructure/llm`. The real provider
    accepts no revision or World Model and supports only `DesignIntent`; all other output
    kinds fail before a request is sent.
18. The benchmark top-level surface is read-only. Dataset, annotation, proposal, and report
    values are detached evidence; none is a World Model/revision value, authorization
    result, or commit input. The core runner receives providers, planners, and clocks only
    through narrow injected ports and has no world-write dependency.

## JSON model strategy

Schema version 1 uses a flat, typed entity registry. Entity IDs are stable keys,
which gives JSON Patch stable paths and prevents duplicate keys inside each entity
type. Each value also contains its ID; semantic validation enforces that the key
and value agree and that IDs are globally unique.

References point in one direction only:

- floor -> building
- room and wall -> floor
- door and window -> host wall
- stair -> lower and upper floor

Parent objects do not repeat child ID lists. Door and window locations are defined
relative to an oriented host wall, so moving a wall cannot leave an independent
opening coordinate behind.

The model uses a local, right-handed Cartesian coordinate system, Z up, metres and
degrees. Floor elevation supplies the Z datum for 2D floor geometry. Supporting a
second unit system requires an explicit schema version and conversion boundary.

JSON Schema Draft 2020-12 owns structural constraints. Cross-entity references,
key/ID equality, polygon topology, overlap, and opening placement are deterministic
domain rules because JSON Schema cannot express them reliably.

## Production-oriented trust boundaries

Read paths share one layered admission pipeline:

```text
transport/library input
  -> StrictJsonTreeGuard
  -> JSON Schema
  -> ModelComplexityPolicy
  -> semantic/reference rules
  -> finite Shapely-derived predicates
  -> deterministic SVG or Render IR output
```

The JSON guard rejects non-standard numbers, non-JSON Python values, cycles, shared
mutable containers, and excessive nesting before schema or geometry traversal. The
complexity policy centrally caps total entities, polygon vertices, coordinate
magnitude, room area, wall length, and Patch operation count. HTTP request size is
also bounded in the transport adapter. These controls keep the accepted work set
finite and predictable; gateway rate limits, deadlines, concurrency quotas, and
process resource limits remain deployment responsibilities.

The browser applies a second read-only admission boundary:

```text
same-origin Render IR JSON
  -> 2 MiB response cap
  -> exact version and field parser
  -> finite values + reference checks + count/point budgets
  -> deeply frozen Render IR
  -> hard-coded Three.js scene mapping
```

This parser does not accept World Model JSON or planner proposals. Scene materials,
textures, colors, and shaders are local implementation choices rather than data-driven
capabilities supplied by the IR.

Revision initialization takes ownership before validation:

```text
caller-owned mutable input
  -> strict JSON check + immediate defensive snapshot
  -> validate that snapshot
  -> extract identity from that snapshot
  -> construct and atomically store that same snapshot
```

No later read of the caller-owned dictionary participates in the transaction. Patch
and restoration candidates already originate from defensive copies and are likewise
validated before CAS commit.

Agent writes have a separate authorization boundary:

```text
untrusted PatchProposal + DesignIntent
  -> AgentAuthorizationGateway
  -> deterministic intent/operation/path/entity policy
  -> ordinary Patch + validation + affected-ID verification
  -> CAS commit with TrustedAuditIdentity
```

The gateway accepts an explicit typed commit request, not an `EvaluationReport`,
`BenchmarkReport`, or arbitrary proposal-shaped mapping. Audit identity travels on a
trusted application channel and is never inferred from LLM-controlled provenance or
rationale. The latter remain stored only as explicitly untrusted diagnostics.

## Modules

| Module | Responsibility | Must not do |
| --- | --- | --- |
| `contracts` | Load and apply the versioned JSON Schema | Repair or reinterpret geometry |
| `domain` | Neutral issue/result types, model vocabulary, and immutable Render IR values | Import infrastructure libraries, FastAPI, or Three.js |
| `intent` | Load/validate Design Intent Schema and expose neutral intent models | Persist geometry or import LLM clients |
| `agents` | Provide typed requirement, planning, reasoning, and patch-generation boundaries | Access repositories or mutate world state |
| `llm` | Define typed prompts/providers and adapt them to proposal-only Agent ports | Import vendor SDKs, access repositories, mutate, validate, or commit models |
| `planning` | Parse requirements, build detached Plan IR, and produce proposal-only semantic patches | Commit revisions or access Shapely |
| `reasoning` | Map validation errors to detached symbolic candidate Plans | Generate coordinates, patches, or automatic corrections |
| `evaluation` | Run scenarios and metrics with detached Patch validation | Access repositories or commit revisions |
| `agent_trace` | Hash observable Agent inputs/outputs and record allowlisted execution metadata | Store content, prompts, hidden reasoning, or obtain write capabilities |
| `policy` | Authorize exact Agent proposal capabilities against intent and immutable context | Apply patches, validate geometry, access repositories, or commit |
| `editing` | Strict RFC 6901 pointers and atomic add/remove/replace operations | Commit or validate models |
| `geometry_engine` | Build transient geometry and calculate predicates | Persist Shapely objects |
| `validation` | Run independently testable L1-L4 rules | Mutate the model |
| `renderer` | Project validated models into deterministic SVG or Render IR | Invent, persist, or commit geometry |
| `application` | Orchestrate validation, rendering, patch, and restoration use cases | Contain transport logic |
| `backend` | FastAPI transport adapter | Contain validation rules |
| `benchmark` | Load separate versioned requirements/references and produce detached two-track reports | Read or mutate World Model state, authorize, validate, patch, revise, or commit |
| `ports` | Define clock, patch, planning, rendering/projecting, export, and revision boundaries | Implement vendor behavior |
| `repositories` | Store immutable revisions, history stacks, and audit events | Skip CAS or validation orchestration |
| `infrastructure` | Provide production adapters such as UTC/monotonic clocks and opt-in OpenAI requirement extraction | Own domain policy or obtain write-side capabilities |
| `frontend` | Admit versioned Render IR, build/dispose Three.js resources, and provide read-only interaction | Read raw World Model JSON, generate Patch operations, access revisions, authorize, or commit |

## Validation levels

- L1: finite coordinates, closed/valid polygons, non-zero walls and areas.
- L2: ID and reference integrity, room overlap, opening host and bounds.
- L3: extensible building-code rules; only explicitly configured rules may run.
- L4: future engineering and structural constraints.

Issues have stable machine-readable codes, severity, JSON Pointer path, involved
entity IDs, human-readable message, and optional details. Renderers reject models
with error-level issues.

## Three.js visualization boundary: Final Enhancement Priority 1

The visualization path is a one-way projection:

```text
authoritative JSON ModelDocument
  -> StrictJsonTreeGuard
  -> Schema + complexity + semantic + geometry validation
  -> WorldModelRenderIRProjector
  -> immutable RenderIR 1.0.0
  -> JSON transport or synchronized static fixture
  -> frontend exact parser
  -> read-only Three.js scene
```

`ArchitectService.render_ir` performs full validation before invoking the projector.
`POST /v1/models/render/ir` exposes the same boundary and returns the existing structured
validation report, plus stable floor-not-found and no-renderable-geometry errors. The
projector depends on neutral domain, geometry, and rendering ports; it preserves stable
floor/entity ordering, source revision identity, metres/degrees, and the model-native
right-handed Z-up frame.

Render IR contains bounds, floors, and explicit room surface, wall extrusion, and
door/window panel objects with stable entity IDs. It is a fresh standard-JSON derivative,
not a second World Model. The viewer provides camera control, floor visibility,
selection, and inspection only. Names remain untrusted display strings and are inserted
as React text; the IR cannot provide HTML, URLs, textures, materials, colors, or shaders.

Scene teardown stops the animation loop, removes listeners, disconnects the
`ResizeObserver`, disposes controls, geometry, materials, textures, renderer lists, and
the renderer, and releases the WebGL context. Render IR v1 deliberately omits stairs and
represents openings as visible panels without wall CSG. Those display limitations do not
change or reinterpret authoritative geometry.

## Incremental editing boundary

`PatchProposal` carries a `base_model_id`, `base_revision`, operations, provenance,
rationale, and declared affected entity IDs.
The stable subset implements RFC 6902 `add`, `remove`, and `replace`, with strict
RFC 6901 path decoding. Root removal is deliberately undefined and rejected.
The application layer additionally protects root replacement, `model_id`,
`revision`, `schema_version`, and `geometry_settings`. Precision-policy migration
requires a separate explicit use case, so a geometry candidate cannot relax its
own acceptance tolerance.

The transaction is:

```text
authorize Agent proposal when the source is an Agent
  -> compare proposal model ID + read immutable head + compare base revision
  -> enforce Patch operation budget
  -> copy JSON
  -> apply all operations atomically
  -> increment application-owned revision
  -> strict JSON + schema + model-complexity validation
  -> semantic and Shapely geometry validation
  -> derive affected IDs from the validated before/after JSON delta
  -> require exact agreement with proposal metadata
  -> repository CAS
  -> atomically store snapshot/history/audit
```

Undo and redo are compensating commits. The repository first returns a read-only
preview token containing the current head and stack target. The application restores
that JSON into a new candidate, revalidates it against the current schema and geometry
policy, then performs a CAS commit that also verifies the preview is still current.
This supports rule upgrades without silently restoring a now-invalid historical model.
A successful branch edit clears redo. Any rejected operation, stale preview, or invalid
candidate leaves all repository state unchanged.

The current repository is thread-safe and process-local. A future database adapter
must preserve the same atomicity and defensive-copy semantics. Deterministic
Requirement and Architecture Planner agents now produce intent/plan proposals only.
Production composition remains deterministic by default. The Mock is available for
explicit injection, and `create_openai_requirement_agent` is the sole opt-in network
composition path. No provider is injected into the default service and no agent may
edit persisted models directly.

Every write also requires a separately supplied `TrustedAuditIdentity` containing
`actor_id`, typed actor category, `trace_id`, and an `agent_version` for Agent actors.
Proposal-controlled `provenance` and `rationale` never populate these trusted fields.

## Agent evolution boundary: Task 1

The versioned Design Intent contract is the first non-geometric intermediate
representation:

```text
requirement input
  -> Design Intent Draft 2020-12 Schema
  -> DesignIntent semantic validation
  -> Requirement Agent / Architecture Planner
  -> PatchProposal
  -> existing validation and revision transaction
```

`DesignIntent`, `RoomRequirement`, and `SpatialConstraint` are immutable,
provider-neutral domain values. They import no LLM SDK, FastAPI, or Shapely. The
canonical JSON form uses an expanded room-type array for compatibility with the
existing planning trace. An exactly-one compact `room_requirements` representation
is accepted at the input boundary and normalized only when constructing a new
domain value; `IntentValidator` itself is read-only.

Spatial constraints are type-level requirements between two different requested
room types. V1 supports adjacency, proximity, separation, and cardinal relative
direction. It deliberately does not include coordinates or distances. Multiple
instances of the same room type remain a later selector/versioning concern rather
than an implicit guess.

Design Intent is not the world model. It may be stored as a versioned planning trace
inside the owned model extension namespace, but room geometry remains solely in the
authoritative model entities. Even when Task 7.1 satisfies constraints inside a
detached proposal-local boundary, those fields remain unverified in the persisted
planning record until a separately authorized realization is validated against the
World Model.

Task 2 provides the explicit Agent interface and Requirement Agent. Task 3 adds a
distinct FloorPlanProposal/Plan IR in front of the existing room-slot patch boundary;
Phase 7 Task 7.1 supplies the first optimization solver behind that unchanged port.

## Requirement Agent boundary: Task 2

Task 2 adds a generic, runtime-checkable `Agent[InputT, OutputT]` protocol with stable
name, version, and `run` operation. The concrete `RequirementAgent` has the narrow
contract:

```text
natural-language string
  -> injected RequirementParser
  -> immutable DesignIntent
```

It is frozen and holds no execution memory. It does not accept a model or revision,
and the `agents` package is architecture-tested against application, editing,
repository, transport, geometry, renderer, LLM-provider, and Shapely dependencies.
The injected parser is excluded from `repr` so a future provider adapter cannot leak
client details through diagnostics.

For compatibility with the pre-existing safe planning application,
`RequirementAgent.parse` delegates to the same `run` boundary and implements the
`RequirementParser` port. The production composition root injects the deterministic
rule parser today. Parser errors propagate with stable structured codes; a dependency
that violates the declared output type is converted to `AGENT_CONTRACT_VIOLATION`.
No provider SDK or network call exists in this milestone.

## Constraint-aware Architecture Planner: Task 3 + Phase 7 Task 7.1

Task 3 introduced the second frozen Agent boundary and a detached Plan IR. Phase 7
Task 7.1 changes the injected planning implementation, not the Agent count or its
authority:

```text
DesignIntent + SpatialConstraint + PlanningRules
  -> ArchitecturePlannerAgent (existing port)
  -> ConstraintFloorPlanPlanner
  -> PlanningProblem
  -> OR-Tools CP-SAT
       variables: room x/y/width/height/orientation
       hard constraints: area/boundary/non-overlap/adjacency/separation
       soft objective: utilization/compactness/circulation/orientation
  -> detached FloorPlanProposal v2
  -> semantic-only PatchProposal
  -> authorization policy
  -> patch copy + complete validation + CAS commit
```

`FloorPlanProposal` remains one exact immutable value type so existing typed Agent,
LLM, and evaluation gates do not accept a parallel lookalike contract. Its JSON shape
is version-dispatched:

- v1 (`1.0.0`) is the original semantic-only contract. Each room has exactly
  `plan_id`, `room_type`, and `target_area`.
- v2 (`2.0.0`) requires a proposal-local boundary and complete finite
  `x/y/width/height/orientation` placement for every room. Its constructor and parser
  independently reject partial placement, boundary escape, overlap, non-finite area,
  and orientation/exposure mismatch.

The provider-neutral `FloorPlanPlanner.plan(intent)` port is unchanged. The
composition root now injects `ConstraintFloorPlanPlanner`; the legacy
`RuleBasedFloorPlanPlanner` remains available only as an explicit v1 compatibility
adapter. No OR-Tools object crosses `planning/solver`, and that package cannot import
World Model, revision, Patch, repository, application, FastAPI, LLM, Shapely,
renderer, or validation modules.

### Solver model and rules

CP-SAT uses an integer grid controlled only by `PlanningGridPolicy`; lengths and
areas cannot use unrelated scale constants. A `PlanningProblem` freezes the validated
intent, its exact type-level spatial constraints, versioned `PlanningRules`, derived
integer boundary, stable room specifications, and first-instance constraint bindings.
The boundary is either explicitly supplied by rules or derived by their declared
utilization/aspect policy. It is not inferred from an existing World Model.

For each axis-aligned rectangular room the model creates `x`, `y`, `width`, `height`,
end coordinates, area, doubled center coordinates, intervals, target-area deviation,
and a one-hot cardinal/interior exposure. Hard constraints include:

- room-type minimum area and minimum dimensions;
- containment in the proposal-local boundary;
- `NoOverlap2D` for every room;
- adjacency as exact side contact with a positive shared-edge length;
- separation as a configured clear gap on at least one axis;
- proximity and cardinal relative-position relations.

Required relations are hard. An optional relation is reified and contributes a
bounded penalty. The integer optimization objective combines unused net room area,
target-area deviation, bounding-box perimeter proxy, pairwise doubled-center Manhattan
distance, orientation misses, and optional-constraint misses. The circulation term is
only a geometric distance proxy; it is not door connectivity, accessibility, or
egress analysis.

### Determinism and failure semantics

The solver dependency is pinned to `ortools==9.15.6755`. Variables, constraints, and
output use stable plan-ID order. Repeated room types receive a stable symmetry-breaking
order. CP-SAT runs with one worker, fixed seed, disabled permutation, and a deterministic
time budget. A bounded secondary objective breaks equal-primary-score ties. The adapter
only accepts `OPTIMAL`; `FEASIBLE`, `UNKNOWN`, `MODEL_INVALID`, and `INFEASIBLE` become
structured `PLANNING_SOLVER_FAILED` errors. There is no equal-area fallback. Byte
stability is tested for repeated runs under the pinned solver/runtime; it is not
promised across future OR-Tools versions or arbitrary CPU architectures.

### Proposal is not realization

The solved coordinates remain transient advisory data. The existing patch generator
still reads only room type/order and may target only pre-existing room `name`/`usage`
plus the owned planning extension. Authorization remains an independent exact
allowlist and continues to reject geometry operations. Consequently a planning commit
does not copy solver rectangles into World Model geometry, and the source intent's
area, orientation, building type, and spatial relations remain explicitly unverified
in the persisted planning record.

`WorldModelRenderIRProjector` accepts an authoritative `ModelDocument`, never a
`FloorPlanProposal`. A solver placement therefore cannot appear as committed Three.js
geometry merely because it can be evaluated. It must first pass a separately authorized
realization, complete Validation, and CAS Commit; the existing geometry authorization
allowlist remains unchanged.

Promoting a selected placement into authoritative geometry is a later capability. It
will require a new typed realization contract and authorization review, followed by
the unchanged Patch -> complete Validation -> CAS Commit path. Task 7.2 evaluates
detached placements but does not realize them. The restricted real provider adapter and
detached benchmark are now implemented; Task 7.3 knowledge retrieval and the Task 7.6
proposal-evaluation loop remain later work.

## Constraint Reasoning boundary: Task 4

Task 4 adds a conservative error-deliberation branch:

```text
error-severity ValidationIssue
  -> ConstraintReasoningAgent
  -> RuleBasedConstraintSolver
  -> ConstraintResolutionPlan
       -> candidates_available: symbolic CandidateSolution values
       -> manual_review_required: no guessed candidate
```

`ConstraintResolutionPlan` is another allowed Plan output, not an alternative world
state. It retains only the source issue code/path/entity IDs, a deterministic strategy
and schema version, status, and symbolic candidates. Candidate actions are currently
`move_wall`, `resize_room`, and `change_layout`; each includes affected IDs and a
rationale, but never coordinates, `PatchOperation`, model JSON, or revision data.

The first rule set deliberately recognizes only safely localized `ROOM_OVERLAP` and
`WALL_ZERO_LENGTH` errors. Code, strict RFC 6901 registry path, referenced entity
identity, and expected cardinality must agree. Unsupported or mismatched inputs produce
`manual_review_required` with no candidates. Malformed issue snapshots and non-error
severities are rejected at both solver and Agent contracts. This prevents a suggestion
from being mistaken for a verified correction.

The `ConstraintSolver[PlanT]` port is provider-neutral and runtime-introspectable.
The reasoning package depends only on neutral issue/error vocabulary and is
architecture-tested against validation implementation, Shapely, application,
editing, repositories, world-model/revision/Patch types, network providers, time,
and randomness. The production composition root injects deterministic rules only.

There is intentionally no automatic reasoning-to-edit loop in Task 4. A future Task 5
Patch Generator must receive an explicitly selected Plan plus the current immutable
revision, produce a `PatchProposal`, and remain subject to the existing application
authorization policy, copy, complete validation, and CAS commit transaction.

Task 4 issue identity does not include a model revision. Consequently a reasoning Plan
is advisory only and cannot authorize a later edit or establish freshness. The first
Task 5 generator is restricted to a `FloorPlanProposal` explicitly paired with its
current `ModelRevision`; consuming constraint-resolution Plans requires a future
revision-bound request contract.

## Patch Generator boundary: Task 5

Task 5 makes the final proposal-producing Agent explicit:

```text
DesignIntent
  -> ArchitecturePlannerAgent
  -> FloorPlanProposal
  -> PatchGenerationRequest(plan, immutable current revision)
  -> PatchGeneratorAgent
  -> PatchProposal(base model, base revision, operations, provenance, rationale, affected IDs)
  -> authorization policy / gateway
  -> patch a copy -> complete validation -> CAS commit -> audit
```

`PatchGeneratorAgent` may read only the explicitly supplied immutable revision envelope.
It cannot access a repository, patch engine, validator, application service, geometry
adapter, or transport. It validates the provider result's type, exact base model and revision,
non-empty affected-entity set, and existence of every reported ID in the supplied
snapshot. A `None` result is the explicit idempotent no-change outcome.

The provider-neutral `PatchProposalGenerator[PlanT]` port uses a contravariant Plan
type. The current deterministic adapter is the existing semantic `RuleBasedPlanner`
through its side-effect-free `generate` operation. `AgentPlanningPipeline` sequences
the FloorPlan and Patch ports and implements the pre-existing `ProposalPlanner`
contract; the production composition root injects the two concrete Agents.

`PatchProposal.affected_entity_ids` may be empty only when the patch changes no entity.
After complete model validation, the application compares the before/after JSON entity
registries and the owned planning record, derives a canonical affected-ID set, and
requires exact set equality with the declaration. Only that independently verified set
is copied into append-only audit details. `base_model_id` additionally prevents a
proposal created for one model from being replayed against another model that happens
to share the same revision number. A no-change planning result re-reads the head before
returning and reports a revision conflict if planning raced with another commit.

The current generator remains semantic-only: it can assign existing room names/usages
and update the owned planning trace, but cannot invent geometry. Supporting a selected
Task 4 candidate requires a future revision-bound Plan and a dedicated generator;
unbound `ConstraintResolutionPlan` values are intentionally rejected by type.

## LLM Adapter boundary: Task 6.1

The LLM layer is an outer, provider-neutral adapter rather than a new domain owner:

```text
StructuredPrompt[DesignIntent | FloorPlanProposal | PatchProposal]
  -> LLMProvider.complete
  -> exact immutable output-type check
  -> RequirementParser / FloorPlanPlanner / PatchProposalGenerator adapter
  -> existing Agent contract checks
```

`LLMOutput` is a closed union of the three proposal values. Runtime checks use exact
types, rejecting arbitrary mappings and subclasses as well as an output of the wrong
kind. Prompt builders are deterministic. The Patch prompt receives only an explicitly
supplied detached `ModelRevision` snapshot, but projects only model/revision binding,
the owned planning record, and the existing room slots' required semantic fields.
Coordinates, arbitrary metadata, and unrelated extension content are excluded. The
adapter does not discover a repository or current head itself.

`LLMRequirementParser`, `LLMFloorPlanPlanner`, and `LLMPatchProposalGenerator` expose
only `parse`, `plan`, and `generate`, respectively. They can be injected into the
existing Agents through structural ports but cannot apply a Patch, run a commit, or
obtain repository state. `MockLLMProvider` is an ordered in-memory typed-response
adapter for deterministic tests.

Final Enhancement Priority 2 adds one concrete outer adapter:

```text
natural-language requirement
  -> canonical JSON data envelope
  -> OpenAI Responses API (strict DesignIntent transport schema, no tools, store=false)
  -> bounded response envelope
  -> strict JSON decode
  -> IntentValidator schema + semantic validation
  -> exact DesignIntent.from_dict
  -> RequirementAgent
  -> existing ConstraintFloorPlanPlanner
  -> detached FloorPlanProposal v2
```

The SDK import is confined to `infrastructure/llm/openai_provider.py`. Its transport
schema is a defensive canonical expansion of the authoritative Design Intent contract:
all five fields are required for Structured Outputs, `rooms` is expanded, orientation
is nullable, and spatial constraints are always an array. The packaged provider-neutral
schema remains unchanged and performs the independent local validation. Raw mappings
never cross the typed LLM boundary.

The real adapter rejects `FLOOR_PLAN_PROPOSAL` and `PATCH_PROPOSAL` before network I/O.
It receives neither revision nor World Model data, has no tools, and has no repository,
policy, editing, validation-bypass, authorization, or commit capability. Configuration
is explicit and credential-free; the SDK reads credentials from the deployment secret
channel. Provider failures use stable sanitized errors. The default factory still uses
`RuleBasedRequirementParser`, so importing or running the normal application does not
initiate model traffic.

## Agent Evaluation boundary: Task 6.2

Evaluation is a read-only orchestration layer:

```text
Scenario(input requirement, expected intent, expected constraints)
  -> injected Requirement Agent
  -> injected FloorPlan Agent
  -> injected Patch Generator
  -> DetachedPatchValidator(patch copy + full Validator)
  -> exact per-stage observations + aggregate metrics
```

The required metrics are binary scenario aggregates with exact counts and rates:
intent extraction accuracy, plan validity, and patch validation success rate. Stage
contract failures are structured and deterministic. Known planning/editing errors are
reported by code/path; unexpected implementation errors propagate rather than being
hidden by a broad exception.

`DetachedPatchValidator` checks model/revision binding and protected paths, applies the
proposal with an injected `PatchEngine` to a defensive revision copy, advances only the
candidate revision, and invokes the injected full `Validator`. For valid candidates it
also derives entity impact from before/after JSON and rejects false affected-ID metadata.
It has no repository dependency and cannot commit; a successful evaluation is evidence
that a proposal passed the current validation policy, not a new world revision.

## Planning evaluation boundary: Phase 7 Task 7.2

Planning evaluation extends the evaluation package without changing the existing
`EvaluationRunner` contract or importing `planning.solver`:

```text
same DesignIntent + already-produced FloorPlanProposal values
  -> explicit PlanningMetricContext
  -> structural/constraint observations per run
  -> all-pairs repeated-run comparison
  -> immutable PlanningMetricsReport v1
```

The context freezes a caller-selected rule-set identity, room minimums, adjacency
contact, separation gap, near-distance threshold, shared `GeometryPrecisionPolicy`,
and a maximum of 64 proposals. `PlanningThresholdSource` is a read-only structural
port, so the composition layer may project `PlanningRules` without coupling evaluation
to OR-Tools or solver modules. Reports are comparable only when their context IDs and
serialized thresholds agree.

Only exact `FloorPlanProposal` values with one identical `DesignIntent` are accepted.
Spatial metrics require v2 placement. Legacy v1 or a mixed batch returns structured
`SOLVED_LAYOUT_REQUIRED` non-applicability for all four metrics; one v2 plan returns
the first three metrics and `REPEATED_PLANS_REQUIRED` for stability. The formulas are:

- constraint satisfaction: successful atomic minimum-area, boundary, pairwise
  non-overlap, and every declared spatial-relation observation divided by their count;
- spatial efficiency: total rectangular room area divided by boundary area;
- circulation: one minus average pairwise room-center Manhattan distance divided by
  boundary width plus height (one room is `1.0`);
- stability: the mean similarity over every proposal pair, using normalized boundary
  and room geometry plus orientation, plan ID, and occurrence-normalized constraint
  bindings.

This layer deliberately evaluates optional relations as observed preferences as well
as required relations; it does not reinterpret an optional miss as invalid World
Model state. Scores are finite, normalized, timestamp-free, and standard-JSON
serializable. The evaluator never runs an Agent/provider, accesses a repository,
applies a Patch, invokes model validation, authorizes an operation, or commits. Its
report is rejected by both the typed authorization request and the gateway itself.

## Planning benchmark boundary: Final Enhancement Priority 3

The top-level `ai_parametric_architect.benchmark` package exposes immutable data/report
contracts and a read-only `BenchmarkRunner`. Importing that surface does not load
OR-Tools. The core `data.py`, `models.py`, and `runner.py` modules are provider-, solver-,
wall-clock-, randomness-, repository-, Patch-, validation-, revision-, authorization-,
and commit-neutral. Actual Agent implementations and the monotonic clock are supplied
by `composition`; `benchmark/cli.py` is only the outer adapter.

Benchmark inputs remain separate by design:

```text
dataset 1.0.0: case ID + sorted tags + untrusted requirement text
annotation set 1.0.0: case ID + expected intent + expected constraints
                         |
                         +-- bound to exact dataset ID/version and one-to-one case coverage
```

Both strict contracts reject unknown/missing fields, malformed standard JSON, duplicate
keys, non-finite values, invalid ordering/identities, and over-budget files or values.
Dataset and annotation identities have independent semantic versions and canonical
SHA-256 content digests. A digest is a reproducibility fingerprint, not a signature,
World Model identity, authorization result, or provenance proof. The loaders cap each
file at 1 MiB, datasets at 64 cases, and each requirement at 16 KiB. Before any Agent or
clock call, `BenchmarkBudget` validates case, system, trial, and total-attempt counts;
the CLI fixes those maxima at 16, 3, 4, and 192 respectively and serializes the selected
budget into the report.

Built-in composition provides three system shapes, with frozen descriptors that record
system/Agent versions, planner strategy, rules version, random seed, and execution mode;
the runner can also accept other implementations of its injected narrow ports:

- `rule-spatial-v2`: deterministic `RuleBasedRequirementParser` plus the independent
  `RuleBasedSpatialFloorPlanPlanner`;
- `cp-sat-v2`: the same deterministic parser plus `ConstraintFloorPlanPlanner`;
- `openai-cp-sat-v2`: the explicit OpenAI requirement adapter plus the same CP-SAT
  planner, additionally recording provider/model/prompt metadata.

The new rule spatial baseline is independent of OR-Tools. It reuses the equal-area
allocation rule and lays rooms in stable intent order along one bounded horizontal strip,
producing a solved `FloorPlanProposal v2` under strategy `rule-based-single-row-v1`.
The pre-existing semantic-only v1 `RuleBasedFloorPlanPlanner` and
`equal-area-stable-order-v1` pipeline are unchanged; the benchmark baseline does not
replace Task 3 Patch planning.

For every system/case/trial, the runner produces two observations:

```text
end_to_end:    dataset requirement -> injected parser -> parsed intent -> same planner
oracle_intent: annotation expected intent ---------------------------> same planner
```

The reference annotation is never supplied to the end-to-end parser. `intent_exact`
records exact agreement with the reference; the oracle track isolates planner behavior
from requirement understanding. The standard fixture deliberately places positional
relation clauses after explicit room lists: this removes room extraction as a confounder
while exposing the deterministic parser's known failure to extract spatial constraints.
The oracle track then compares planners against those same external constraints.

Intent accuracy, planning success, and plan validity include every configured attempt in
their denominators, including parse/plan failures. Constraint satisfaction, spatial
efficiency, circulation, and repeated-run stability include explicit attempt, covered-
attempt, sample, reason, and coverage fields. End-to-end spatial metrics admit only
successful plans whose parsed intent exactly matches the reference, preventing a system
from receiving a geometry score for solving a different problem. Stability groups
repeated proposals by case and counts comparison pairs. Parse/plan/total nanosecond
summaries expose minimum, nearest-rank median and p95, maximum, total, and coverage;
`oracle_intent` has no parse timing.

The serialized report is an allowlist, not a transcript. It retains artifact IDs,
versions/digests, budget and metric context, bounded declared system metadata, aggregate metrics,
case/system/trial keys, boolean outcomes, proposal SHA-256 digests, timing, and known
failure `stage/code/path`. It omits raw requirements, expected reference values, typed
intent/proposal objects, provider output/messages, prompts, exception text/details, and
credential fields. Allowlisted IDs/model/context values are caller-declared metadata,
not a secret channel, and operators must not place secrets there. The default CLI composes
only the first two offline systems. Supplying
`--openai-model` explicitly adds the third and lets the SDK obtain credentials from
`OPENAI_API_KEY`; no real-network benchmark result is claimed by this documentation.

`BenchmarkReport`, reference annotations, and all planner proposals remain detached
evidence. Neither the runner nor CLI turns them into an `AgentPatchCommitRequest`, and
the authorization gateway rejects them. Priority 3 therefore leaves the existing model
validation, revision CAS, authorization policy, affected-ID verification, audit, and
commit boundaries unchanged.

## Observable Agent Trace boundary: Task 6.3

`AgentTraceRecorder` accepts observable JSON values, computes deterministic canonical
UTF-8 JSON HMAC-SHA-256 digests through an injected `TenantTraceHasher`, and immediately
discards content. The HMAC input includes a protocol label, tenant identity, and a
distinct input/output domain. An `AgentTrace` contains only schema version, trace ID,
Agent name/version, tenant/key/algorithm identifiers, input/output digests,
injected-clock UTC timestamp, and ordered `ToolCallMetadata`. The secret key is never
stored in the trace. Tool metadata is restricted to sequence, registered tool name,
and succeeded/failed/rejected status.

Trace values cannot contain prompts, inputs/outputs, arguments/results, error text,
rationale, reasoning, or chain-of-thought. The trace package has no dependency on LLM
providers, application services, editing, repositories, transport, geometry, or vendor
SDKs. Traces are observability artifacts, not authoritative model state. Their digests
support correlation and integrity checks only; they are not anonymization or privacy
protection and remain subject to access control, tenant isolation, and retention rules.

The cross-layer acceptance test injects the Mock through all three LLM adapters and
existing Agents, evaluates the resulting Patch using complete detached validation,
records content-free traces, and only then passes the proposal separately to the trusted
EditingService. This demonstrates composability without granting the provider commit
authority or introducing a second world-state source.

## BIM/IFC boundary

IFC is a derived export through a read-only `ModelExporter` port. Stable internal
IDs, floor ownership, local placement, host relationships, wall dimensions, and
opening parameters are retained from the first schema. IFC GlobalIds and property
sets remain mapping metadata, never an alternative geometry source.

## Test strategy

- Contract tests cover accepted and rejected JSON fixtures.
- Unit tests cover every geometry predicate and validation issue code.
- Renderer tests parse XML and test determinism rather than relying on a large
  brittle snapshot.
- Render IR value/projector tests cover immutability, deterministic order, Z-up
  coordinates, bounds, floor filtering, finite derived values, and input non-mutation.
- Render IR API tests cover the complete validation gate and structured floor/no-geometry
  errors; a golden integration test keeps the frontend fixture equal to projector output.
- Frontend tests cover exact contract admission, reference and resource-budget rejection,
  scene mapping, untrusted names as text, same-origin loading, and deduplicated resource
  disposal.
- Integration tests execute example JSON through validation and SVG rendering.
- Architecture tests guard forbidden dependency directions, confine Three.js to the
  frontend, and prevent protected layers from depending on Render IR.
- Patch tests cover JSON Pointer escapes, object/array semantics, failure atomicity,
  revision conflicts, JSON-only state, compensating undo/redo, and audit ordering.
- Intent contract tests cover both room representations, packaged Schema resources,
  and exact agreement between Schema enums/limits and domain values.
- Intent unit tests cover immutable models, finite values, semantic references,
  deterministic issue ordering, and validator non-mutation.
- Agent tests cover protocol conformance, deterministic delegation, exact input
  preservation, structured dependency-contract failures, frozen state, and forbidden
  dependency directions.
- Architecture-planner tests cover immutable Plan JSON round-trips, stable allocation,
  exact area totals, orientation/constraint preservation, Plan-to-Patch routing,
  non-mutation, composition, and the complete validation/revision commit path.
- Constraint-reasoning tests cover strict immutable Plan serialization, conservative
  known/unknown mappings, stable candidate ordering, Agent contracts, non-mutation,
  provider-neutral ports, forbidden dependencies, and validation-error integration.
- Patch-generator tests cover request/revision binding, provider contract failures,
  affected-entity integrity, idempotent no-change, pipeline ordering, non-mutation,
  application-policy rechecks, validation/commit integration, and audit propagation.
- LLM-adapter tests cover the closed typed output union, exact-kind/subclass rejection,
  deterministic prompts, Mock exhaustion/order, Agent-port composition, and forbidden
  write/provider-SDK dependencies.
- Evaluation tests cover strict Scenario round-trips, all three required metrics,
  structured stage failures, unexpected-error propagation, full detached validation,
  affected-ID integrity, non-mutation, and no repository/commit capability.
- Planning-metric tests cover explicit threshold contexts, all four normalized scores,
  legacy/non-repeated non-applicability, all-pairs stability, deterministic JSON,
  CP-SAT repeated-run comparability, non-mutation, and authority-neutral dependencies.
- Benchmark tests cover strict separate artifacts, digest stability, exact annotation
  coverage, preflight budgets, both tracks and all-attempt denominators, metric/timing
  coverage, independent rule/CP-SAT systems, offline-default CLI behavior, report
  redaction, no OR-Tools top-level import, and rejection at authorization/commit boundaries.
- Agent-trace tests cover canonical tenant/domain HMAC, key rotation, strict safe metadata,
  UTC normalization, content/chain-of-thought exclusion, trace/audit correlation, clock
  injection, immutability, and dependency rules.
- Security regressions cover non-standard JSON, finite overflow, complexity and body
  budgets, malicious authorization attempts, forged identity metadata, tenant/domain
  HMAC isolation, and concurrent revision initialization.
