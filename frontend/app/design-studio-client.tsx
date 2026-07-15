"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { loadPlanningShowcase } from "@/lib/proposal-preview/source";
import type {
  PreviewMetricResult,
  PreviewRoom,
  ShowcaseScenario,
  SuccessfulShowcaseScenario,
} from "@/lib/proposal-preview/types";
import { ProposalPlan, roomLabel } from "./proposal-plan";
import { WorldModelViewer, type WorldModelViewSnapshot } from "./viewer-client";
import styles from "./design-studio.module.css";

type StageStatus = "pending" | "running" | "succeeded" | "failed" | "not_applicable";
type PipelineStageId = "requirement" | "intent" | "planning" | "evaluation" | "world_model";
type ViewportMode = "proposal" | "world-model";
type ExecutionMode = "offline" | "recorded" | "openai";

interface PipelineStage {
  readonly id: PipelineStageId;
  readonly index: string;
  readonly label: string;
}

const PIPELINE: readonly PipelineStage[] = [
  { id: "requirement", index: "01", label: "Requirement" },
  { id: "intent", index: "02", label: "Design Intent" },
  { id: "planning", index: "03", label: "Constraint Planning" },
  { id: "evaluation", index: "04", label: "Evaluation" },
  { id: "world_model", index: "05", label: "Authoritative World Model" },
];

const EMPTY_STAGES: Record<PipelineStageId, StageStatus> = {
  requirement: "pending",
  intent: "pending",
  planning: "pending",
  evaluation: "pending",
  world_model: "pending",
};

const EMPTY_WORLD_SNAPSHOT: WorldModelViewSnapshot = {
  renderIr: null,
  selected: null,
  floorId: null,
  status: "loading",
  errorMessage: null,
};

function completedStages(scenario: ShowcaseScenario): Record<PipelineStageId, StageStatus> {
  if (scenario.status === "success") {
    return {
      requirement: "succeeded",
      intent: "succeeded",
      planning: "succeeded",
      evaluation: "succeeded",
      world_model: "not_applicable",
    };
  }
  return {
    requirement: scenario.intent ? "succeeded" : "failed",
    intent: scenario.intent ? "succeeded" : "not_applicable",
    planning: scenario.intent ? "failed" : "not_applicable",
    evaluation: "not_applicable",
    world_model: "not_applicable",
  };
}

function statusLabel(status: StageStatus): string {
  return status === "not_applicable" ? "not applicable" : status;
}

function metricDisplay(metric: PreviewMetricResult): string {
  if (!metric.applicable || metric.value === null) return "N/A";
  return `${(metric.value * 100).toFixed(1)}%`;
}

