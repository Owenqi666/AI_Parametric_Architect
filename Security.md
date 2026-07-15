# Security Model

AI Parametric Architect is a production-oriented prototype, not a finished
multi-tenant service. This document defines the security boundaries implemented by
the prototype and the controls a production deployment must add around them.

## Assets and trust boundaries

The authoritative asset is an immutable revision of the JSON world model. Plans,
LLM responses, solver proposals, evaluation reports, traces, Shapely objects, rendered
SVG, Render IR, and Three.js scenes are derived or advisory values; none of them is an
authority to mutate or commit the world model.

The main untrusted inputs are:

- HTTP and CLI JSON documents;
- patch operations and proposal metadata produced by people or agents;
- natural-language requirements and LLM suggestions;
- proposal `provenance` and `rationale` strings;
- scenario data supplied to the evaluation runner;
- Render IR JSON loaded by the browser;
- floor and entity names rendered as display text.

Authenticated application context, including `TrustedAuditIdentity` and tenant HMAC
keys, must be supplied by trusted infrastructure. It must never be reconstructed from
proposal text, LLM output, or an evaluation result.

## Mandatory write path

Every agent-originated write uses this sequence:

```text
PatchProposal (untrusted)
  -> authorization policy
  -> patch a defensive JSON copy
  -> JSON Schema + complexity + semantic + geometry validation
  -> affected-entity verification
  -> compare-and-swap revision commit
  -> trusted audit event
```

Agents and LLM providers have no repository, patch-application, validation-bypass, or
commit capability. An evaluation success is an observation only and is deliberately
not accepted by the authorization gateway as a commit credential.

Visualization is entirely on the read side. Render IR, scene selection, camera/floor
visibility, and WebGL state are not `AgentPatchCommitRequest` values and cannot enter the
authorization gateway or revision repository.

## Strict JSON boundary

`StrictJsonTreeGuard` is applied before schema, geometry, editing, and evaluation
work. Accepted values are exactly the JSON value tree: objects with string keys,
arrays, strings, booleans, null, integers, and finite floating-point numbers. The
guard rejects, among other values:

- `NaN`, positive infinity, and negative infinity;
- `datetime`, `set`, `tuple`, bytes, enums, and custom objects;
- non-string object keys;
- cyclic or aliased mutable containers and excessively deep trees.

JSON decoding also rejects non-standard `NaN` and `Infinity` tokens. Validation does
not normalize or mutate a document. Revision initialization validates a defensive
snapshot and commits that same snapshot, so mutation of the caller-owned object
during validation cannot change the committed state.

## Geometry and computation budgets

`ModelComplexityPolicy` centralizes limits for entity count, total polygon vertices,
coordinate magnitude, room area, wall length, and patch operation count. These are
application safety limits, not building-code claims. Deployments may inject a stricter
policy but must use one policy consistently at every relevant entry point.

Every derived geometry and rendering number must remain finite. Models that exceed a
budget fail with a stable machine-readable issue before expensive geometry work.
The renderer independently refuses non-finite derived values and never emits
`NaN`/`Infinity` text. `ValidationIssue.details` is itself constrained to a defensive
standard-JSON copy, so a diagnostic cannot reintroduce a non-finite or custom value at
the response boundary.

Resource budgets reduce denial-of-service risk; they do not replace infrastructure
controls such as reverse-proxy body limits, request timeouts, concurrency limits,
process isolation, and memory/CPU quotas.

## Visualization boundary

The server projects Render IR only after the input passes strict JSON admission, JSON
Schema, complexity, semantic/reference, and geometry validation. `RenderIR 1.0.0`
retains source model/revision identity and returns a fresh standard-JSON tree, but it is
not a revision snapshot, Patch input, authorization result, or commit credential. The
projector independently refuses non-finite direct and derived coordinates.

The browser treats Render IR as untrusted data and applies the following controls:

- only same-origin sources are accepted, including after redirects, and fetch uses
  `credentials: "same-origin"`;
