# AI Parametric Architect Studio

> A safe, constraint-aware world-model planning environment for architectural AI.

AI Parametric Architect Studio converts natural-language requirements into typed architectural intent, produces deterministic floor-plan proposals with OR-Tools CP-SAT, evaluates those proposals, and visualizes validated world-model revisions through a read-only Three.js interface.

The system is built around one rule:

> **Persisted JSON revisions are the only authoritative world model.**

LLM responses, solver layouts, benchmark reports, Render IR, SVG output, and Three.js scenes are derived or advisory artifacts. None of them can directly mutate or commit authoritative geometry.

---

## Overview

```mermaid
flowchart TD
    A["Natural-language requirement<br/>untrusted input"]
    B["Typed DesignIntent<br/>advisory"]
    C["CP-SAT planner<br/>deterministic"]
    D["Detached FloorPlanProposal<br/>not committed"]
    E["Evaluation and benchmark<br/>evidence only"]
    F["PatchProposal<br/>untrusted candidate"]
    G["Authorization policy"]
    H["Schema, semantic, and geometry validation"]
    I["CAS revision commit<br/>authoritative JSON"]
    J["Trusted audit event"]
    K["Render IR<br/>read-only"]
    L["Three.js scene<br/>derived view"]

    A --> B
    B --> C
    C --> D
    D --> E
    D -. "future realization contract" .-> F
    F --> G
    G --> H
    H --> I
    I --> J
    I --> K
    K --> L
```

This separation makes the system easier to validate, reproduce, audit, benchmark, and secure than a direct LLM-to-geometry pipeline.

---

## Key Capabilities

- JSON-first authoritative world model
- JSON Schema Draft 2020-12 validation
- semantic and cross-reference validation
- Shapely-based geometry validation
- deterministic SVG rendering
- immutable Render IR 1.0.0
- read-only Three.js visualization
- JSON Patch with `add`, `remove`, and `replace`
- immutable revision history with compare-and-swap
- compensating undo and redo
- trusted audit identity
- typed Requirement, Planning, Reasoning, and Patch Generator agents
- deterministic OR-Tools CP-SAT floor-plan planning
- detached planning metrics
- rule-based and CP-SAT benchmark systems
- opt-in OpenAI Responses adapter for `DesignIntent` extraction only
- tenant-scoped HMAC trace correlation
- offline showcase application

---

## Project Status

**Current maturity**

> Production-oriented AI Agent Framework Prototype with constraint-aware detached planning, evaluation, and read-only 3D visualization.

The project is not a production-ready public service. It does not claim:

- building-code compliance
- automatic architectural correctness
- authoritative AI-generated geometry
- durable multi-process persistence
- public-internet readiness
- automatic proposal realization
- IFC or DXF export
- production RAG
- unrestricted multi-agent autonomy

---

## Product Workspaces

### Design Studio

The Design Studio presents recorded deterministic scenarios and exposes the observable planning stages:

```text
Requirement
  -> DesignIntent
  -> CP-SAT planning
  -> Detached FloorPlanProposal
  -> Planning metrics
```

Every proposal preview is explicitly labelled:

- **Detached Proposal**
- **Not committed to World Model**
- **Advisory planning output**

The current Studio release does not expose a live OpenAI planning control or a live planning-preview endpoint.

### Detached Planning Sandbox

The sandbox renders proposal-local room rectangles, room areas, orientations, and spatial constraints through a dedicated frontend contract.

It does not call `WorldModelRenderIRProjector`, create patches, or present proposal geometry as committed world-model state.

### Benchmark Lab

The Benchmark Lab compares planning systems across two tracks:

- `end_to_end`: requirement text → parser → planner
- `oracle_intent`: reference intent → planner

Built-in systems:

- `rule-spatial-v2`
- `cp-sat-v2`
- `openai-cp-sat-v2` when explicitly enabled through the benchmark CLI

Reported metrics include:

- exact intent accuracy
- planning success
- plan validity
- constraint satisfaction
- spatial efficiency
- circulation proxy
- repeated-run stability
- parse, planning, and total runtime

### World Model Explorer

The World Model Explorer uses the authoritative rendering path:

```text
Validated JSON revision
  -> Render IR 1.0.0
  -> strict browser admission
  -> read-only Three.js scene
```

Supported interactions include:

- isometric and top views
- orbit and zoom
- fit-to-model
- floor visibility
- entity tree and search
- entity selection and inspection
- stable `entity_id` mapping
- Render IR and SVG debugging downloads

The viewer cannot generate patches, access the repository, authorize operations, or commit revisions.

### Architecture and Safety

This workspace explains:

- why the LLM cannot directly edit geometry
- why solver output is not authoritative
- why evaluation is not authorization
- why Render IR is read-only
- how compare-and-swap rejects stale writes
- how trusted audit identity is separated from proposal text

---

## Quick Start

### Requirements

