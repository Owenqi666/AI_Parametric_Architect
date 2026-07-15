# Three.js World Model Viewer

The viewer consumes only versioned Render IR produced from a validated JSON
World Model. It does not parse, edit, patch, or persist authoritative model
documents.

## Development

```bash
npm ci
npm run dev
```

The bundled demonstration loads
`/examples/simple-house.render-ir.json`, a deterministic derivative of
`../examples/valid_simple_house.json`. Python tests keep that fixture synchronized
with the backend projector.

## Quality gates

```bash
npm run typecheck
npm run lint
npm test
npm run build
```