- declared and streamed response data is capped at 2 MiB;
- version, fields, literals, finite numbers, closed/horizontal rings, bounds, floor
  references, and opening-to-host-wall references are checked exactly;
- admission is capped at 128 floors, 10,000 render objects, and 100,000 geometry points;
- the admitted value is deeply frozen before scene construction;
- Render IR has no URL, texture, material, color, shader, or executable-content field;
  Three.js appearance is hard-coded locally;
- untrusted names remain unchanged strings and are inserted through React text nodes,
  never HTML injection APIs;
- device pixel ratio is capped at 2 to bound render-target growth.

The viewer has no raw World Model, Patch, authorization, repository, or commit client.
Teardown stops the animation loop, removes DOM listeners, disconnects the
`ResizeObserver`, disposes controls, geometries, materials, textures, renderer lists,
and the renderer, then releases the WebGL context. These controls limit accidental
resource retention but do not make a browser GPU process a trusted execution boundary.

## Constraint-solver boundary

Phase 7 Task 7.1 adds OR-Tools CP-SAT only inside `planning/solver`. Solver output is
an advisory `FloorPlanProposal v2`, never authoritative World Model geometry and never
a commit credential. The solver has no repository, Patch, application, authorization,
validation, FastAPI, LLM, Shapely, renderer, or revision dependency. OR-Tools values do
not cross this boundary.

CP-SAT output cannot directly supply authoritative Render IR or Three.js geometry. The
visualization projector accepts only a World Model document; solver placement remains a
detached Proposal until a separately authorized realization passes complete validation
and CAS commit. The existing geometry authorization allowlist has not been widened.

`PlanningRules` and `PlanningGridPolicy` centralize solver safety limits and scaling:

- maximum room count, spatial-constraint count, intent area, and coordinate magnitude;
- exact integer-grid conversion for configured lengths and conservative area rounding;
- finite positive minimum areas/dimensions/contact/gap/distance values;
- bounded integer objective coefficients with an explicit overflow check;
- one CP-SAT worker, fixed seed, disabled permutation, and deterministic-time budget.

Only an `OPTIMAL` result is accepted. `FEASIBLE`, `UNKNOWN`, `MODEL_INVALID`, and
`INFEASIBLE` results fail closed with a structured `PLANNING_SOLVER_FAILED` error;
there is no fallback that silently drops required constraints. Output construction
revalidates the provider-neutral v2 Proposal contract, including finite placement,
boundary containment, non-overlap, and declared orientation exposure.

These controls bound the model submitted by the built-in planner, but a native solver
is still a CPU/memory-intensive dependency. Production deployment must enforce process
isolation, wall-clock cancellation, concurrency quotas, and memory/CPU limits outside
the Python process. The exact dependency is pinned to `ortools==9.15.6755`; supported
deployment images must use an available CPython glibc/macOS wheel. The project does not
claim Alpine/musl or PyPy support.

Soft objective scores are preferences, not safety proofs or building-code compliance.
The current circulation term is a Manhattan center-distance proxy, and default room
minimums are planning policy only. Proposal byte stability is tested with the pinned
solver/runtime, but is not a cross-version or cross-architecture cryptographic
guarantee.

## Planning-metric boundary

Phase 7 Task 7.2 scores already-produced detached proposals. The evaluator has no
solver, provider, repository, Patch, authorization, validation, revision, or commit
dependency. It cannot turn an evaluation result into World Model authority. Both the
typed `AgentPatchCommitRequest` and `AgentAuthorizationGateway` reject a
`PlanningMetricsReport`; only the mandatory write path above can create a revision.

Metric thresholds and precision are supplied through an explicit immutable
`PlanningMetricContext`. Comparisons are meaningful only under the same serialized
context, and deployments must bind context IDs to trusted configuration rather than
accepting an LLM-declared identity. Input run count is capped at 64, all scores are
checked finite and normalized, and the report contains no timestamp or model
mutation. A semantic-only v1 Proposal yields a structured not-applicable result rather
than invented coordinates; stability requires at least two runs of one exact Intent.

