import {
  BENCHMARK_REPORT_SCHEMA_VERSION,
  type BenchmarkAttemptObservation,
  type BenchmarkBudget,
  type BenchmarkExecutionMode,
  type BenchmarkFailure,
  type BenchmarkMetricContext,
  type BenchmarkMetricSummary,
  type BenchmarkReport,
  type BenchmarkRuntimeSummary,
  type BenchmarkSystemDescriptor,
  type BenchmarkSystemReport,
  type BenchmarkTrack,
  type BenchmarkTrackObservation,
  type BenchmarkTrackSummary,
} from "./types";

export const MAX_BENCHMARK_REPORT_BYTES = 4 * 1024 * 1024;
export const MAX_BENCHMARK_CASES = 256;
export const MAX_BENCHMARK_SYSTEMS = 8;
export const MAX_BENCHMARK_TRIALS = 64;
export const MAX_BENCHMARK_ATTEMPTS = 4096;

const MAX_CONTEXT_ROOM_AREAS = 128;
const IDENTIFIER = /^[a-z][a-z0-9_.:-]*$/;
const ROOM_TYPE = /^[a-z][a-z0-9_-]*$/;
const ERROR_CODE = /^[A-Z][A-Z0-9_]*$/;
const SHA256 = /^[0-9a-f]{64}$/;

type JsonRecord = Record<string, unknown>;

export class BenchmarkReportContractError extends Error {
  readonly path: string;

  constructor(message: string, path = "/") {
    super(message);
    this.name = "BenchmarkReportContractError";
    this.path = path;
  }
}

function record(value: unknown, path: string): JsonRecord {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new BenchmarkReportContractError("Expected an object.", path);
  }
  return value as JsonRecord;
}

function exactKeys(value: JsonRecord, expected: readonly string[], path: string): void {
  const actual = Object.keys(value).sort();
  const canonical = [...expected].sort();
  if (actual.length !== canonical.length || actual.some((key, index) => key !== canonical[index])) {
    throw new BenchmarkReportContractError(
      "Object fields do not match BenchmarkReport 1.0.0.",
      path,
    );
  }
}

function array(value: unknown, path: string): readonly unknown[] {
  if (!Array.isArray(value)) throw new BenchmarkReportContractError("Expected an array.", path);
  return value;
}

function literal<T extends string>(value: unknown, expected: T, path: string): T {
  if (value !== expected) {
    throw new BenchmarkReportContractError(`Expected ${JSON.stringify(expected)}.`, path);
  }
  return expected;
}

function oneOf<T extends string>(value: unknown, values: readonly T[], path: string): T {
  if (typeof value !== "string" || !values.includes(value as T)) {
    throw new BenchmarkReportContractError("Unsupported literal value.", path);
  }
  return value as T;
}

function boolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") throw new BenchmarkReportContractError("Expected a boolean.", path);
  return value;
}

function text(value: unknown, path: string, maximum = 256): string {
  if (
    typeof value !== "string" ||
    value.trim().length === 0 ||
    value.length > maximum
  ) {
    throw new BenchmarkReportContractError("Expected bounded non-empty text.", path);
  }
  return value;
}

function nullableText(value: unknown, path: string): string | null {
  return value === null ? null : text(value, path);
}

function identifier(value: unknown, path: string): string {
  if (typeof value !== "string" || value.length > 128 || !IDENTIFIER.test(value)) {
    throw new BenchmarkReportContractError("Expected a canonical identifier.", path);
  }
  return value;
}

function digest(value: unknown, path: string): string {
  if (typeof value !== "string" || !SHA256.test(value)) {
    throw new BenchmarkReportContractError("Expected a lowercase SHA-256 digest.", path);
  }
  return value;
}

function finite(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new BenchmarkReportContractError("Expected a finite number.", path);
  }
  return value;
}

function positiveFinite(value: unknown, path: string): number {
  const result = finite(value, path);
  if (result <= 0) throw new BenchmarkReportContractError("Expected a positive number.", path);
  return result;
}

