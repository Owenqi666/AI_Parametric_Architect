# Showcase Guide

This showcase demonstrates three separate capabilities without weakening the project's
authority boundaries:

1. deterministic replay of requirement-to-intent-to-CP-SAT planning;
2. read-only Three.js visualization of a validated JSON World Model; and
3. local inspection of a versioned planning benchmark report.

The browser never commits geometry. The planning view shows detached proposals, while the
World Model view shows a separate read-only Render IR projection of an authoritative JSON
revision.

## One-command launch

From the repository root:

```bash
make showcase
```

The command runs `scripts/run_showcase.sh`, which:

- verifies `uv`, `node`, and `npm` are available;
- requires Node.js 22.13.0 or newer;
- installs from the lockfiles on a cold start, or verifies the existing dependency tree before
  offline reuse;
- verifies Python is at least 3.12 and lower than 3.14;
- starts FastAPI at `http://127.0.0.1:8000`; and
- starts the Studio at `http://127.0.0.1:3000`.

Press `Ctrl+C` in the launch terminal to stop both processes.

The application is offline by default: it loads same-origin bundled JSON artifacts and does
not configure an OpenAI provider. A cold dependency installation can still require access to
Python and npm package registries. Prime the locked dependency caches before using the demo in
an air-gapped environment.

Set `SHOWCASE_FORCE_INSTALL=1` only when you intentionally want to resynchronize both dependency
environments from their lockfiles. Normal repeat launches verify the existing Python environment
offline and reuse a valid `frontend/node_modules` tree.

To use different local ports:

```bash
SHOWCASE_BACKEND_PORT=8010 SHOWCASE_FRONTEND_PORT=3010 make showcase
```

The script also accepts `SHOWCASE_BACKEND_HOST` and `SHOWCASE_FRONTEND_HOST`. Binding beyond
loopback does not make this prototype safe for public exposure; transport authentication,
tenant isolation, reverse-proxy limits, and deployment hardening remain external requirements.

## Product areas

| Route | Purpose | Authority posture |
| --- | --- | --- |
| `/` | Design Studio with three curated planning scenarios | Detached proposal replay only |
| `/benchmark` | Benchmark Lab for the bundled report or a local report import | Detached evidence only |
| `/world-model` | Searchable read-only Three.js World Model explorer | Derived view of JSON revision |
| `/architecture` | Trust categories and mandatory write-path explanation | Documentation only |

Useful backend checks:

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/v1/capabilities
```

The default capability response is:

```json
{
  "openai_requirement_parser_available": false,
  "benchmark_live_mode_available": false,
  "live_planning_preview_available": false
}
```

These values are explicit trusted deployment declarations. They are not inferred from an API
key or other environment variable.

## Design Studio walkthrough

The Studio loads
`frontend/public/examples/planning-showcase.preview-1.0.0.json`. That artifact was produced by
the typed recorded-Mock requirement path and the real deterministic CP-SAT planner. Clicking
**Run planning** animates a local replay; it does not call a provider or execute a new solver
run in the browser.

The generator uses a showcase-only objective profile that disables compactness and circulation
objective terms so the five-room recording proves optimality quickly. Hard constraints remain in
force, and `PlanningMetricsEvaluator` scores circulation separately. Do not interpret the
scenario circulation metric as an objective optimized by this replay profile; the bundled
benchmark uses the standard planning-rule configuration.

The **Offline deterministic** and **Recorded showcase replay** selections both use the same
bundled evidence. Their presentation timing differs, but neither is a live network mode.

### South-facing family house

The requirement requests 120 m², three bedrooms, a living room, a kitchen, south orientation,
and required kitchen-to-living adjacency. The bundled result is a detached
`FloorPlanProposal 2.0.0` produced by `cp-sat-rectilinear-v1`.

Select a room rectangle to inspect its plan ID, solved dimensions, orientation, and applicable
constraints. The banner and inspector deliberately label these coordinates as advisory.

### Compact apartment

The 72 m² apartment scenario includes bedroom, bathroom, living, and kitchen spaces. Its
evidence compares `rule-spatial-v2` and `cp-sat-v2` on the same typed intent. The comparison is
useful for discussing metric tradeoffs, not choosing authoritative geometry.

### Conflicting spatial constraints

The third scenario requires the bedroom to be both north and south of the bathroom. The typed
intent is valid, but its required constraints are jointly infeasible. CP-SAT fails closed with:

```json
{
  "stage": "plan",
  "code": "PLANNING_SOLVER_FAILED",
  "path": "/problem"
}
```

No proposal, fallback geometry, or metric evidence is created.

### Curated-input behavior

This is a finite recorded showcase. If the requirement text no longer exactly matches the
selected scenario, the Studio returns `SHOWCASE_INPUT_NOT_RECORDED`. Restore the text with
**Reset** or choose another scenario. The UI does not pretend that arbitrary edited text was
parsed or solved.

### Proposal versus World Model

Use the viewport tabs to compare two explicitly different modes:

- **Proposal** displays a detached planning artifact that is not committed.
- **World Model** displays a read-only scene projected from the separate validated sample
  `mdl_showcase_house`, revision 7.

There is no code path from the proposal preview into the World Model projector. The World Model
sample is not a realization of the selected proposal.

## World Model Explorer

The explorer loads `frontend/public/examples/showcase-house.render-ir.json`, a Render IR 1.0.0
derivative of `examples/showcase_house.json`. The sample contains two floors and 26 render
objects: 7 rooms, 13 walls, 2 doors, and 4 windows.

Try the following:

- orbit, pan, zoom, and switch camera mode;
- change floor visibility;
- select an object in the scene or entity navigator;
- search by entity ID or name; and
- inspect source model ID, revision, schema, floor, and geometry kind.

The scene is disposable. It has no Patch, repository, authorization, revision, or commit client.
SVG and Render IR downloads are debugging derivatives, not revision snapshots.

## Benchmark Lab

The Lab admits the bundled
`frontend/public/examples/planning-core.benchmark-report-1.0.0.json` under a strict browser-side
contract. It provides:

- end-to-end and oracle-intent tracks;
- aggregate metric and runtime summaries;
- per-case attempt outcomes and proposal digests; and
- stable, redacted failure distributions.

Use **Import report** to inspect another local BenchmarkReport 1.0.0 file. Import is bounded,
validated, and frozen in memory; the Lab does not upload it or write World Model state.

See [BENCHMARK_METHODOLOGY.md](BENCHMARK_METHODOLOGY.md) before interpreting scores.

## Optional OpenAI use

The default Studio has no live planning endpoint and this release exposes no **OpenAI live**
control, regardless of capability declarations. The capability response is diagnostic/future
discovery metadata; it is not a UI switch. An API key alone changes no flag. A future live mode
must first implement a strict detached-preview endpoint, local validation, resource budgets,
tests, and a dedicated security review.

The real adapter can be composed explicitly in Python without granting it a write port:

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
intent = requirement_agent.run("Create a 120 sqm three bedroom house")
proposal = create_architecture_planner_agent().run(intent)
```

