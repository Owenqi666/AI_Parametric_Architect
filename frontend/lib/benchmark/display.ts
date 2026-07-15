import type {
  BenchmarkMetricSummary,
  BenchmarkRuntimeSummary,
  BenchmarkTrack,
  ProfileMetric,
} from "./types";

export const TRACK_LABELS: Record<BenchmarkTrack, string> = {
  end_to_end: "End-to-end",
  oracle_intent: "Oracle intent",
};

export const METRIC_LABELS: Record<ProfileMetric, string> = {
  planning_success: "Planning success",
  plan_validity: "Plan validity",
  constraint_satisfaction: "Constraint satisfaction",
  spatial_efficiency: "Spatial efficiency",
  circulation: "Circulation proxy",
  stability: "Stability",
};

export const SYSTEM_COLORS = [
  "#6fd4ff",
  "#ffb86b",
  "#b8f28d",
  "#d8a6ff",
  "#ff7d9c",
  "#7ee6cf",
  "#f4dd73",
  "#9fb6ff",
] as const;

export function formatPercent(value: number | null): string {
  return value === null
    ? "N/A"
    : new Intl.NumberFormat("en", {
        style: "percent",
        maximumFractionDigits: 1,
      }).format(value);
}

export function formatMetricEvidence(metric: BenchmarkMetricSummary): string {
  if (!metric.applicable) return `N/A · ${metric.reason ?? "no applicable samples"}`;
  const success = metric.successes === null
    ? ""
    : ` · ${metric.successes} passed / ${metric.attempt_count - metric.successes} failed`;
  return `${formatPercent(metric.value)} · coverage ${metric.covered_attempt_count}/${metric.attempt_count} · samples ${metric.sample_count}${success}`;
}

export function formatDuration(value: number | null): string {
  if (value === null) return "N/A";
  if (value < 1_000) return `${value} ns`;
  if (value < 1_000_000) return `${(value / 1_000).toFixed(value < 10_000 ? 1 : 0)} μs`;
  if (value < 1_000_000_000) return `${(value / 1_000_000).toFixed(value < 10_000_000 ? 2 : 1)} ms`;
  return `${(value / 1_000_000_000).toFixed(2)} s`;
}

export function formatRuntimeEvidence(runtime: BenchmarkRuntimeSummary): string {
  if (!runtime.applicable) return `N/A · ${runtime.reason ?? "no runtime samples"}`;
  return `median ${formatDuration(runtime.median_ns)} · p95 ${formatDuration(runtime.p95_ns)} · coverage ${runtime.covered_attempt_count}/${runtime.attempt_count}`;
}

export function shortDigest(value: string): string {
  return `${value.slice(0, 10)}…${value.slice(-8)}`;
}
