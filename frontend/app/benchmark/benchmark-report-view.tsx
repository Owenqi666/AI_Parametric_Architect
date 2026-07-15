"use client";

import { useId, useMemo, useState } from "react";

import {
  METRIC_LABELS,
  TRACK_LABELS,
  formatDuration,
  formatMetricEvidence,
  formatPercent,
  formatRuntimeEvidence,
  shortDigest,
} from "../../lib/benchmark/display";
import {
  BENCHMARK_TRACKS,
  PROFILE_METRICS,
  type BenchmarkAttemptObservation,
  type BenchmarkFailure,
  type BenchmarkReport,
  type BenchmarkSystemReport,
  type BenchmarkTrack,
} from "../../lib/benchmark/types";

import styles from "./benchmark.module.css";
import { MetricRadar } from "./metric-radar";

interface BenchmarkReportViewProps {
  readonly report: BenchmarkReport;
  readonly sourceLabel: string;
}

interface FailureBucket {
  readonly failure: BenchmarkFailure;
  count: number;
  readonly systems: Set<string>;
}

function observationStatus(observation: BenchmarkAttemptObservation, track: BenchmarkTrack): string {
  const value = observation.tracks[track];
  if (value.planning_succeeded) return value.plan_valid ? "Valid proposal" : "Invalid proposal";
  return value.failure ? `${value.failure.stage}: ${value.failure.code}` : "Planning failed";
}

function failureBuckets(
  observations: readonly BenchmarkAttemptObservation[],
  track: BenchmarkTrack,
): readonly FailureBucket[] {
  const buckets = new Map<string, FailureBucket>();
  for (const observation of observations) {
    const failure = observation.tracks[track].failure;
    if (!failure) continue;
    const key = `${failure.stage}\u0000${failure.code}\u0000${failure.path}`;
    const existing = buckets.get(key);
    if (existing) {
      existing.count += 1;
      existing.systems.add(observation.system_id);
    } else {
      buckets.set(key, {
        failure,
        count: 1,
        systems: new Set([observation.system_id]),
      });
    }
  }
  return [...buckets.values()].sort(
    (left, right) => right.count - left.count || left.failure.code.localeCompare(right.failure.code),
  );
}

function SystemCard({ system, track }: { readonly system: BenchmarkSystemReport; readonly track: BenchmarkTrack }) {
  const summary = system.tracks[track];
  return (
    <article className={styles.systemCard}>
      <div className={styles.systemCardHeader}>
        <div>
          <p className={styles.kicker}>System</p>
          <h3>{system.descriptor.system_id}</h3>
        </div>
        <span className={styles.modeBadge} data-mode={system.descriptor.execution_mode}>
          {system.descriptor.deterministic ? "Deterministic" : "Real nondeterministic"}
        </span>
      </div>
      <dl className={styles.systemMetadata}>
        <div><dt>Planner</dt><dd>{system.descriptor.planner_configuration.strategy}</dd></div>
        <div><dt>Rules</dt><dd>{system.descriptor.planner_configuration.rules_version}</dd></div>
        <div><dt>Intent agent</dt><dd>{system.descriptor.intent_agent.name}</dd></div>
        <div><dt>Plan agent</dt><dd>{system.descriptor.floor_plan_agent.name}</dd></div>
        {system.descriptor.provider ? (
          <div><dt>Provider</dt><dd>{system.descriptor.provider}</dd></div>
        ) : null}
        {system.descriptor.model ? (
          <div><dt>Model</dt><dd>{system.descriptor.model}</dd></div>
        ) : null}
      </dl>

      <div className={styles.intentMetric}>
        <span>{track === "oracle_intent" ? "E2E parser exactness · not used" : "E2E parser exactness"}</span>
        <strong>{track === "oracle_intent" ? "N/A" : formatPercent(system.intent_extraction_accuracy.value)}</strong>
        <small>
          {track === "oracle_intent"
            ? "Oracle track supplies reference intent directly."
            : formatMetricEvidence(system.intent_extraction_accuracy)}
        </small>
      </div>

      <div className={styles.metricGrid}>
        {PROFILE_METRICS.map((metric) => {
          const value = summary.metrics[metric];
          return (
            <div key={metric} className={styles.metricCell} data-applicable={value.applicable}>
              <span>{METRIC_LABELS[metric]}</span>
              <strong>{formatPercent(value.value)}</strong>
              <small>
                {value.applicable
                  ? `${value.covered_attempt_count}/${value.attempt_count} covered · ${value.sample_count} samples`
                  : value.reason}
              </small>
              {value.successes !== null ? (
                <small>
                  {value.successes} passed · {value.attempt_count - value.successes} failed
                </small>
              ) : null}
            </div>
          );
        })}
      </div>
    </article>
  );
}