export function DesignStudioClient() {
  const [artifactStatus, setArtifactStatus] = useState<"loading" | "ready" | "error">("loading");
  const [artifactError, setArtifactError] = useState<string | null>(null);
  const [scenarios, setScenarios] = useState<readonly ShowcaseScenario[]>([]);
  const [scenarioId, setScenarioId] = useState("");
  const [requirement, setRequirement] = useState("");
  const [executionMode, setExecutionMode] = useState<ExecutionMode>("offline");
  const [openAiLiveAvailable, setOpenAiLiveAvailable] = useState(false);
  const [viewportMode, setViewportMode] = useState<ViewportMode>("proposal");
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  const [stageStatuses, setStageStatuses] = useState<Record<PipelineStageId, StageStatus>>(EMPTY_STAGES);
  const [showOutput, setShowOutput] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [inputFailure, setInputFailure] = useState<string | null>(null);
  const [worldSnapshot, setWorldSnapshot] = useState<WorldModelViewSnapshot>(EMPTY_WORLD_SNAPSHOT);
  const runVersion = useRef(0);

  useEffect(() => {
    const abort = new AbortController();
    void loadPlanningShowcase(undefined, abort.signal)
      .then((artifact) => {
        if (abort.signal.aborted) return;
        const first = artifact.scenarios.find((scenario) => scenario.status === "success") ?? artifact.scenarios[0];
        if (!first) throw new Error("Showcase artifact contains no scenarios.");
        setScenarios(artifact.scenarios);
        setScenarioId(first.scenario_id);
        setRequirement(first.input_requirement);
        setStageStatuses(completedStages(first));
        setSelectedPlanId(first.status === "success" ? (first.proposal.rooms[0]?.plan_id ?? null) : null);
        setShowOutput(true);
        setArtifactStatus("ready");
      })
      .catch((error: unknown) => {
        if (abort.signal.aborted) return;
        setArtifactStatus("error");
        setArtifactError(error instanceof Error ? error.message : "Showcase data could not be admitted.");
      });
    return () => abort.abort();
  }, []);

  useEffect(() => {
    const abort = new AbortController();
    void fetch("/v1/capabilities", { credentials: "same-origin", signal: abort.signal })
      .then(async (response) => {
        if (!response.ok) return null;
        return (await response.json()) as unknown;
      })
      .then((value) => {
        if (abort.signal.aborted || value === null || typeof value !== "object") return;
        const capabilities = value as Record<string, unknown>;
        setOpenAiLiveAvailable(
          capabilities.openai_requirement_parser_available === true &&
            capabilities.live_planning_preview_available === true,
        );
      })
      .catch(() => undefined);
    return () => abort.abort();
  }, []);

  useEffect(() => () => {
    runVersion.current += 1;
  }, []);

  const activeScenario = useMemo(
    () => scenarios.find((scenario) => scenario.scenario_id === scenarioId) ?? null,
    [scenarioId, scenarios],
  );

  const successfulScenario =
    showOutput && activeScenario?.status === "success" ? activeScenario : null;
  const selectedRoom = useMemo(() => {
    if (!successfulScenario) return null;
    return successfulScenario.proposal.rooms.find((room) => room.plan_id === selectedPlanId) ?? null;
  }, [selectedPlanId, successfulScenario]);

  const changeScenario = (nextId: string) => {
    runVersion.current += 1;
    const next = scenarios.find((scenario) => scenario.scenario_id === nextId);
    if (!next) return;
    setScenarioId(nextId);
    setRequirement(next.input_requirement);
    setStageStatuses(completedStages(next));
    setSelectedPlanId(next.status === "success" ? (next.proposal.rooms[0]?.plan_id ?? null) : null);
    setInputFailure(null);
    setShowOutput(true);
    setIsRunning(false);
  };

  const reset = () => {
    if (!activeScenario) return;
    runVersion.current += 1;
    setRequirement(activeScenario.input_requirement);
    setStageStatuses(completedStages(activeScenario));
    setSelectedPlanId(activeScenario.status === "success" ? (activeScenario.proposal.rooms[0]?.plan_id ?? null) : null);
    setInputFailure(null);
    setShowOutput(true);
    setIsRunning(false);
  };

  const runPlanning = async () => {
    if (!activeScenario || isRunning) return;
    const version = ++runVersion.current;
    setInputFailure(null);
    setShowOutput(false);
    setSelectedPlanId(null);
    if (requirement.trim() !== activeScenario.input_requirement) {
      setStageStatuses({
        requirement: "failed",
        intent: "not_applicable",
        planning: "not_applicable",
        evaluation: "not_applicable",
        world_model: "not_applicable",
      });
      setInputFailure("SHOWCASE_INPUT_NOT_RECORDED");
      return;
    }

    setIsRunning(true);
    setStageStatuses(EMPTY_STAGES);
    const pause = executionMode === "recorded" ? 430 : 130;
    const sequence: readonly PipelineStageId[] = ["requirement", "intent", "planning", "evaluation"];
    for (const stage of sequence) {
      if (version !== runVersion.current) return;
      if (activeScenario.status === "rejected" && stage === "evaluation") break;
      setStageStatuses((current) => ({ ...current, [stage]: "running" }));
      await new Promise((resolve) => window.setTimeout(resolve, pause));
      if (version !== runVersion.current) return;
      if (activeScenario.status === "rejected" && stage === "planning") {
        setStageStatuses((current) => ({
          ...current,
          planning: "failed",
          evaluation: "not_applicable",
          world_model: "not_applicable",
        }));
        setShowOutput(true);
        setIsRunning(false);
        return;
      }
      setStageStatuses((current) => ({ ...current, [stage]: "succeeded" }));
    }
    if (version !== runVersion.current) return;
    setStageStatuses((current) => ({ ...current, world_model: "not_applicable" }));
    setSelectedPlanId(activeScenario.status === "success" ? (activeScenario.proposal.rooms[0]?.plan_id ?? null) : null);
    setShowOutput(true);
    setIsRunning(false);
  };

  const handleWorldSnapshot = useCallback((snapshot: WorldModelViewSnapshot) => {
    setWorldSnapshot(snapshot);
  }, []);

  if (artifactStatus !== "ready") {
    return (
      <section className={styles.pageState} role={artifactStatus === "error" ? "alert" : "status"}>
        <div className={styles.statePulse} aria-hidden="true" />
        <p className={styles.kicker}>AI Parametric Architect Studio</p>
        <h1>{artifactStatus === "error" ? "Showcase evidence could not be admitted" : "Preparing the planning workspace"}</h1>
        <p>{artifactError ?? "Loading verified offline artifacts without network or provider access."}</p>
      </section>
    );
  }

  return (
    <div className={styles.workspace}>
      <aside className={styles.leftPanel} aria-label="Planning input and execution pipeline">
        <div className={styles.panelIntro}>
          <p className={styles.kicker}>Safe planning workspace</p>
          <h1>Design Studio</h1>
          <p>Natural language becomes typed intent before a constraint solver proposes geometry.</p>
        </div>

        <div className={styles.inputGroup}>
          <label htmlFor="scenario">Showcase scenario</label>
          <select id="scenario" value={scenarioId} onChange={(event) => changeScenario(event.target.value)}>
            {scenarios.map((scenario) => (
              <option key={scenario.scenario_id} value={scenario.scenario_id}>
                {scenario.title}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.inputGroup}>
          <div className={styles.labelRow}>
            <label htmlFor="requirement">Natural-language requirement</label>
            <span>Untrusted input</span>
          </div>
          <textarea
            id="requirement"
            value={requirement}
            onChange={(event) => setRequirement(event.target.value)}
            rows={6}
            spellCheck="true"
          />
          <small>Editing outside a curated scenario fails closed in this offline showcase.</small>
        </div>

        <div className={styles.inputGroup}>
          <label htmlFor="execution-mode">Execution mode</label>
          <select
            id="execution-mode"
            value={executionMode}
            onChange={(event) => setExecutionMode(event.target.value as ExecutionMode)}
          >
            <option value="offline">Offline deterministic</option>
            <option value="recorded">Recorded showcase replay</option>
            {openAiLiveAvailable ? <option value="openai">OpenAI live · intent only</option> : null}
          </select>
          <span className={styles.modeBadge}>Recorded deterministic showcase</span>
        </div>

        <div className={styles.actionRow}>
          <button className={styles.primaryAction} type="button" onClick={() => void runPlanning()} disabled={isRunning}>
            {isRunning ? "Running…" : "Run planning"}
          </button>
          <button className={styles.secondaryAction} type="button" onClick={reset} disabled={isRunning}>
            Reset
          </button>
        </div>

        <section className={styles.pipeline} aria-labelledby="pipeline-heading">
          <div className={styles.sectionHeading}>
            <h2 id="pipeline-heading">Observable pipeline</h2>
            <span>No hidden reasoning</span>
          </div>
          <ol>
            {PIPELINE.map((stage) => (
              <li key={stage.id} data-status={stageStatuses[stage.id]}>
                <span className={styles.stepIndex}>{stage.index}</span>
                <span className={styles.stepCopy}>
                  <strong>{stage.label}</strong>
                  <small>{statusLabel(stageStatuses[stage.id])}</small>
                </span>
                <i aria-hidden="true" />
              </li>
            ))}
          </ol>
        </section>
      </aside>

      <section className={styles.viewportPanel} aria-label="Planning and World Model viewport">
        <header className={styles.viewportHeader}>
          <div>
            <p className={styles.kicker}>{viewportMode === "proposal" ? "Mode A" : "Mode B"}</p>
            <h2>{viewportMode === "proposal" ? "Detached Proposal Preview" : "Authoritative World Model"}</h2>
          </div>
          <div className={styles.modeSwitcher} role="tablist" aria-label="Viewport authority mode">
            <button
              type="button"
              role="tab"
              aria-selected={viewportMode === "proposal"}
              onClick={() => setViewportMode("proposal")}
            >
              Proposal
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={viewportMode === "world-model"}
              onClick={() => setViewportMode("world-model")}
            >
              World Model
            </button>
          </div>
        </header>

        {viewportMode === "proposal" ? (
          <div className={styles.proposalViewport} role="tabpanel">
            <div className={styles.detachedBanner}>
              <strong>Detached Proposal</strong>
              <span>Not committed to World Model</span>
              <span>Advisory planning output</span>
            </div>
            {isRunning ? (
              <div className={styles.viewportSkeleton} aria-label="Planning proposal is running" />
            ) : inputFailure ? (
              <StructuredFailure
                code={inputFailure}
                title="No recorded output for edited input"
                description="Select or restore a curated scenario. This offline build does not pretend to run an unconfigured provider."
              />
            ) : showOutput && activeScenario?.status === "rejected" ? (
              <StructuredFailure
                code={activeScenario.failure.code}
                title="Constraint planning failed closed"
                description="The solver returned no proposal and no fallback geometry was fabricated."
              />
            ) : successfulScenario ? (
              <ProposalPlan
                proposal={successfulScenario.proposal}
                selectedPlanId={selectedPlanId}
                onSelect={setSelectedPlanId}
              />
            ) : (
              <div className={styles.emptyViewport}>Run a curated scenario to inspect its detached proposal.</div>
            )}
          </div>
        ) : (
          <div className={styles.worldViewport} role="tabpanel">
            <WorldModelViewer embedded onSnapshot={handleWorldSnapshot} />
          </div>
        )}
      </section>

      <aside className={styles.inspectorPanel} aria-label="Selection inspector">
        {viewportMode === "proposal" ? (
          <ProposalInspector scenario={successfulScenario} room={selectedRoom} />
        ) : (
          <WorldInspector snapshot={worldSnapshot} />
        )}
      </aside>

      <section className={styles.evidenceRail} aria-label="Planning metrics and execution evidence">
        <EvidenceRail scenario={successfulScenario} activeScenario={activeScenario} inputFailure={inputFailure} />
      </section>
    </div>
  );
}

function StructuredFailure({
  code,
  title,
  description,
}: {
  readonly code: string;
  readonly title: string;
  readonly description: string;
}) {
  return (
    <div className={styles.failureState} role="alert">
      <span aria-hidden="true">!</span>
      <p className={styles.kicker}>No proposal created</p>
      <h3>{title}</h3>
      <code>{code}</code>
      <p>{description}</p>
    </div>
  );
}

function ProposalInspector({
  scenario,
  room,
}: {
  readonly scenario: SuccessfulShowcaseScenario | null;
  readonly room: PreviewRoom | null;
}) {
  if (!scenario || !room) {
    return (
      <div className={styles.inspectorEmpty}>
        <p className={styles.kicker}>Proposal inspector</p>
        <h2>No room selected</h2>
        <p>Select a detached room rectangle to inspect observable solver output.</p>
      </div>
    );
  }
  const constraints = scenario.proposal.spatial_constraints.filter(
    (constraint) => constraint.source_plan_id === room.plan_id || constraint.target_plan_id === room.plan_id,
  );
  return (
    <div className={styles.inspectorContent}>
      <div className={styles.inspectorTitle}>
        <span className={styles.advisoryDot} aria-hidden="true" />
        <div>
          <p className={styles.kicker}>Detached room</p>
          <h2>{roomLabel(room.room_type)}</h2>
        </div>
      </div>
      <div className={styles.authorityNotice}>
        <strong>Advisory only</strong>
        <span>Not authoritative geometry</span>
      </div>
      <DefinitionPanel
        title="Solved placement"
        values={[
          ["Plan ID", room.plan_id],
          ["Room type", room.room_type],
          ["Target area", `${room.target_area.toFixed(1)} m²`],
          ["Solved area", `${(room.width * room.height).toFixed(1)} m²`],
          ["Origin", `${room.x.toFixed(2)}, ${room.y.toFixed(2)} m`],
          ["Dimensions", `${room.width.toFixed(2)} × ${room.height.toFixed(2)} m`],
          ["Orientation", room.orientation],
        ]}
      />
      <section className={styles.inspectorSection}>
        <h3>Applicable constraints</h3>
        {constraints.length ? (
          <ul className={styles.constraintList}>
            {constraints.map((constraint) => (
              <li key={`${constraint.source_plan_id}-${constraint.relation}-${constraint.target_plan_id}`}>
                <strong>{constraint.relation.replaceAll("_", " ")}</strong>
                <span>{constraint.source_plan_id} → {constraint.target_plan_id}</span>
                <small>{constraint.required ? "Required" : "Preference"}</small>
              </li>
            ))}
          </ul>
        ) : (
          <p className={styles.muted}>No explicit spatial constraint is bound to this room.</p>
        )}
      </section>
      <details className={styles.jsonDisclosure}>
        <summary>View JSON</summary>
        <pre>{JSON.stringify(room, null, 2)}</pre>
      </details>
    </div>
  );
}

function WorldInspector({ snapshot }: { readonly snapshot: WorldModelViewSnapshot }) {
  const source = snapshot.renderIr?.source_model;
  const selected = snapshot.selected;
  return (
    <div className={styles.inspectorContent}>
      <div className={styles.inspectorTitle}>
        <span className={styles.authorityDot} aria-hidden="true" />
        <div>
          <p className={styles.kicker}>Authoritative selection</p>
          <h2>{selected?.name ?? "World Model"}</h2>
        </div>
      </div>
      <div className={`${styles.authorityNotice} ${styles.authorityNoticeWorld}`}>
        <strong>Authoritative source</strong>
        <span>Scene is a derived read-only projection</span>
      </div>
      <DefinitionPanel
        title="Revision identity"
        values={[
          ["Model ID", source?.model_id ?? "—"],
          ["Revision", source ? String(source.revision) : "—"],
          ["Schema", source?.schema_version ?? "—"],
          ["Render IR", snapshot.renderIr?.render_ir_version ?? "—"],
        ]}
      />
      <DefinitionPanel
        title="Selected entity"
        values={[
          ["Entity ID", selected?.entity_id ?? "No selection"],
          ["Entity type", selected?.entity_type ?? "—"],
          ["Floor", selected?.floor_id ?? snapshot.floorId ?? "All floors"],
          ["Validation", snapshot.status === "ready" ? "Validated projection" : snapshot.status],
        ]}
      />
      {selected ? (
        <details className={styles.jsonDisclosure}>
          <summary>View JSON</summary>
          <pre>{JSON.stringify(selected, null, 2)}</pre>
        </details>
      ) : null}
    </div>
  );
}

function DefinitionPanel({
  title,
  values,
}: {
  readonly title: string;
  readonly values: readonly (readonly [string, string])[];
}) {
  return (
    <section className={styles.inspectorSection}>
      <h3>{title}</h3>
      <dl className={styles.definitionList}>
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

function EvidenceRail({
  scenario,
  activeScenario,
  inputFailure,
}: {
  readonly scenario: SuccessfulShowcaseScenario | null;
  readonly activeScenario: ShowcaseScenario | null;
  readonly inputFailure: string | null;
}) {
  const systems = scenario?.evidence.systems ?? [];
  const cpSat = systems.find((system) => system.system_id === "cp-sat-v2") ?? systems[0];
  const baseline = systems.find((system) => system.system_id === "rule-spatial-v2");
  const metricItems = cpSat
    ? [
        ["Constraint satisfaction", metricDisplay(cpSat.metrics.constraint_satisfaction)],
        ["Spatial efficiency", metricDisplay(cpSat.metrics.spatial_efficiency)],
        ["Circulation proxy", metricDisplay(cpSat.metrics.circulation)],
        ["Plan stability", metricDisplay(cpSat.metrics.stability)],
      ] as const
    : [];
  return (
    <>
      <div className={styles.evidenceLead}>
        <p className={styles.kicker}>Execution evidence</p>
        <strong>{inputFailure ?? activeScenario?.failure?.code ?? "CP-SAT · deterministic"}</strong>
        <span>{scenario ? scenario.proposal.strategy : "No geometry result"}</span>
      </div>
      <div className={styles.metricStrip}>
        {metricItems.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
        {!metricItems.length ? (
          <div>
            <span>Fail-closed result</span>
            <strong>No proposal</strong>
          </div>
        ) : null}
      </div>
      <div className={styles.comparisonEvidence}>
        <span>{baseline ? "Baseline vs CP-SAT" : "Proposal digest"}</span>
        {baseline && cpSat ? (
          <strong>
            Efficiency {metricDisplay(baseline.metrics.spatial_efficiency)} → {metricDisplay(cpSat.metrics.spatial_efficiency)}
          </strong>
        ) : (
          <code>{scenario?.proposal_digest.slice(0, 16) ?? "no-proposal"}</code>
        )}
        <small>Runtime: not retained in deterministic scenario artifact</small>
      </div>
      <div className={styles.noAuthorityEvidence}>
        <strong>No write authority</strong>
        <span>Evaluation evidence cannot authorize a commit.</span>
      </div>
    </>
  );
}

