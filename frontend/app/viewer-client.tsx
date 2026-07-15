"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { EntityList } from "./entity-list";
import { loadRenderIr, DEFAULT_RENDER_IR_SOURCE } from "@/lib/render-ir/source";
import type { RenderIr } from "@/lib/render-ir/types";
import { SceneController } from "@/lib/three/scene-controller";

interface WorldModelViewerProps {
  readonly source?: string;
}

export function WorldModelViewer({ source = DEFAULT_RENDER_IR_SOURCE }: WorldModelViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const controllerRef = useRef<SceneController | null>(null);
  const [renderIr, setRenderIr] = useState<RenderIr | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [floorId, setFloorId] = useState<string | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [loadVersion, setLoadVersion] = useState(0);

  useEffect(() => {
    const abortController = new AbortController();
    Promise.resolve()
      .then(() => {
        if (abortController.signal.aborted) return null;
        setStatus("loading");
        setErrorMessage(null);
        return loadRenderIr(source, abortController.signal);
      })
      .then((value) => {
        if (abortController.signal.aborted || value === null) return;
        setRenderIr(value);
        setFloorId(null);
        setSelectedId(null);
        setStatus("ready");
      })
      .catch((error: unknown) => {
        if (abortController.signal.aborted) return;
        setRenderIr(null);
        setStatus("error");
        setErrorMessage(error instanceof Error ? error.message : "The visualization could not be loaded.");
      });
    return () => abortController.abort();
  }, [source, loadVersion]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !renderIr) return;
    let active = true;
    let controller: SceneController | null = null;
    try {
      controller = new SceneController(canvas, renderIr, setSelectedId);
      controllerRef.current = controller;
    } catch {
      queueMicrotask(() => {
        if (!active) return;
        setStatus("error");
        setErrorMessage("This browser could not start the 3D viewer.");
      });
    }
    return () => {
      active = false;
      controller?.dispose();
      controllerRef.current = null;
    };
  }, [renderIr]);

  const selected = useMemo(
    () => renderIr?.objects.find((item) => item.entity_id === selectedId) ?? null,
    [renderIr, selectedId],
  );

  const chooseFloor = (nextFloorId: string | null) => {
    setFloorId(nextFloorId);
    controllerRef.current?.setFloor(nextFloorId);
  };

  const chooseEntity = (entityId: string) => {
    controllerRef.current?.selectEntity(entityId);
  };

  return (
    <main className="viewer-shell">
      <header className="viewer-header">
        <div className="brand-lockup">
          <span className="brand-index" aria-hidden="true">01</span>
          <div>
            <p className="eyebrow">Embodied world model</p>
            <h1>Parametric Architect</h1>
          </div>
        </div>
        <div className="model-summary" aria-live="polite">
          <span className={`status-dot status-dot--${status}`} aria-hidden="true" />
          <span>{status === "ready" ? "Validated projection" : status === "loading" ? "Loading projection" : "Projection unavailable"}</span>
          {renderIr ? (
            <>
              <span className="summary-divider" aria-hidden="true" />
              <span className="mono">{renderIr.source_model.model_id}</span>
              <span className="revision-chip">REV {renderIr.source_model.revision}</span>
            </>
          ) : null}
        </div>
      </header>

      <section className="viewer-stage" aria-label="World model visualization workspace">
        <canvas
          ref={canvasRef}
          className="world-canvas"
          aria-label="Interactive 3D view. Drag to orbit, scroll to zoom, and press Escape to clear selection."
          tabIndex={0}
        />

        <div className="stage-toolbar" aria-label="Camera controls">
          <button type="button" onClick={() => controllerRef.current?.viewIsometric()}>
            Isometric
          </button>
          <button type="button" onClick={() => controllerRef.current?.viewTop()}>
            Plan view
          </button>
        </div>

        <div className="axis-key" aria-label="Model coordinate system">
          <span><i className="axis axis--x" />X</span>
          <span><i className="axis axis--y" />Y</span>
          <span><i className="axis axis--z" />Z up</span>
        </div>

        {status !== "ready" ? (
          <div className="stage-state" role={status === "error" ? "alert" : "status"}>
            <span className="stage-state__number">{status === "error" ? "!" : "…"}</span>
            <h2>{status === "error" ? "Unable to open the model" : "Building the scene"}</h2>
            <p>{errorMessage ?? "Validating the versioned visualization contract."}</p>
            {status === "error" ? (
              <button type="button" onClick={() => setLoadVersion((value) => value + 1)}>
                Retry
              </button>
            ) : null}
          </div>
        ) : null}
      </section>

      <aside className="model-panel" aria-label="World model browser">
        <section className="panel-section panel-section--floors">
          <p className="section-kicker">Floor visibility</p>
          <div className="floor-options">
            <button
              type="button"
              data-active={floorId === null}
              aria-pressed={floorId === null}
              onClick={() => chooseFloor(null)}
            >
              <span>All floors</span>
              <small>{renderIr?.floors.length ?? 0}</small>
            </button>
            {renderIr?.floors.map((floor) => (
              <button
                type="button"
                key={floor.entity_id}
                data-active={floorId === floor.entity_id}
                aria-pressed={floorId === floor.entity_id}
                onClick={() => chooseFloor(floor.entity_id)}
              >
                <span>{floor.name}</span>
                <small>{floor.elevation.toFixed(2)} m</small>
              </button>
            ))}
          </div>
        </section>

        <section className="panel-section panel-section--entities">
          <div className="section-heading">
            <p className="section-kicker">Entity registry</p>
            <span>{renderIr?.objects.filter((item) => floorId === null || item.floor_id === floorId).length ?? 0}</span>
          </div>
          {renderIr ? (
            <EntityList
              objects={renderIr.objects}
              visibleFloorId={floorId}
              selectedId={selectedId}
              onSelect={chooseEntity}
            />
          ) : null}
        </section>

        <section className="selection-card" aria-live="polite">
          <p className="section-kicker">Selection</p>
          {selected ? (
            <>
              <strong>{selected.name}</strong>
              <dl>
                <div><dt>Type</dt><dd>{selected.entity_type}</dd></div>
                <div><dt>Entity ID</dt><dd className="mono">{selected.entity_id}</dd></div>
                <div><dt>Floor</dt><dd className="mono">{selected.floor_id}</dd></div>
                {(selected.entity_type === "door" || selected.entity_type === "window") ? (
                  <div><dt>Host wall</dt><dd className="mono">{selected.host_wall_id}</dd></div>
                ) : null}
              </dl>
            </>
          ) : (
            <p className="selection-empty">Select geometry in the scene or choose an entity above.</p>
          )}
        </section>

        <footer className="panel-footer">
          <span>Render IR {renderIr?.render_ir_version ?? "—"}</span>
          <span>Right-handed · Z-up · metres</span>
        </footer>
      </aside>
    </main>
  );
}