function normalized(value: unknown, path: string): number {
  const result = finite(value, path);
  if (result < 0 || result > 1) {
    throw new BenchmarkReportContractError("Expected a normalized number.", path);
  }
  return result;
}

function integer(value: unknown, path: string, minimum: number, maximum = Number.MAX_SAFE_INTEGER): number {
  if (!Number.isSafeInteger(value) || (value as number) < minimum || (value as number) > maximum) {
    throw new BenchmarkReportContractError("Expected a bounded safe integer.", path);
  }
  return value as number;
}

function nullableInteger(value: unknown, path: string): number | null {
  return value === null ? null : integer(value, path, 0);
}

function nullableNormalized(value: unknown, path: string): number | null {
  return value === null ? null : normalized(value, path);
}

function coverage(value: unknown, covered: number, attempts: number, path: string): number {
  const result = normalized(value, path);
  if (result !== covered / attempts) {
    throw new BenchmarkReportContractError("Coverage does not match its explicit denominator.", path);
  }
  return result;
}

function parseBudget(value: unknown, path: string): BenchmarkBudget {
  const item = record(value, path);
  exactKeys(item, ["max_cases", "max_systems", "max_trials", "max_attempts"], path);
  return {
    max_cases: integer(item.max_cases, `${path}/max_cases`, 1, MAX_BENCHMARK_CASES),
    max_systems: integer(item.max_systems, `${path}/max_systems`, 1, MAX_BENCHMARK_SYSTEMS),
    max_trials: integer(item.max_trials, `${path}/max_trials`, 1, MAX_BENCHMARK_TRIALS),
    max_attempts: integer(item.max_attempts, `${path}/max_attempts`, 1, MAX_BENCHMARK_ATTEMPTS),
  };
}

function parseMetricContext(value: unknown, path: string): BenchmarkMetricContext {
  const item = record(value, path);
  exactKeys(
    item,
    [
      "context_id",
      "minimum_room_areas",
      "default_minimum_room_area",
      "minimum_adjacency_contact",
      "separation_gap",
      "near_distance",
      "precision",
      "max_runs",
    ],
    path,
  );
  const areaValues = array(item.minimum_room_areas, `${path}/minimum_room_areas`);
  if (areaValues.length > MAX_CONTEXT_ROOM_AREAS) {
    throw new BenchmarkReportContractError(
      "Metric context room-area budget exceeded.",
      `${path}/minimum_room_areas`,
    );
  }
  let previousRoomType = "";
  const minimumRoomAreas = areaValues.map((value, index) => {
    const areaPath = `${path}/minimum_room_areas/${index}`;
    const area = record(value, areaPath);
    exactKeys(area, ["room_type", "minimum_area"], areaPath);
    const roomType = text(area.room_type, `${areaPath}/room_type`, 128);
    if (!ROOM_TYPE.test(roomType) || roomType <= previousRoomType) {
      throw new BenchmarkReportContractError(
        "Room-area entries must use sorted unique canonical room types.",
        `${areaPath}/room_type`,
      );
    }
    previousRoomType = roomType;
    return {
      room_type: roomType,
      minimum_area: positiveFinite(area.minimum_area, `${areaPath}/minimum_area`),
    };
  });
  const precisionPath = `${path}/precision`;
  const precision = record(item.precision, precisionPath);
  exactKeys(precision, ["linear_tolerance", "decimal_places"], precisionPath);
  const linearTolerance = finite(precision.linear_tolerance, `${precisionPath}/linear_tolerance`);
  if (linearTolerance < 1e-12 || linearTolerance > 1e-2) {
    throw new BenchmarkReportContractError(
      "linear_tolerance is outside the supported precision range.",
      `${precisionPath}/linear_tolerance`,
    );
  }
  return {
    context_id: identifier(item.context_id, `${path}/context_id`),
    minimum_room_areas: minimumRoomAreas,
    default_minimum_room_area: positiveFinite(
      item.default_minimum_room_area,
      `${path}/default_minimum_room_area`,
    ),
    minimum_adjacency_contact: positiveFinite(
      item.minimum_adjacency_contact,
      `${path}/minimum_adjacency_contact`,
    ),
    separation_gap: positiveFinite(item.separation_gap, `${path}/separation_gap`),
    near_distance: positiveFinite(item.near_distance, `${path}/near_distance`),
    precision: {
      linear_tolerance: linearTolerance,
      decimal_places: integer(precision.decimal_places, `${precisionPath}/decimal_places`, 0, 12),
    },
    max_runs: integer(item.max_runs, `${path}/max_runs`, 1, MAX_BENCHMARK_TRIALS),
  };
}

