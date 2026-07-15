"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import Image from "next/image";
import type { RenderObject } from "@/lib/render-ir/types";
import { WorldModelViewer, type WorldModelViewSnapshot } from "../viewer-client";
import styles from "./world-model.module.css";

const EMPTY_SNAPSHOT: WorldModelViewSnapshot = {
  renderIr: null,
  selected: null,
  floorId: null,
  status: "loading",
  errorMessage: null,
};

const ENTITY_LABELS: Readonly<Record<RenderObject["entity_type"], string>> = {
  room: "Rooms",
  wall: "Walls",
  door: "Doors",
  window: "Windows",
};

export function WorldModelExplorerClient() {
  const [snapshot, setSnapshot] = useState<WorldModelViewSnapshot>(EMPTY_SNAPSHOT);
  const [query, setQuery] = useState("");
  const [selectionRequest, setSelectionRequest] = useState<{
    readonly entityId: string;
    readonly requestId: number;
  } | null>(null);
  const selectionSequence = useRef(0);
  const [svgOpen, setSvgOpen] = useState(false);

  const handleSnapshot = useCallback((next: WorldModelViewSnapshot) => {
    setSnapshot(next);
  }, []);

  const filteredObjects = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!snapshot.renderIr) return [];
    if (!normalized) return snapshot.renderIr.objects;
    return snapshot.renderIr.objects.filter(
      (item) => item.entity_id.toLowerCase().includes(normalized) || item.name.toLowerCase().includes(normalized),
    );
  }, [query, snapshot.renderIr]);

  const groupedObjects = useMemo(() => {
    const groups = new Map<RenderObject["entity_type"], RenderObject[]>();
    for (const item of filteredObjects) {
      const current = groups.get(item.entity_type) ?? [];
      current.push(item);
      groups.set(item.entity_type, current);
    }
    return groups;
  }, [filteredObjects]);

  const source = snapshot.renderIr?.source_model;
  const selected = snapshot.selected;

  return (
    <div className={styles.explorer}>
      <aside className={styles.navigator} aria-label="World Model entity navigator">
        <header className={styles.navigatorHeader}>
          <p className={styles.kicker}>Authoritative sample</p>
          <h1>World Model Explorer</h1>
          <p>Search a validated, read-only projection of the current JSON revision.</p>
        </header>

        <div className={styles.searchField}>
          <label htmlFor="entity-search">Search entity ID or name</label>
          <input
            id="entity-search"
            type="search"
            placeholder="room, wall, win…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <span>{filteredObjects.length} results</span>
        </div>

        <div className={styles.entityTree} aria-label="Filtered entity tree">
          {(["room", "wall", "door", "window"] as const).map((entityType) => {
            const objects = groupedObjects.get(entityType) ?? [];
            if (!objects.length) return null;
            return (
              <section key={entityType}>
                <h2>
                  <span>{ENTITY_LABELS[entityType]}</span>
                  <small>{objects.length}</small>
                </h2>
                <ul>
                  {objects.map((item) => (
                    <li key={item.entity_id}>
                      <button
                        type="button"
                        data-selected={selected?.entity_id === item.entity_id}
                        aria-pressed={selected?.entity_id === item.entity_id}
                        onClick={() => {
                          selectionSequence.current += 1;
                          setSelectionRequest({
                            entityId: item.entity_id,
                            requestId: selectionSequence.current,
                          });
                        }}
                      >
                        <i data-type={item.entity_type} aria-hidden="true" />
                        <span>
                          <strong>{item.name}</strong>
                          <small>{item.entity_id}</small>
                        </span>
                        <b>{item.floor_id}</b>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
          {filteredObjects.length === 0 && snapshot.status === "ready" ? (
            <div className={styles.emptyTree}>No entity matches “{query}”.</div>
          ) : null}
        </div>
      </aside>

      <section className={styles.viewport} aria-label="Validated World Model 3D scene">
        <div className={styles.viewportTitle}>
          <span className={styles.authorityPill}>Authoritative World Model</span>
          <span>Derived read-only scene</span>
          <code>{source?.model_id ?? "loading"} / rev {source?.revision ?? "—"}</code>
        </div>
        <WorldModelViewer
          embedded
          selectionRequest={selectionRequest}
          onSnapshot={handleSnapshot}
        />
      </section>

      <aside className={styles.inspector} aria-label="World Model metadata and entity inspector">
        <section className={styles.identityCard}>
          <div>
            <span className={styles.statusDot} data-ready={snapshot.status === "ready"} aria-hidden="true" />
            <p className={styles.kicker}>Validation status</p>
          </div>
          <strong>{snapshot.status === "ready" ? "Validated projection" : snapshot.status}</strong>
          <p>Render IR is admitted only after complete schema, semantic, complexity and geometry validation.</p>
        </section>

        <InspectorSection
          title="Model metadata"
          values={[
            ["Model ID", source?.model_id ?? "—"],
            ["Revision", source ? String(source.revision) : "—"],
            ["Schema", source?.schema_version ?? "—"],
            ["Root building", source?.root_building_id ?? "—"],
          ]}
        />
        <InspectorSection
          title="Coordinate contract"
          values={[
            ["Units", "metres / degrees"],
            ["System", "local Cartesian"],
            ["Handedness", "right-handed"],
            ["Up axis", "Z up"],
          ]}
        />
        <InspectorSection
          title={selected ? selected.name : "Entity selection"}
          values={[
            ["Entity ID", selected?.entity_id ?? "No selection"],
            ["Entity type", selected?.entity_type ?? "—"],
            ["Floor", selected?.floor_id ?? snapshot.floorId ?? "All floors"],
            ["Render object", selected?.geometry.kind ?? "—"],
          ]}
        />

        <section className={styles.artifactSection}>
          <h2>Derived artifacts</h2>
          <button type="button" onClick={() => setSvgOpen((value) => !value)} aria-expanded={svgOpen}>
            {svgOpen ? "Hide" : "Preview"} SVG floor plan
          </button>
          <a href="/examples/showcase-house.svg" download="showcase-house.svg">Download SVG</a>
          <a href="/examples/showcase-house.render-ir.json" download="showcase-house.render-ir.json">Download Render IR</a>
          <p>Downloads are derived debugging artifacts, never revision snapshots.</p>
        </section>

        {svgOpen ? (
          <figure className={styles.svgPreview}>
            <Image
              src="/examples/showcase-house.svg"
              width={920}
              height={720}
              unoptimized
              alt="Deterministic SVG preview of the sample ground floor"
            />
            <figcaption>Deterministic SVG · validated read-only output</figcaption>
          </figure>
        ) : null}

        {selected ? (
          <details className={styles.jsonDisclosure}>
            <summary>View JSON</summary>
            <pre>{JSON.stringify(selected, null, 2)}</pre>
          </details>
        ) : null}
      </aside>
    </div>
  );
}

function InspectorSection({
  title,
  values,
}: {
  readonly title: string;
  readonly values: readonly (readonly [string, string])[];
}) {
  return (
    <section className={styles.inspectorSection}>
      <h2>{title}</h2>
      <dl>
        {values.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
