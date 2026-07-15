# AI Parametric Architect Studio frontend

The browser application presents four bounded product areas:

- `/` — Design Studio with typed intent evidence and a detached Proposal Preview;
- `/benchmark` — Benchmark Lab with strict `BenchmarkReport 1.0.0` admission;
- `/world-model` — read-only World Model Explorer through `Render IR → Three.js`;
- `/architecture` — Architecture & Safety explanation.

Proposal Preview, BenchmarkReport and Render IR use separate exact parsers. The
frontend has no repository, JSON Patch, authorization, validation-bypass, CAS or
commit client, and never treats scene state as the World Model.

## Development

```bash
npm ci
npm run dev
```

The bundled demonstration loads deterministic same-origin fixtures under
`public/examples/`. Proposal evidence is labeled as recorded replay; the authoritative
3D view loads `showcase-house.render-ir.json`, generated from the validated
`../examples/showcase_house.json`. Python integration tests keep generated artifacts
synchronized with their backend contracts.

For the full offline application and API, run `../scripts/run_showcase.sh` from the
repository root.

## Quality gates

```bash
npm run typecheck
npm run lint
npm test
npm run build
```