These metrics are ranking and regression signals, not safety proofs. In particular,
the circulation score is a room-center distance proxy, the constraint score also
observes optional preferences, and the stability score is a normalized comparison,
not a cryptographic reproducibility guarantee. None establishes code compliance,
accessibility, egress safety, geometric validity of authoritative World Model data,
or authorization to commit.

## Agent authorization

`AgentAuthorizationGateway` accepts only an explicit typed commit request containing a
`DesignIntent` and `PatchProposal`. The injected deterministic policy verifies:

- intent and planning-record alignment;
- model and base-revision binding;
- allowed operation types and exact allowed paths;
- allowed entity types and affected-entity declarations;
- exact semantic operations expected for the authorized planning capability.

Authorization does not replace model validation. A policy-authorized proposal still
passes through the complete patch, validation, impact verification, and CAS pipeline.

## Trusted audit identity

Every repository write requires a `TrustedAuditIdentity` on a separate trusted
channel. Audit entries record:

- `actor_id` and `actor_type` (`human`, `agent`, or `system`);
- `agent_version` for an agent actor;
- `trace_id` for correlation;
- append-only revision transition metadata.

Proposal `provenance` and `rationale` are serialized as
`untrusted_provenance` and `untrusted_rationale`. They cannot assert a human identity.
Patch proposals that use reserved human-identity provenance forms are rejected, but
this text-level check is defense in depth; authentication remains the responsibility
of the trusted identity channel.

The built-in repository is in-memory and process-local. It provides lock-protected
atomicity for this prototype but not durable, tamper-evident audit storage. A production
adapter must atomically persist the revision, head, undo/redo state, and audit event,
and should forward audit events to access-controlled append-only storage.

## Trace security

Agent input and output fingerprints use HMAC-SHA-256 with a tenant-specific secret,
explicit tenant/key identifiers, and separate input/output domains. Domain separation
prevents the same observable value from receiving the same digest in different trace
roles. Keys must be injected from a secret manager, rotated by `key_id`, never logged,
and never stored in an `AgentTrace`.

Trace digests are for correlation and integrity checks only. They are **not
anonymization or privacy protection**: low-entropy inputs can still be guessed by an
actor who possesses the tenant key, and metadata itself may be sensitive. Traces must
therefore follow normal access control, retention, tenant isolation, and deletion
policies. Prompt text, input/output content, tool arguments/results, rationale,
reasoning, and chain-of-thought are prohibited from trace records.

## Prompt data minimization

The Patch prompt does not expose the complete world model. It contains only model and
revision binding plus an allowlisted planning context: the owned planning record,
existing room-slot semantic fields needed by the current capability, and extension
presence. Authoritative World Model geometry, arbitrary metadata, secrets, and
unrelated extension content are excluded. A detached v2 proposal may contain its own
candidate rectangles; those values remain untrusted suggestions and do not widen Patch
or commit authority. A future provider adapter must preserve or further restrict this
projection.

## Known limitations and deployment requirements

Before exposing the prototype to untrusted internet traffic, a deployment must add:

- authentication, authorization, and tenant isolation at the transport boundary;
- durable transactional revision storage and tamper-evident audit export;
- managed HMAC key generation, storage, rotation, revocation, and deletion;
- request-body, rate, timeout, concurrency, CPU, and memory enforcement;
- native solver isolation, cancellation, dependency scanning, and platform-compatible wheels;
- browser CSP/security headers, static-asset integrity controls, and WebGL/GPU resource isolation;
- TLS, security headers, dependency and container scanning, and incident monitoring;
- a persistence migration and recovery strategy;
- threat-model review of any future network LLM provider and its data-retention terms.

The same-origin client check does not replace server-side authentication, authorization,
CSP, or resource quotas, and the current viewer does not make `/v1/models/render/ir`
safe for public internet exposure. Render IR v1 omits stairs and represents door/window
openings as panels without CSG; consumers must not infer that an undisplayed stair is
absent from the World Model or that a wall has been authoritatively cut.

Do not connect a real LLM, broaden an authorization allowlist, or add a new agent write
capability without a dedicated security review and adversarial regression tests.