Set `OPENAI_API_KEY` through a managed environment/secret channel and set `OPENAI_MODEL` to an
approved Structured Outputs model snapshot before running that code. The provider receives only
the requirement and returns only a locally validated `DesignIntent`; the local CP-SAT result is
still detached. This snippet is not wired to the Studio and performs no Patch or commit.

The explicit real-network benchmark entry point is:

```bash
export OPENAI_API_KEY='managed-secret-value'
uv run ai-architect-benchmark \
  benchmarks/datasets/planning-core-1.0.0.json \
  benchmarks/annotations/planning-core-reference-1.0.0.json \
  planning-benchmark-openai.json \
  --trials 2 \
  --openai-model '<approved-structured-output-model-snapshot>'
```

This adds `openai-cp-sat-v2`, marked `real_nondeterministic`, to the two offline systems. The
network adapter performs requirement-to-`DesignIntent` extraction only. CP-SAT still produces a
detached proposal, and no Patch or commit occurs. Use an approved model snapshot and apply
egress, cost, rate, credential, logging, retention, and vendor-review controls.

## Regenerating bundled artifacts

For maintainers:

```bash
uv run python scripts/generate_world_model_showcase.py
uv run python scripts/generate_showcase_fixtures.py
```

The second command reruns the benchmark and overwrites its report. Proposal results are
deterministic under the pinned environment, but measured monotonic runtimes legitimately change
between runs. Review all generated diffs and rerun the contract, architecture, and security
tests before accepting an update.

## Browser E2E acceptance run

The release candidate was exercised against the one-command local server in a real browser with
the committed offline fixtures. The acceptance run verified:

- the family-house replay exposes typed `DesignIntent` and all three detached-Proposal warnings;
- the conflict scenario retains typed intent, returns `PLANNING_SOLVER_FAILED`, and creates no
  proposal;
- edited, unrecorded text fails closed with `SHOWCASE_INPUT_NOT_RECORDED`;
- Benchmark Lab admits the bundled versioned report and switches between end-to-end and
  oracle-intent tracks;
- the World Model WebGL scene loads, floor filtering and camera Fit work, and entity selection
  updates the structured inspector;
- route changes release the viewer without an uncaught browser error; and
- the Studio remains usable at 390, 768, 1024, 1366, and 1512 pixel viewport widths.

The browser console finished with no errors or warnings on a clean run. The four checked-in files
under `docs/images/` are captures from that application run, not composed mockups. Contract and
component automation remains in Vitest; this repository does not add a separate Playwright or
Cypress dependency.

## Troubleshooting

### A required command is missing

Install `uv`, Node.js 22.13.0 or newer, and npm. The launch script reports the first missing
command and exits.

### A port is already in use

Stop the process using port 8000 or 3000, or launch with the port overrides shown above. Keep the
frontend and backend values in the same invocation so the development proxy targets the correct
API origin.

### The capability diagnostic endpoint is unavailable

The Studio does not request this endpoint and continues to use bundled offline evidence. To
diagnose backend configuration separately, check both endpoints directly:

```bash
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/v1/capabilities
```

The default false capability response is healthy behavior, not an OpenAI configuration error.

### A bundled artifact is rejected

Do not bypass the parser. Restore the generated JSON from a trusted checkout or regenerate it
with the repository script, then run the relevant tests. The browser intentionally rejects
unknown fields, wrong versions, malformed references, non-finite numbers, and over-budget data.

### The 3D canvas is blank

Check the browser console for Render IR admission or WebGL errors. Confirm
`/examples/showcase-house.render-ir.json` returns JSON from the frontend origin. Hardware or
browser WebGL policy may still prevent rendering even when the artifact is valid.

### An edited requirement fails immediately

This is expected for inputs outside the three curated recordings. Reset the selected scenario.
For real parsing, use the opt-in Python adapter or benchmark CLI under a reviewed deployment;
the current Studio does not expose arbitrary live input.
