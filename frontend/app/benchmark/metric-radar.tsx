import { useId } from "react";

import {
  METRIC_LABELS,
  SYSTEM_COLORS,
  formatMetricEvidence,
  formatPercent,
} from "../../lib/benchmark/display";
import {
  PROFILE_METRICS,
  type BenchmarkSystemReport,
  type BenchmarkTrack,
} from "../../lib/benchmark/types";

import styles from "./benchmark.module.css";

interface MetricRadarProps {
  readonly systems: readonly BenchmarkSystemReport[];
  readonly track: BenchmarkTrack;
}

const CENTER = 160;
const RADIUS = 104;

function point(index: number, value: number): readonly [number, number] {
  const angle = -Math.PI / 2 + (Math.PI * 2 * index) / PROFILE_METRICS.length;
  return [
    CENTER + Math.cos(angle) * RADIUS * value,
    CENTER + Math.sin(angle) * RADIUS * value,
  ];
}

function points(values: readonly number[]): string {
  return values.map((value, index) => point(index, value).join(",")).join(" ");
}

export function MetricRadar({ systems, track }: MetricRadarProps) {
  const titleId = useId();
  const descriptionId = useId();
  const axisPoints = PROFILE_METRICS.map((_, index) => point(index, 1));
  const description = systems
    .map((system) => {
      const metrics = system.tracks[track].metrics;
      return `${system.descriptor.system_id}: ${PROFILE_METRICS.map(
        (metric) => `${METRIC_LABELS[metric]} ${formatPercent(metrics[metric].value)}`,
      ).join(", ")}`;
    })
    .join(". ");

  return (
    <section className={styles.profilePanel} aria-labelledby={titleId}>
      <div className={styles.sectionHeading}>
        <div>
          <p className={styles.kicker}>Normalized profile</p>
          <h2 id={titleId}>Comparable score shape</h2>
        </div>
        <p>Markers without a closed polygon indicate at least one N/A metric.</p>
      </div>

      <div className={styles.radarLayout}>
        <svg
          className={styles.radar}
          viewBox="0 0 320 320"
          role="img"
          aria-labelledby={`${titleId} ${descriptionId}`}
        >
          <title>System metric comparison for the selected track</title>
          <desc id={descriptionId}>{description}</desc>
          {[0.25, 0.5, 0.75, 1].map((ring) => (
            <polygon
              key={ring}
              points={points(PROFILE_METRICS.map(() => ring))}
              className={styles.radarRing}
            />
          ))}
          {axisPoints.map(([x, y], index) => (
            <line
              key={PROFILE_METRICS[index]}
              x1={CENTER}
              y1={CENTER}
              x2={x}
              y2={y}
              className={styles.radarAxis}
            />
          ))}
          {systems.map((system, systemIndex) => {
            const metrics = system.tracks[track].metrics;
            const values = PROFILE_METRICS.map((metric) => metrics[metric].value);
            const color = SYSTEM_COLORS[systemIndex % SYSTEM_COLORS.length];
            const complete = values.every((value): value is number => value !== null);
            return (
              <g key={system.descriptor.system_id}>
                {complete ? (
                  <polygon
                    points={points(values)}
                    fill={color}
                    stroke={color}
                    className={styles.radarSeries}
                  />
                ) : null}
                {values.map((value, metricIndex) => {
                  if (value === null) return null;
                  const [x, y] = point(metricIndex, value);
                  return (
                    <circle
                      key={PROFILE_METRICS[metricIndex]}
                      cx={x}
                      cy={y}
                      r="4"
                      fill={color}
                      stroke="#081016"
                      strokeWidth="2"
                    />
                  );
                })}
              </g>
            );
          })}
          {PROFILE_METRICS.map((metric, index) => {
            const [x, y] = point(index, 1.22);
            return (
              <text
                key={metric}
                x={x}
                y={y}
                textAnchor={x < CENTER - 8 ? "end" : x > CENTER + 8 ? "start" : "middle"}
                dominantBaseline="middle"
                className={styles.radarLabel}
              >
                {METRIC_LABELS[metric]}
              </text>
            );
          })}
        </svg>

        <div className={styles.legend} aria-label="System color legend">
          {systems.map((system, index) => (
            <span key={system.descriptor.system_id}>
              <i
                aria-hidden="true"
                style={{ background: SYSTEM_COLORS[index % SYSTEM_COLORS.length] }}
              />
              {system.descriptor.system_id}
            </span>
          ))}
        </div>
      </div>

      <div className={styles.tableScroller}>
        <table className={styles.dataTable}>
          <caption>Text equivalent for the normalized profile</caption>
          <thead>
            <tr>
              <th scope="col">Metric</th>
              {systems.map((system) => (
                <th scope="col" key={system.descriptor.system_id}>
                  {system.descriptor.system_id}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {PROFILE_METRICS.map((metric) => (
              <tr key={metric}>
                <th scope="row">{METRIC_LABELS[metric]}</th>
                {systems.map((system) => (
                  <td key={system.descriptor.system_id}>
                    {formatMetricEvidence(system.tracks[track].metrics[metric])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