function parseNamedVersion(value: unknown, path: string): { readonly name: string; readonly version: string } {
  const item = record(value, path);
  exactKeys(item, ["name", "version"], path);
  return {
    name: text(item.name, `${path}/name`),
    version: text(item.version, `${path}/version`),
  };
}

function parseDescriptor(value: unknown, path: string): BenchmarkSystemDescriptor {
  const item = record(value, path);
  exactKeys(
    item,
    [
      "system_id",
      "system_version",
      "intent_agent",
      "floor_plan_agent",
      "planner_configuration",
      "execution_mode",
      "deterministic",
      "provider",
      "model",
      "prompt_version",
    ],
    path,
  );
  const plannerPath = `${path}/planner_configuration`;
  const planner = record(item.planner_configuration, plannerPath);
  exactKeys(planner, ["strategy", "rules_version", "random_seed"], plannerPath);
  const executionMode = oneOf<BenchmarkExecutionMode>(
    item.execution_mode,
    ["deterministic", "real_nondeterministic"],
    `${path}/execution_mode`,
  );
  const deterministic = boolean(item.deterministic, `${path}/deterministic`);
  if (deterministic !== (executionMode === "deterministic")) {
    throw new BenchmarkReportContractError(
      "deterministic must agree with execution_mode.",
      `${path}/deterministic`,
    );
  }
  const randomSeed = nullableInteger(planner.random_seed, `${plannerPath}/random_seed`);
  if (executionMode === "deterministic" && randomSeed === null) {
    throw new BenchmarkReportContractError(
      "Deterministic systems require a random seed.",
      `${plannerPath}/random_seed`,
    );
  }
  const provider = nullableText(item.provider, `${path}/provider`);
  const model = nullableText(item.model, `${path}/model`);
  if (executionMode === "real_nondeterministic" && (provider === null || model === null)) {
    throw new BenchmarkReportContractError(
      "Real nondeterministic systems must identify provider and model.",
      path,
    );
  }
  return {
    system_id: identifier(item.system_id, `${path}/system_id`),
    system_version: text(item.system_version, `${path}/system_version`),
    intent_agent: parseNamedVersion(item.intent_agent, `${path}/intent_agent`),
    floor_plan_agent: parseNamedVersion(item.floor_plan_agent, `${path}/floor_plan_agent`),
    planner_configuration: {
      strategy: text(planner.strategy, `${plannerPath}/strategy`),
      rules_version: text(planner.rules_version, `${plannerPath}/rules_version`),
      random_seed: randomSeed,
    },
    execution_mode: executionMode,
    deterministic,
    provider,
    model,
    prompt_version: nullableText(item.prompt_version, `${path}/prompt_version`),
  };
}

