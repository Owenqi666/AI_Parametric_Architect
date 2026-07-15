# 60–90 Second Recording Script

Target duration: approximately 84 seconds.

The script is written for one continuous screen recording with narration. It demonstrates the
product and its boundaries; it does not imply that the browser is executing a live provider or
committing geometry.

## Preflight, before recording

1. From the repository root, run:

   ```bash
   make showcase
   ```

2. Wait until the terminal prints both local URLs and the Studio has loaded at
   `http://127.0.0.1:3000`.
3. Keep browser zoom and window size stable.
4. Confirm the first Design Studio scenario is **South-facing family house**.
5. Confirm `GET /v1/capabilities` is healthy with all three diagnostic values false. These
   booleans do not enable a Studio live mode in this release.
6. Close unrelated tabs, notifications, terminals, and any UI containing credentials.

## Shot list and narration

### 0–8 seconds — Establish the product

**Action:** Show the Design Studio header, execution mode, pipeline, and detached-proposal banner.

**Narration:**

> “AI Parametric Architect turns requirements into typed, constraint-aware planning evidence.
> This build is offline by default, and only persisted JSON revisions are authoritative.”

### 8–23 seconds — Run the family-house replay

**Action:** Keep **South-facing family house** selected. Click **Run planning**. As the pipeline
completes, select the kitchen or living-room rectangle and point to the adjacency entry in the
inspector.

**Narration:**

> “This recorded typed intent preserves 120 square metres, three bedrooms, south orientation,
> and required kitchen-to-living adjacency. CP-SAT produced this detached proposal; the
> coordinates are advisory and not committed.”

### 23–35 seconds — Show a measured planner tradeoff

**Action:** Select **Compact apartment**. Point to the evidence rail and its
**Baseline vs CP-SAT** label.

**Narration:**

> “On the same 72-square-metre apartment intent, both planners satisfy the measured constraints.
> The baseline records 100 percent spatial efficiency, while CP-SAT records an 82 percent
> circulation proxy. These are comparison signals, not building-code proofs.”

The UI rounds the stored CP-SAT circulation value `0.8198198198` to `82.0%`.

### 35–47 seconds — Demonstrate fail-closed behavior

**Action:** Select **Conflicting spatial constraints**, then click **Run planning**. Pause on the
structured failure showing `PLANNING_SOLVER_FAILED` and **No proposal created**.

**Narration:**

> “If the bedroom is required to be both north and south of the bathroom, the typed intent reaches
> the solver but is infeasible. The system fails closed: no fallback geometry and no metric evidence
> are fabricated.”

### 47–61 seconds — Separate proposal from World Model

**Action:** Use the top navigation to open **World Model**. Orbit the two-floor scene, select one
entity in the navigator, and point to model ID `mdl_showcase_house` and revision 7.

**Narration:**

> “This is a separate validated JSON revision, projected through Render IR into a disposable
> Three.js scene. Selection and camera state are read-only; the viewer has no Patch, repository,
> authorization, or commit client.”

### 61–75 seconds — Show benchmark evidence

**Action:** Open **Benchmark Lab**. Select the **Oracle intent** tab. Point first to the CP-SAT
constraint score, then to runtime evidence or the per-case matrix.

**Narration:**

> “The bundled benchmark separates end-to-end parsing from an oracle-intent planner track. Across
> eight cases and two trials, CP-SAT records full oracle constraint satisfaction; real monotonic
> timings remain visible and host-dependent.”

### 75–84 seconds — Close on the safety model

**Action:** Open **Architecture & Safety** and stop on the authority invariant and mandatory write
path.

**Narration:**

> “The invariant is simple: intelligence proposes, deterministic controls decide. Any future
> write must still pass authorization, complete validation, compare-and-swap, and trusted audit.”

## Recording accuracy checklist

- Say “recorded replay,” not “live AI,” while using the Design Studio.
- Say “detached proposal,” not “generated building” or “committed plan.”
- Do not imply the World Model sample was created from the selected proposal.
- Describe circulation as a proxy, not a walking path or egress result.
- Do not claim a real OpenAI run; the bundled report contains only deterministic systems.
- Do not describe a proposal digest as a signature or proof of authenticity.
- If a control or artifact fails to load, stop and fix the setup instead of editing around the
  fail-closed state during recording.

## Optional 15-second extension

If the recording may run closer to 90 seconds, expand the Benchmark Lab segment by opening one
case in the attempt matrix and showing its proposal digests across two trials.

Suggested narration:

> “The report keeps proposal fingerprints and redacted outcomes, not proposal geometry or provider
> messages. Even perfect evidence has no write authority.”
