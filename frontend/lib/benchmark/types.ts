export const BENCHMARK_REPORT_SCHEMA_VERSION = "1.0.0" as const;
export const DEFAULT_BENCHMARK_REPORT_SOURCE =
  "/examples/planning-core.benchmark-report-1.0.0.json";

export type BenchmarkTrack = "end_to_end" | "oracle_intent";
export type BenchmarkStage = "intent" | "plan";
export type BenchmarkExecutionMode = "deterministic" | "real_nondeterministic";

export interface BenchmarkBudget {
  readonly max_cases: number;
  readonly max_systems: number;
  readonly max_trials: number;
  readonly max_attempts: number;
}

export interface BenchmarkMetricContext {
  readonly context_id: string;
  readonly minimum_room_areas: readonly {
    readonly room_type: string;
    readonly minimum_area: number;
  }[];
  readonly default_minimum_room_area: number;
  readonly minimum_adjacency_contact: number;
  readonly separation_gap: number;
  readonly near_distance: number;
  readonly precision: {
    readonly linear_tolerance: number;
    readonly decimal_places: number;
  };
  readonly max_runs: number;
}

export interface BenchmarkSystemDescriptor {
  readonly system_id: string;
  readonly system_version: string;
  readonly intent_agent: {
    readonly name: string;
    readonly version: string;
  };
  readonly floor_plan_agent: {
    readonly name: string;
    readonly version: string;
  };
  readonly planner_configuration: {
    readonly strategy: string;
    readonly rules_version: string;
    readonly random_seed: number | null;
  };
  readonly execution_mode: BenchmarkExecutionMode;
  readonly deterministic: boolean;
  readonly provider: string | null;
  readonly model: string | null;
  readonly prompt_version: string | null;
}

export interface BenchmarkFailure {
  readonly stage: BenchmarkStage;
  readonly code: string;
  readonly path: string;
}

export interface BenchmarkMetricSummary {
  readonly name: string;
  readonly value: number | null;
  readonly applicable: boolean;
  readonly attempt_count: number;
  readonly covered_attempt_count: number;
  readonly sample_count: number;
  readonly coverage: number;
  readonly successes: number | null;
  readonly reason: string | null;
}

export interface BenchmarkRuntimeSummary {
  readonly name: string;
  readonly applicable: boolean;
  readonly attempt_count: number;
  readonly covered_attempt_count: number;
  readonly sample_count: number;
  readonly coverage: number;
  readonly minimum_ns: number | null;
  readonly median_ns: number | null;
  readonly p95_ns: number | null;
  readonly maximum_ns: number | null;
  readonly total_ns: number | null;
  readonly reason: string | null;
}

export interface BenchmarkTrackSummary {
  readonly track: BenchmarkTrack;
  readonly metrics: {
    readonly planning_success: BenchmarkMetricSummary;
    readonly plan_validity: BenchmarkMetricSummary;
    readonly constraint_satisfaction: BenchmarkMetricSummary;
    readonly spatial_efficiency: BenchmarkMetricSummary;
    readonly circulation: BenchmarkMetricSummary;
    readonly stability: BenchmarkMetricSummary;
  };
  readonly runtime_ns: {
    readonly parse: BenchmarkRuntimeSummary;
    readonly plan: BenchmarkRuntimeSummary;
    readonly total: BenchmarkRuntimeSummary;
  };
}

export interface BenchmarkSystemReport {
  readonly descriptor: BenchmarkSystemDescriptor;
  readonly attempt_count: number;
  readonly intent_extraction_accuracy: BenchmarkMetricSummary;
  readonly tracks: {
    readonly end_to_end: BenchmarkTrackSummary;
    readonly oracle_intent: BenchmarkTrackSummary;
  };
}

export interface BenchmarkTrackObservation {
  readonly track: BenchmarkTrack;
  readonly planning_succeeded: boolean;
  readonly plan_valid: boolean;
  readonly proposal_digest: string | null;
  readonly runtime_ns: {
    readonly parse: number | null;
    readonly plan: number | null;
    readonly total: number;
  };
  readonly failure: BenchmarkFailure | null;
}

export interface BenchmarkAttemptObservation {
  readonly case_id: string;
  readonly system_id: string;
  readonly trial_index: number;
  readonly intent_exact: boolean;
  readonly tracks: {
    readonly end_to_end: BenchmarkTrackObservation;
    readonly oracle_intent: BenchmarkTrackObservation;
  };
}

export interface BenchmarkReport {
  readonly schema_version: typeof BENCHMARK_REPORT_SCHEMA_VERSION;
  readonly dataset: {
    readonly dataset_id: string;
    readonly dataset_version: string;
    readonly digest: string;
    readonly case_count: number;
  };
  readonly annotations: {
    readonly annotation_set_id: string;
    readonly annotation_set_version: string;
    readonly digest: string;
  };
  readonly configuration: {
    readonly trials: number;
    readonly budget: BenchmarkBudget;
    readonly metric_context: BenchmarkMetricContext;
  };
  readonly systems: readonly BenchmarkSystemReport[];
  readonly observations: readonly BenchmarkAttemptObservation[];
}

export const BENCHMARK_TRACKS: readonly BenchmarkTrack[] = [
  "end_to_end",
  "oracle_intent",
];

export const PROFILE_METRICS = [
  "planning_success",
  "plan_validity",
  "constraint_satisfaction",
  "spatial_efficiency",
  "circulation",
  "stability",
] as const;

export type ProfileMetric = (typeof PROFILE_METRICS)[number];