function parseMetric(
  value: unknown,
  path: string,
  expectedName: string,
  attemptCount: number,
  binary: boolean,
): BenchmarkMetricSummary {
  const item = record(value, path);
  exactKeys(
    item,
    [
      "name",
      "value",
      "applicable",
      "attempt_count",
      "covered_attempt_count",
      "sample_count",
      "coverage",
      "successes",
      "reason",
    ],
    path,
  );
  literal(item.name, expectedName, `${path}/name`);
  const attempts = integer(item.attempt_count, `${path}/attempt_count`, 1, MAX_BENCHMARK_ATTEMPTS);
  if (attempts !== attemptCount) {
    throw new BenchmarkReportContractError("Metric denominator is inconsistent.", `${path}/attempt_count`);
  }
  const covered = integer(
    item.covered_attempt_count,
    `${path}/covered_attempt_count`,
    0,
    attempts,
  );
  const samples = integer(item.sample_count, `${path}/sample_count`, 0, MAX_BENCHMARK_ATTEMPTS);
  const metricValue = nullableNormalized(item.value, `${path}/value`);
  const applicable = boolean(item.applicable, `${path}/applicable`);
  const successes = nullableInteger(item.successes, `${path}/successes`);
  const reason = nullableText(item.reason, `${path}/reason`);
  if (applicable !== (metricValue !== null)) {
    throw new BenchmarkReportContractError("Metric applicability is inconsistent.", `${path}/applicable`);
  }
  if (metricValue === null) {
    if (covered !== 0 || samples !== 0 || successes !== null || reason === null) {
      throw new BenchmarkReportContractError("N/A metrics require zero coverage and a reason.", path);
    }
  } else {
    if (covered < 1 || samples < 1 || reason !== null) {
      throw new BenchmarkReportContractError("Applicable metrics require covered samples.", path);
    }
    if (successes !== null && successes > samples) {
      throw new BenchmarkReportContractError("Metric successes exceed samples.", `${path}/successes`);
    }
  }
  if (binary) {
    if (
      metricValue === null ||
      covered !== attempts ||
      samples !== attempts ||
      successes === null ||
      metricValue !== successes / attempts
    ) {
      throw new BenchmarkReportContractError(
        "Binary metrics must retain every attempt and exact success count.",
        path,
      );
    }
  }
  return {
    name: expectedName,
    value: metricValue,
    applicable,
    attempt_count: attempts,
    covered_attempt_count: covered,
    sample_count: samples,
    coverage: coverage(item.coverage, covered, attempts, `${path}/coverage`),
    successes,
    reason,
  };
}

function parseRuntime(
  value: unknown,
  path: string,
  expectedName: string,
  attemptCount: number,
): BenchmarkRuntimeSummary {
  const item = record(value, path);
  exactKeys(
    item,
    [
      "name",
      "applicable",
      "attempt_count",
      "covered_attempt_count",
      "sample_count",
      "coverage",
      "minimum_ns",
      "median_ns",
      "p95_ns",
      "maximum_ns",
      "total_ns",
      "reason",
    ],
    path,
  );
  literal(item.name, expectedName, `${path}/name`);
  const attempts = integer(item.attempt_count, `${path}/attempt_count`, 1, MAX_BENCHMARK_ATTEMPTS);
  if (attempts !== attemptCount) {
    throw new BenchmarkReportContractError("Runtime denominator is inconsistent.", `${path}/attempt_count`);
  }
  const covered = integer(
    item.covered_attempt_count,
    `${path}/covered_attempt_count`,
    0,
    attempts,
  );
  const samples = integer(item.sample_count, `${path}/sample_count`, 0, MAX_BENCHMARK_ATTEMPTS);
  if (samples !== covered) {
    throw new BenchmarkReportContractError("Runtime sample and coverage counts differ.", path);
  }
  const values = {
    minimum_ns: nullableInteger(item.minimum_ns, `${path}/minimum_ns`),
    median_ns: nullableInteger(item.median_ns, `${path}/median_ns`),
    p95_ns: nullableInteger(item.p95_ns, `${path}/p95_ns`),
    maximum_ns: nullableInteger(item.maximum_ns, `${path}/maximum_ns`),
    total_ns: nullableInteger(item.total_ns, `${path}/total_ns`),
  };
  const applicable = boolean(item.applicable, `${path}/applicable`);
  const reason = nullableText(item.reason, `${path}/reason`);
  if (applicable !== (samples > 0)) {
    throw new BenchmarkReportContractError("Runtime applicability is inconsistent.", `${path}/applicable`);
  }
  if (samples === 0) {
    if (Object.values(values).some((entry) => entry !== null) || reason === null) {
      throw new BenchmarkReportContractError("N/A runtime requires null values and a reason.", path);
    }
  } else {
    if (Object.values(values).some((entry) => entry === null) || reason !== null) {
      throw new BenchmarkReportContractError("Sampled runtime requires complete quantiles.", path);
    }
    const minimum = values.minimum_ns!;
    const median = values.median_ns!;
    const p95 = values.p95_ns!;
    const maximum = values.maximum_ns!;
    const total = values.total_ns!;
    if (!(minimum <= median && median <= p95 && p95 <= maximum) || total < maximum) {
      throw new BenchmarkReportContractError("Runtime quantiles or total are inconsistent.", path);
    }
  }
  return {
    name: expectedName,
    applicable,
    attempt_count: attempts,
    covered_attempt_count: covered,
    sample_count: samples,
    coverage: coverage(item.coverage, covered, attempts, `${path}/coverage`),
    ...values,
    reason,
  };
}