- Python 3.12 or 3.13
- [`uv`](https://docs.astral.sh/uv/)
- Node.js 22.13.0 or newer

### Start the showcase

```bash
./scripts/run_showcase.sh
```

The launcher starts:

- frontend: `http://127.0.0.1:3000`
- FastAPI backend: `http://127.0.0.1:8000`

Press `Ctrl+C` to stop both processes.

The default showcase requires no API key, database, or manually generated fixture. A first-time dependency installation may still require internet access to package registries.

---


## Backend API

Start FastAPI manually:

```bash
uv sync --dev --locked
uv run uvicorn ai_parametric_architect.backend.api:app --reload
```

Available endpoints:

- `GET /health`
- `GET /v1/capabilities`
- `POST /v1/models/validate`
- `POST /v1/models/render/svg`
- `POST /v1/models/render/ir`
- `POST /v1/models/render/ir?floor_id=<floor-id>`

### Validate a model

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/models/validate   -H 'Content-Type: application/json'   --data-binary @examples/valid_simple_house.json
```

### Render SVG

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/models/render/svg   -H 'Content-Type: application/json'   --data-binary @examples/valid_simple_house.json   --output simple_house.svg
```

### Generate Render IR

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/models/render/ir   -H 'Content-Type: application/json'   --data-binary @examples/valid_simple_house.json   --output simple-house.render-ir.json
```

The same deterministic read path is available through the CLI:

```bash
uv run ai-architect validate examples/valid_simple_house.json
uv run ai-architect render-svg examples/valid_simple_house.json simple_house.svg
```

---

## Core Architecture

### Authoritative World Model

The authoritative state is a versioned JSON document inside an immutable revision envelope.

```text
Transport or library input
  -> StrictJsonTreeGuard
  -> JSON Schema
  -> ModelComplexityPolicy
  -> semantic and reference rules
  -> finite geometry predicates
  -> validated model
```

The strict JSON boundary rejects:

- `NaN` and infinity
- non-string object keys
- tuples, sets, bytes, datetimes, enums, and custom objects
- cyclic containers
- aliased mutable containers
- excessively deep trees

### Editing and Revision Control

```text
Immutable revision snapshot
  -> apply JSON Patch to a defensive copy
  -> enforce protected paths and operation budgets
  -> increment application-owned revision
  -> complete validation
  -> independently derive affected entities
  -> compare-and-swap commit
  -> append trusted audit event
```

The supported JSON Patch subset is:

- `add`
- `remove`
- `replace`

Undo and redo are compensating commits. Historical revisions are never overwritten.

The built-in repository is thread-safe but process-local and in-memory. It is intended for development and prototype use.

### Agent Write Boundary

Agent-generated proposals cannot write directly to the repository.

```text
PatchProposal
  -> AgentAuthorizationGateway
  -> deterministic intent and operation policy
  -> patch a defensive copy
  -> complete validation
  -> affected-entity verification
  -> CAS commit
  -> trusted audit
```

Evaluation reports, benchmark reports, solver scores, and frontend state are not valid authorization inputs.

---

## Constraint-aware Planning

### DesignIntent

`DesignIntent` is an immutable, provider-neutral intermediate representation containing:

- building type
- target area
- room requirements
- optional orientation
- spatial constraints

Example:

```json
{
  "building_type": "house",
  "area": 120,
  "rooms": ["living", "bedroom", "bedroom", "bedroom", "kitchen"],
  "orientation": "south",
  "spatial_constraints": [
    {
      "source_room_type": "kitchen",
      "relation": "adjacent_to",
      "target_room_type": "living",
      "required": true
    }
  ]
}
```

`DesignIntent` is not a second world model and contains no authoritative geometry.

### CP-SAT Planner

The production planning composition uses a pinned OR-Tools CP-SAT solver:

```text
DesignIntent
  -> PlanningRules
  -> integer-grid CP-SAT model
  -> detached FloorPlanProposal v2
```

The solver models:

- room `x`, `y`, `width`, and `height`
- boundary containment
- minimum room dimensions and areas
- non-overlap
- exact shared-edge adjacency
- separation gaps
- proximity
- cardinal relative-position constraints
- orientation preferences
- bounded optimization objectives

The solver runs with:

- one worker
- fixed seed
- stable variable order
- deterministic-time budget
- bounded integer objective coefficients
- `OPTIMAL`-only acceptance

`FEASIBLE`, `UNKNOWN`, `MODEL_INVALID`, and `INFEASIBLE` fail closed with a structured error.

### Proposal Is Not Realization

A `FloorPlanProposal v2` contains solved rectangles but remains advisory.

It cannot:

- enter the authoritative Render IR path
- create committed walls or rooms
- modify a revision
- act as authorization evidence

Promoting a selected proposal into authoritative geometry requires a future realization contract, authorization review, full validation, and CAS commit.

---

## Optional OpenAI Adapter

The project includes an opt-in OpenAI Responses adapter under `infrastructure/llm`.

Its only supported live responsibility is:

```text
Natural-language requirement
  -> OpenAI Responses API
  -> strict structured output
  -> local JSON decoding
  -> IntentValidator
  -> immutable DesignIntent
```

It cannot generate or commit:

- authoritative geometry
- `FloorPlanProposal`
- `PatchProposal`
- revisions
- repository writes

It receives no world model, revision, repository handle, patch engine, or commit service.

Example:

```python
import os

from ai_parametric_architect.composition import (
    create_architecture_planner_agent,
    create_openai_requirement_agent,
)
from ai_parametric_architect.infrastructure import OpenAIProviderConfig

requirement_agent = create_openai_requirement_agent(
    OpenAIProviderConfig(model=os.environ["OPENAI_MODEL"])
)

intent = requirement_agent.run(
    "Design a 120 sqm south-facing family house with three bedrooms."
)

proposal = create_architecture_planner_agent().run(intent)
```

Credentials are read by the OpenAI SDK from `OPENAI_API_KEY`. Keys are not stored in prompts, configuration objects, errors, or traces.

The default application, FastAPI routes, showcase, and benchmark systems remain deterministic and offline unless explicitly configured otherwise.

---

## Planning Benchmark

Run the default offline benchmark:

```bash
uv run ai-architect-benchmark   benchmarks/datasets/planning-core-1.0.0.json   benchmarks/annotations/planning-core-reference-1.0.0.json   planning-benchmark-report.json   --trials 2
```

To explicitly include the OpenAI parser:

```bash
uv run ai-architect-benchmark   benchmarks/datasets/planning-core-1.0.0.json   benchmarks/annotations/planning-core-reference-1.0.0.json   planning-benchmark-report.json   --trials 2   --openai-model "$OPENAI_MODEL"
```

Benchmark datasets and reference annotations are separate, versioned artifacts. Reference intent is never supplied to the end-to-end parser.

Reports retain only allowlisted identifiers, aggregate metrics, timings, proposal digests, and sanitized failure codes. They do not store raw requirements, reference answers, provider messages, prompts, exception text, credentials, or hidden reasoning.

---

## Security Boundaries

Implemented controls include:

- strict JSON admission
- defensive snapshots
- model and patch complexity budgets
- finite derived-number checks
- exact affected-entity verification
- deterministic agent authorization
- trusted audit identity
- tenant-scoped HMAC-SHA-256 traces
- prompt data minimization
- response and request byte limits
- strict browser-side admission contracts
- same-origin Render IR loading
- deeply frozen browser data
- explicit proposal/world-model separation

See [`Security.md`](Security.md) for the threat model and deployment requirements.

Before public internet exposure, a deployment must still add:

- authentication and tenant isolation
- durable transactional persistence
- tamper-evident audit export
- reverse-proxy request limits
- concurrency, CPU, memory, and timeout enforcement
- solver process isolation and cancellation
- provider egress and cost controls
- CSP and production web hardening
- structured observability and SLOs
- dependency and container security controls

---

## Testing and Quality Gates

### Backend

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov=ai_parametric_architect --cov-report=term-missing
uv run coverage json -o coverage.json
uv run python scripts/verify_branch_coverage.py
```

### Frontend

```bash
cd frontend
npm ci
npm run typecheck
npm run lint
npm test
npm run build
```

Coverage includes branch measurement with a separate branch-only gate.

CI also verifies:

- Python 3.12 and 3.13
- packaged JSON Schema resources
- isolated wheel installation
- frontend type checking, linting, tests, and build
- architecture dependency rules
- deterministic proposal and rendering behavior

---

## Repository Layout

```text
src/ai_parametric_architect/
  agent_trace/       HMAC-based trace correlation
  agents/            typed Requirement, Planner, Reasoning, and Patch agents
  application/       orchestration and write-side use cases
  backend/           FastAPI adapter and public capability metadata
  benchmark/         versioned datasets, annotations, runners, and reports
  contracts/         world-model JSON Schema resources
  domain/            revisions, patches, audit, issues, and Render IR values
  editing/           strict JSON Pointer and atomic JSON Patch engine
  evaluation/        detached agent and planning evaluation
  geometry_engine/   Shapely adapter
  infrastructure/    clocks and opt-in vendor integrations
  intent/            DesignIntent Schema, models, and validation
  llm/               provider-neutral contracts, prompts, adapters, and Mock
  planning/          rule planners, CP-SAT planner, and proposal contracts
  policy/            deterministic agent authorization
  ports/             stable application and domain interfaces
  reasoning/         symbolic candidate-resolution plans
  repositories/      in-memory revision repository
  renderer/          deterministic SVG and Render IR projectors
  validation/        structural, semantic, and geometry validation

frontend/             showcase UI and strict browser admission
benchmarks/           planning datasets and reference annotations
examples/             valid and invalid world-model fixtures
tests/                unit, integration, architecture, and security regressions
```

---

## Documentation

The repository currently includes the following documentation files:

- [Detailed Architecture](architecture.md)
- [Security Model](Security.md)
- [Historical Industrial Architecture Review](Industrial_Architecture_Review.md)

The historical review is retained for traceability and should not be interpreted as the current release status.

---

## License

This repository is currently marked as proprietary. Review the license before public distribution or external contribution.