export function BenchmarkReportView({ report, sourceLabel }: BenchmarkReportViewProps) {
  const [track, setTrack] = useState<BenchmarkTrack>("end_to_end");
  const caseIds = useMemo(
    () => [...new Set(report.observations.map((observation) => observation.case_id))].sort(),
    [report],
  );
  const [requestedCaseId, setRequestedCaseId] = useState(caseIds[0] ?? "");
  const selectedCaseId = caseIds.includes(requestedCaseId)
    ? requestedCaseId
    : (caseIds[0] ?? "");
  const tabPanelId = useId();
  const tabIdPrefix = useId();

  const failures = useMemo(
    () => failureBuckets(report.observations, track),
    [report, track],
  );
  const selectedObservations = report.observations
    .filter((observation) => observation.case_id === selectedCaseId)
    .sort(
      (left, right) =>
        left.system_id.localeCompare(right.system_id) || left.trial_index - right.trial_index,
    );
  const openAiSystems = report.systems.filter(
    (system) => system.descriptor.provider === "openai-responses",
  );

  return (
    <div className={styles.reportView}>
      <section className={styles.reportIdentity} aria-labelledby="benchmark-report-identity">
        <div>
          <p className={styles.kicker}>Admitted report · {sourceLabel}</p>
          <h2 id="benchmark-report-identity">
            {report.dataset.dataset_id} <span>v{report.dataset.dataset_version}</span>
          </h2>
          <p>
            {report.dataset.case_count} cases · {report.systems.length} systems · {report.configuration.trials} trials
          </p>
        </div>
        <dl>
          <div>
            <dt>Dataset digest</dt>
            <dd title={report.dataset.digest}>{shortDigest(report.dataset.digest)}</dd>
          </div>
          <div>
            <dt>Reference set</dt>
            <dd>{report.annotations.annotation_set_id} v{report.annotations.annotation_set_version}</dd>
          </div>
          <div>
            <dt>Annotation digest</dt>
            <dd title={report.annotations.digest}>{shortDigest(report.annotations.digest)}</dd>
          </div>
          <div>
            <dt>Metric context</dt>
            <dd>{report.configuration.metric_context.context_id}</dd>
          </div>
        </dl>
      </section>

      <aside className={styles.evidenceWarning} aria-label="Evidence limitations">
        <strong>Detached evidence only.</strong>
        <span>
          Scores and proposal fingerprints are comparison signals—not World Model geometry,
          validation proof, code compliance, authorization, or commit authority. Circulation is
          a room-center distance proxy.
        </span>
      </aside>

      {openAiSystems.length > 0 ? (
        <aside className={styles.networkNotice} aria-label="OpenAI evidence notice">
          <strong>Report declares OpenAI Responses evidence.</strong>
          <span>
            Report metadata marks {openAiSystems.map((system) => system.descriptor.system_id).join(", ")} as real
            nondeterministic. Treat provider/model fields as declared metadata and compare coverage
            before drawing conclusions.
          </span>
        </aside>
      ) : null}

      <div className={styles.trackTabs} role="tablist" aria-label="Benchmark track">
        {BENCHMARK_TRACKS.map((value) => (
          <button
            key={value}
            id={`${tabIdPrefix}-${value}`}
            type="button"
            role="tab"
            aria-selected={track === value}
            aria-controls={tabPanelId}
            tabIndex={track === value ? 0 : -1}
            onClick={() => setTrack(value)}
            onKeyDown={(event) => {
              const currentIndex = BENCHMARK_TRACKS.indexOf(value);
              let nextIndex: number | null = null;
              if (event.key === "ArrowRight") {
                nextIndex = (currentIndex + 1) % BENCHMARK_TRACKS.length;
              } else if (event.key === "ArrowLeft") {
                nextIndex = (currentIndex - 1 + BENCHMARK_TRACKS.length) % BENCHMARK_TRACKS.length;
              } else if (event.key === "Home") {
                nextIndex = 0;
              } else if (event.key === "End") {
                nextIndex = BENCHMARK_TRACKS.length - 1;
              }
              if (nextIndex === null) return;
              event.preventDefault();
              const nextTrack = BENCHMARK_TRACKS[nextIndex];
              setTrack(nextTrack);
              document.getElementById(`${tabIdPrefix}-${nextTrack}`)?.focus();
            }}
          >
            <strong>{TRACK_LABELS[value]}</strong>
            <span>
              {value === "end_to_end"
                ? "Requirement → parser → planner"
                : "Reference intent → planner"}
            </span>
          </button>
        ))}
      </div>

      <div
        id={tabPanelId}
        role="tabpanel"
        aria-labelledby={`${tabIdPrefix}-${track}`}
        className={styles.trackPanel}
      >
        {track === "end_to_end" ? (
          <aside className={styles.trackNotice} aria-label="End-to-end coverage explanation">
            <strong>Why several spatial metrics are N/A</strong>
            <span>
              The bundled deterministic parser produced plans but did not exactly match the external
              reference intents. Spatial scores therefore remain uncovered instead of scoring a
              different intent as though it were the reference. Switch to Oracle intent to inspect
              planner-only evidence.
            </span>
          </aside>
        ) : (
          <aside className={styles.trackNotice} aria-label="Oracle-intent coverage explanation">
            <strong>Planner-only evidence</strong>
            <span>
              This track bypasses intent parsing and supplies the external reference intent directly.
              It isolates planner behavior; it is not an end-to-end product score.
            </span>
          </aside>
        )}
        <section aria-labelledby="system-comparison-heading">
          <div className={styles.sectionHeading}>
            <div>
              <p className={styles.kicker}>{TRACK_LABELS[track]}</p>
              <h2 id="system-comparison-heading">System comparison</h2>
            </div>
            <p>Every binary score retains all configured attempts in its denominator.</p>
          </div>
          <div className={styles.systemGrid}>
            {report.systems.map((system) => (
              <SystemCard key={system.descriptor.system_id} system={system} track={track} />
            ))}
          </div>
        </section>

        <MetricRadar systems={report.systems} track={track} />

        <section className={styles.panel} aria-labelledby="runtime-heading">
          <div className={styles.sectionHeading}>
            <div>
              <p className={styles.kicker}>Observed timing</p>
              <h2 id="runtime-heading">Runtime evidence</h2>
            </div>
            <p>Monotonic timings vary by host and are not deterministic score inputs.</p>
          </div>
          <div className={styles.tableScroller}>
            <table className={styles.dataTable}>
              <caption>Runtime summaries for the selected track</caption>
              <thead>
                <tr>
                  <th scope="col">System</th>
                  <th scope="col">Parse</th>
                  <th scope="col">Plan</th>
                  <th scope="col">Total</th>
                </tr>
              </thead>
              <tbody>
                {report.systems.map((system) => {
                  const runtime = system.tracks[track].runtime_ns;
                  return (
                    <tr key={system.descriptor.system_id}>
                      <th scope="row">{system.descriptor.system_id}</th>
                      <td>{formatRuntimeEvidence(runtime.parse)}</td>
                      <td>{formatRuntimeEvidence(runtime.plan)}</td>
                      <td>{formatRuntimeEvidence(runtime.total)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <section className={styles.panel} aria-labelledby="case-matrix-heading">
          <div className={styles.sectionHeading}>
            <div>
              <p className={styles.kicker}>Attempt matrix</p>
              <h2 id="case-matrix-heading">Per-case outcomes</h2>
            </div>
            <p>Select a case to compare proposal fingerprints across both tracks.</p>
          </div>
          <div className={styles.tableScroller}>
            <table className={styles.dataTable}>
              <caption>Per-case aggregate for {TRACK_LABELS[track]}</caption>
              <thead>
                <tr>
                  <th scope="col">Case</th>
                  <th scope="col">System</th>
                  <th scope="col">Intent exact</th>
                  <th scope="col">Planning</th>
                  <th scope="col">Valid</th>
                  <th scope="col">Failed</th>
                </tr>
              </thead>
              <tbody>
                {caseIds.flatMap((caseId) =>
                  report.systems.map((system) => {
                    const values = report.observations.filter(
                      (observation) =>
                        observation.case_id === caseId &&
                        observation.system_id === system.descriptor.system_id,
                    );
                    const intentExact = values.filter((value) => value.intent_exact).length;
                    const planning = values.filter(
                      (value) => value.tracks[track].planning_succeeded,
                    ).length;
                    const valid = values.filter((value) => value.tracks[track].plan_valid).length;
                    return (
                      <tr key={`${caseId}:${system.descriptor.system_id}`}>
                        <th scope="row">
                          <button
                            type="button"
                            className={styles.caseButton}
                            aria-pressed={selectedCaseId === caseId}
                            onClick={() => setRequestedCaseId(caseId)}
                          >
                            {caseId}
                          </button>
                        </th>
                        <td>{system.descriptor.system_id}</td>
                        <td>{intentExact}/{values.length}</td>
                        <td>{planning}/{values.length}</td>
                        <td>{valid}/{values.length}</td>
                        <td>{values.length - planning}/{values.length}</td>
                      </tr>
                    );
                  }),
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className={styles.panel} aria-labelledby="failure-heading">
          <div className={styles.sectionHeading}>
            <div>
              <p className={styles.kicker}>Redacted diagnostics</p>
              <h2 id="failure-heading">Failure distribution</h2>
            </div>
            <p>Reports retain stage, stable code and path only—never provider messages.</p>
          </div>
          {failures.length === 0 ? (
            <p className={styles.emptyState}>No recorded failures for this track.</p>
          ) : (
            <div className={styles.tableScroller}>
              <table className={styles.dataTable}>
                <caption>Failure code distribution for {TRACK_LABELS[track]}</caption>
                <thead>
                  <tr>
                    <th scope="col">Stage</th>
                    <th scope="col">Code</th>
                    <th scope="col">Path</th>
                    <th scope="col">Systems</th>
                    <th scope="col">Count</th>
                  </tr>
                </thead>
                <tbody>
                  {failures.map((bucket) => (
                    <tr key={`${bucket.failure.stage}:${bucket.failure.code}:${bucket.failure.path}`}>
                      <td>{bucket.failure.stage}</td>
                      <th scope="row">{bucket.failure.code}</th>
                      <td><code>{bucket.failure.path || "—"}</code></td>
                      <td>{[...bucket.systems].sort().join(", ")}</td>
                      <td>{bucket.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className={styles.panel} aria-labelledby="selected-case-heading">
          <div className={styles.sectionHeading}>
            <div>
              <p className={styles.kicker}>Selected case</p>
              <h2 id="selected-case-heading">{selectedCaseId}</h2>
            </div>
            <p>Proposal fingerprints prove identity only; report data contains no proposal geometry.</p>
          </div>
          <div className={styles.tableScroller}>
            <table className={styles.dataTable}>
              <caption>End-to-end and oracle-intent observations for {selectedCaseId}</caption>
              <thead>
                <tr>
                  <th scope="col">System / trial</th>
                  <th scope="col">Intent exact</th>
                  <th scope="col">End-to-end observation</th>
                  <th scope="col">End-to-end digest</th>
                  <th scope="col">Oracle observation</th>
                  <th scope="col">Oracle digest</th>
                </tr>
              </thead>
              <tbody>
                {selectedObservations.map((observation) => (
                  <tr key={`${observation.system_id}:${observation.trial_index}`}>
                    <th scope="row">
                      {observation.system_id}<small>Trial {observation.trial_index + 1}</small>
                    </th>
                    <td>{observation.intent_exact ? "Exact" : "Different"}</td>
                    <td>
                      {observationStatus(observation, "end_to_end")}
                      <small>{formatDuration(observation.tracks.end_to_end.runtime_ns.total)}</small>
                    </td>
                    <td>
                      {observation.tracks.end_to_end.proposal_digest ? (
                        <code title={observation.tracks.end_to_end.proposal_digest}>
                          {shortDigest(observation.tracks.end_to_end.proposal_digest)}
                        </code>
                      ) : "—"}
                    </td>
                    <td>
                      {observationStatus(observation, "oracle_intent")}
                      <small>{formatDuration(observation.tracks.oracle_intent.runtime_ns.total)}</small>
                    </td>
                    <td>
                      {observation.tracks.oracle_intent.proposal_digest ? (
                        <code title={observation.tracks.oracle_intent.proposal_digest}>
                          {shortDigest(observation.tracks.oracle_intent.proposal_digest)}
                        </code>
                      ) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