function parseTrackSummary(
  value: unknown,
  path: string,
  expectedTrack: BenchmarkTrack,
  attemptCount: number,
): BenchmarkTrackSummary {
  const item = record(value, path);
  exactKeys(item, ["track", "metrics", "runtime_ns"], path);
  literal(item.track, expectedTrack, `${path}/track`);
  const metricsPath = `${path}/metrics`;
  const metrics = record(item.metrics, metricsPath);
  exactKeys(
    metrics,
    [
      "planning_success",
      "plan_validity",
      "constraint_satisfaction",
      "spatial_efficiency",
      "circulation",
      "stability",
    ],
    metricsPath,
  );
  const runtimePath = `${path}/runtime_ns`;
  const runtime = record(item.runtime_ns, runtimePath);
  exactKeys(runtime, ["parse", "plan", "total"], runtimePath);
  const result: BenchmarkTrackSummary = {
    track: expectedTrack,
    metrics: {
      planning_success: parseMetric(
        metrics.planning_success,
        `${metricsPath}/planning_success`,
        "planning_success",
        attemptCount,
        true,
      ),
      plan_validity: parseMetric(
        metrics.plan_validity,
        `${metricsPath}/plan_validity`,
        "plan_validity",
        attemptCount,
        true,
      ),
      constraint_satisfaction: parseMetric(
        metrics.constraint_satisfaction,
        `${metricsPath}/constraint_satisfaction`,
        "constraint_satisfaction_score",
        attemptCount,
        false,
      ),
      spatial_efficiency: parseMetric(
        metrics.spatial_efficiency,
        `${metricsPath}/spatial_efficiency`,
        "spatial_efficiency_score",
        attemptCount,
        false,
      ),
      circulation: parseMetric(
        metrics.circulation,
        `${metricsPath}/circulation`,
        "circulation_score",
        attemptCount,
        false,
      ),
      stability: parseMetric(
        metrics.stability,
        `${metricsPath}/stability`,
        "plan_stability_score",
        attemptCount,
        false,
      ),
    },
    runtime_ns: {
      parse: parseRuntime(runtime.parse, `${runtimePath}/parse`, "parse_runtime_ns", attemptCount),
      plan: parseRuntime(runtime.plan, `${runtimePath}/plan`, "plan_runtime_ns", attemptCount),
      total: parseRuntime(runtime.total, `${runtimePath}/total`, "total_runtime_ns", attemptCount),
    },
  };
  if (expectedTrack === "oracle_intent" && result.runtime_ns.parse.applicable) {
    throw new BenchmarkReportContractError("Oracle-intent tracks cannot contain parse timing.", `${runtimePath}/parse`);
  }
  if (!result.runtime_ns.total.applicable || result.runtime_ns.total.covered_attempt_count !== attemptCount) {
    throw new BenchmarkReportContractError("Total runtime must cover every attempt.", `${runtimePath}/total`);
  }
  return result;
}

function parseSystem(value: unknown, path: string, expectedAttempts: number): BenchmarkSystemReport {
  const item = record(value, path);
  exactKeys(item, ["descriptor", "attempt_count", "intent_extraction_accuracy", "tracks"], path);
  const attemptCount = integer(item.attempt_count, `${path}/attempt_count`, 1, MAX_BENCHMARK_ATTEMPTS);
  if (attemptCount !== expectedAttempts) {
    throw new BenchmarkReportContractError("System attempt count is inconsistent.", `${path}/attempt_count`);
  }
  const tracksPath = `${path}/tracks`;
  const tracks = record(item.tracks, tracksPath);
  exactKeys(tracks, ["end_to_end", "oracle_intent"], tracksPath);
  return {
    descriptor: parseDescriptor(item.descriptor, `${path}/descriptor`),
    attempt_count: attemptCount,
    intent_extraction_accuracy: parseMetric(
      item.intent_extraction_accuracy,
      `${path}/intent_extraction_accuracy`,
      "intent_extraction_accuracy",
      attemptCount,
      true,
    ),
    tracks: {
      end_to_end: parseTrackSummary(
        tracks.end_to_end,
        `${tracksPath}/end_to_end`,
        "end_to_end",
        attemptCount,
      ),
      oracle_intent: parseTrackSummary(
        tracks.oracle_intent,
        `${tracksPath}/oracle_intent`,
        "oracle_intent",
        attemptCount,
      ),
    },
  };
}

function parseFailure(value: unknown, path: string): BenchmarkFailure | null {
  if (value === null) return null;
  const item = record(value, path);
  exactKeys(item, ["stage", "code", "path"], path);
  const code = text(item.code, `${path}/code`, 128);
  if (!ERROR_CODE.test(code)) {
    throw new BenchmarkReportContractError("Failure code is not canonical.", `${path}/code`);
  }
  if (typeof item.path !== "string" || item.path.length > 512 || (item.path && !item.path.startsWith("/"))) {
    throw new BenchmarkReportContractError("Failure path must be a bounded JSON pointer.", `${path}/path`);
  }
  return {
    stage: oneOf(item.stage, ["intent", "plan"], `${path}/stage`),
    code,
    path: item.path,
  };
}

function parseTrackObservation(
  value: unknown,
  path: string,
  expectedTrack: BenchmarkTrack,
): BenchmarkTrackObservation {
  const item = record(value, path);
  exactKeys(
    item,
    ["track", "planning_succeeded", "plan_valid", "proposal_digest", "runtime_ns", "failure"],
    path,
  );
  literal(item.track, expectedTrack, `${path}/track`);
  const planningSucceeded = boolean(item.planning_succeeded, `${path}/planning_succeeded`);
  const planValid = boolean(item.plan_valid, `${path}/plan_valid`);
  if (planValid && !planningSucceeded) {
    throw new BenchmarkReportContractError("A valid plan requires successful planning.", path);
  }
  const proposalDigest = item.proposal_digest === null
    ? null
    : digest(item.proposal_digest, `${path}/proposal_digest`);
  const failure = parseFailure(item.failure, `${path}/failure`);
  if (planningSucceeded ? proposalDigest === null || failure !== null : proposalDigest !== null) {
    throw new BenchmarkReportContractError("Proposal digest/failure state is inconsistent.", path);
  }
  const runtimePath = `${path}/runtime_ns`;
  const runtime = record(item.runtime_ns, runtimePath);
  exactKeys(runtime, ["parse", "plan", "total"], runtimePath);
  const parse = nullableInteger(runtime.parse, `${runtimePath}/parse`);
  const plan = nullableInteger(runtime.plan, `${runtimePath}/plan`);
  const total = integer(runtime.total, `${runtimePath}/total`, 0);
  if (expectedTrack === "end_to_end" ? parse === null : parse !== null) {
    throw new BenchmarkReportContractError("Track parse runtime is inconsistent.", `${runtimePath}/parse`);
  }
  if (total !== (parse ?? 0) + (plan ?? 0)) {
    throw new BenchmarkReportContractError("Total runtime does not equal measured stages.", `${runtimePath}/total`);
  }
  if (planningSucceeded && plan === null) {
    throw new BenchmarkReportContractError("Successful planning requires plan timing.", `${runtimePath}/plan`);
  }
  if (failure?.stage === "intent" && plan !== null) {
    throw new BenchmarkReportContractError("Intent failure cannot retain plan timing.", `${runtimePath}/plan`);
  }
  if (failure?.stage === "plan" && plan === null) {
    throw new BenchmarkReportContractError("Plan failure requires plan timing.", `${runtimePath}/plan`);
  }
  return {
    track: expectedTrack,
    planning_succeeded: planningSucceeded,
    plan_valid: planValid,
    proposal_digest: proposalDigest,
    runtime_ns: { parse, plan, total },
    failure,
  };
}

function parseObservation(value: unknown, path: string): BenchmarkAttemptObservation {
  const item = record(value, path);
  exactKeys(item, ["case_id", "system_id", "trial_index", "intent_exact", "tracks"], path);
  const tracksPath = `${path}/tracks`;
  const tracks = record(item.tracks, tracksPath);
  exactKeys(tracks, ["end_to_end", "oracle_intent"], tracksPath);
  return {
    case_id: identifier(item.case_id, `${path}/case_id`),
    system_id: identifier(item.system_id, `${path}/system_id`),
    trial_index: integer(item.trial_index, `${path}/trial_index`, 0, MAX_BENCHMARK_TRIALS - 1),
    intent_exact: boolean(item.intent_exact, `${path}/intent_exact`),
    tracks: {
      end_to_end: parseTrackObservation(
        tracks.end_to_end,
        `${tracksPath}/end_to_end`,
        "end_to_end",
      ),
      oracle_intent: parseTrackObservation(
        tracks.oracle_intent,
        `${tracksPath}/oracle_intent`,
        "oracle_intent",
      ),
    },
  };
}

function requireAggregateConsistency(
  systems: readonly BenchmarkSystemReport[],
  observations: readonly BenchmarkAttemptObservation[],
): void {
  for (const system of systems) {
    const values = observations.filter(
      (observation) => observation.system_id === system.descriptor.system_id,
    );
    const intentSuccesses = values.filter((observation) => observation.intent_exact).length;
    if (system.intent_extraction_accuracy.successes !== intentSuccesses) {
      throw new BenchmarkReportContractError(
        "Intent accuracy does not match observations.",
        "/systems",
      );
    }
    for (const track of ["end_to_end", "oracle_intent"] as const) {
      const summary = system.tracks[track];
      const planningSuccesses = values.filter(
        (observation) => observation.tracks[track].planning_succeeded,
      ).length;
      const validSuccesses = values.filter(
        (observation) => observation.tracks[track].plan_valid,
      ).length;
      if (
        summary.metrics.planning_success.successes !== planningSuccesses ||
        summary.metrics.plan_validity.successes !== validSuccesses
      ) {
        throw new BenchmarkReportContractError(
          "Track binary metrics do not match observations.",
          "/systems",
        );
      }
    }
  }
}

function deepFreeze<T>(value: T): T {
  if (typeof value !== "object" || value === null || Object.isFrozen(value)) return value;
  for (const child of Object.values(value as Record<string, unknown>)) deepFreeze(child);
  return Object.freeze(value);
}

export function parseBenchmarkReport(value: unknown): BenchmarkReport {
  const root = record(value, "/");
  exactKeys(root, ["schema_version", "dataset", "annotations", "configuration", "systems", "observations"], "/");
  literal(root.schema_version, BENCHMARK_REPORT_SCHEMA_VERSION, "/schema_version");

  const dataset = record(root.dataset, "/dataset");
  exactKeys(dataset, ["dataset_id", "dataset_version", "digest", "case_count"], "/dataset");
  const annotations = record(root.annotations, "/annotations");
  exactKeys(
    annotations,
    ["annotation_set_id", "annotation_set_version", "digest"],
    "/annotations",
  );
  const configuration = record(root.configuration, "/configuration");
  exactKeys(configuration, ["trials", "budget", "metric_context"], "/configuration");
  const budget = parseBudget(configuration.budget, "/configuration/budget");
  const caseCount = integer(dataset.case_count, "/dataset/case_count", 1, MAX_BENCHMARK_CASES);
  const trials = integer(configuration.trials, "/configuration/trials", 1, MAX_BENCHMARK_TRIALS);
  if (caseCount > budget.max_cases || trials > budget.max_trials) {
    throw new BenchmarkReportContractError("Report exceeds its declared budget.", "/configuration");
  }
  const metricContext = parseMetricContext(
    configuration.metric_context,
    "/configuration/metric_context",
  );
  if (trials > metricContext.max_runs) {
    throw new BenchmarkReportContractError(
      "Trials exceed the metric-context run budget.",
      "/configuration/trials",
    );
  }

  const systemValues = array(root.systems, "/systems");
  if (systemValues.length === 0 || systemValues.length > budget.max_systems) {
    throw new BenchmarkReportContractError("System count exceeds the report budget.", "/systems");
  }
  const expectedAttempts = caseCount * trials;
  const systems = systemValues.map((system, index) =>
    parseSystem(system, `/systems/${index}`, expectedAttempts),
  );
  const systemIds = systems.map((system) => system.descriptor.system_id);
  if (new Set(systemIds).size !== systemIds.length) {
    throw new BenchmarkReportContractError("System IDs must be unique.", "/systems");
  }

  const observationValues = array(root.observations, "/observations");
  const expectedObservationCount = expectedAttempts * systems.length;
  if (
    expectedObservationCount > budget.max_attempts ||
    expectedObservationCount > MAX_BENCHMARK_ATTEMPTS ||
    observationValues.length !== expectedObservationCount
  ) {
    throw new BenchmarkReportContractError(
      "Observation count does not match the complete attempt matrix.",
      "/observations",
    );
  }
  const observations = observationValues.map((observation, index) =>
    parseObservation(observation, `/observations/${index}`),
  );
  const systemIdSet = new Set(systemIds);
  const keys = new Set<string>();
  const caseIds = new Set<string>();
  for (const observation of observations) {
    if (!systemIdSet.has(observation.system_id)) {
      throw new BenchmarkReportContractError("Observation references an unknown system.", "/observations");
    }
    if (observation.trial_index >= trials) {
      throw new BenchmarkReportContractError("Observation trial is out of range.", "/observations");
    }
    const key = `${observation.case_id}\u0000${observation.system_id}\u0000${observation.trial_index}`;
    if (keys.has(key)) {
      throw new BenchmarkReportContractError("Observation keys must be unique.", "/observations");
    }
    keys.add(key);
    caseIds.add(observation.case_id);
  }
  if (caseIds.size !== caseCount) {
    throw new BenchmarkReportContractError("Observation case coverage is incomplete.", "/observations");
  }
  for (const caseId of caseIds) {
    for (const systemId of systemIds) {
      for (let trial = 0; trial < trials; trial += 1) {
        if (!keys.has(`${caseId}\u0000${systemId}\u0000${trial}`)) {
          throw new BenchmarkReportContractError(
            "Observations do not cover every configured attempt.",
            "/observations",
          );
        }
      }
    }
  }
  requireAggregateConsistency(systems, observations);

  return deepFreeze({
    schema_version: BENCHMARK_REPORT_SCHEMA_VERSION,
    dataset: {
      dataset_id: identifier(dataset.dataset_id, "/dataset/dataset_id"),
      dataset_version: text(dataset.dataset_version, "/dataset/dataset_version"),
      digest: digest(dataset.digest, "/dataset/digest"),
      case_count: caseCount,
    },
    annotations: {
      annotation_set_id: identifier(
        annotations.annotation_set_id,
        "/annotations/annotation_set_id",
      ),
      annotation_set_version: text(
        annotations.annotation_set_version,
        "/annotations/annotation_set_version",
      ),
      digest: digest(annotations.digest, "/annotations/digest"),
    },
    configuration: { trials, budget, metric_context: metricContext },
    systems,
    observations,
  });
}
