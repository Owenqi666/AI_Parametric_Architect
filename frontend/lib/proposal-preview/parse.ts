import type {
  CardinalOrientation,
  DetachedFloorPlanProposal,
  PlanningShowcaseArtifact,
  PreviewConstraint,
  PreviewDesignIntent,
  PreviewRoom,
  PreviewMetricContext,
  PreviewMetricResult,
  PreviewSpatialConstraint,
  RoomOrientation,
  ShowcaseExecution,
  ShowcaseFailure,
  ShowcaseScenarioEvidence,
  ShowcaseScenario,
  SpatialRelation,
} from "./types";

const TOKEN = /^[a-z][a-z0-9_-]*$/;
const ERROR_CODE = /^[A-Z][A-Z0-9_]*$/;
const SHA256 = /^[0-9a-f]{64}$/;
const MAX_SCENARIOS = 8;
const MAX_ROOMS = 64;
const MAX_CONSTRAINTS = 128;
const MAX_TEXT = 16_384;

const CARDINAL = new Set<CardinalOrientation>(["north", "south", "east", "west"]);
const ROOM_ORIENTATIONS = new Set<RoomOrientation>([
  "north",
  "south",
  "east",
  "west",
  "interior",
]);
const RELATIONS = new Set<SpatialRelation>([
  "adjacent_to",
  "near",
  "separated_from",
  "north_of",
  "south_of",
  "east_of",
  "west_of",
]);

export class ProposalPreviewAdmissionError extends Error {
  constructor(message: string, readonly path = "/") {
    super(`${message} (${path})`);
    this.name = "ProposalPreviewAdmissionError";
  }
}

export function parsePlanningShowcase(value: unknown): PlanningShowcaseArtifact {
  const root = objectAt(value, "/");
  exactFields(root, ["schema_version", "artifact_kind", "execution", "scenarios"], "/");
  literal(root.schema_version, "1.0.0", "/schema_version");
  literal(root.artifact_kind, "detached_floor_plan_showcase", "/artifact_kind");
  const execution = parseExecution(root.execution);
  const scenariosValue = arrayAt(root.scenarios, "/scenarios", 1, MAX_SCENARIOS);
  const scenarios = scenariosValue.map((scenario, index) =>
    parseScenario(scenario, `/scenarios/${index}`),
  );
  const ids = scenarios.map((scenario) => scenario.scenario_id);
  if (new Set(ids).size !== ids.length) fail("Scenario IDs must be unique.", "/scenarios");
  return deepFreeze({
    schema_version: "1.0.0",
    artifact_kind: "detached_floor_plan_showcase",
    execution,
    scenarios,
  });
}

function parseExecution(value: unknown): ShowcaseExecution {
  const execution = objectAt(value, "/execution");
  exactFields(execution, ["mode", "intent_parser", "planner"], "/execution");
  literal(execution.mode, "deterministic_offline_replay", "/execution/mode");
  const parser = namedVersion(execution.intent_parser, "/execution/intent_parser");
  const planner = objectAt(execution.planner, "/execution/planner");
  exactFields(
    planner,
    ["name", "version", "strategy", "rules_version", "random_seed"],
    "/execution/planner",
  );
  literal(planner.strategy, "cp-sat-rectilinear-v1", "/execution/planner/strategy");
  const randomSeed = integerAt(planner.random_seed, "/execution/planner/random_seed", 0);
  return {
    mode: "deterministic_offline_replay",
    intent_parser: parser,
    planner: {
      name: boundedText(planner.name, "/execution/planner/name", 128),
      version: boundedText(planner.version, "/execution/planner/version", 64),
      strategy: "cp-sat-rectilinear-v1",
      rules_version: boundedText(planner.rules_version, "/execution/planner/rules_version", 64),
      random_seed: randomSeed,
    },
  };
}

function namedVersion(value: unknown, path: string): { readonly name: string; readonly version: string } {
  const item = objectAt(value, path);
  exactFields(item, ["name", "version"], path);
  return {
    name: boundedText(item.name, `${path}/name`, 128),
    version: boundedText(item.version, `${path}/version`, 64),
  };
}

function parseScenario(value: unknown, path: string): ShowcaseScenario {
  const item = objectAt(value, path);
  exactFields(
    item,
    [
      "scenario_id",
      "title",
      "input_requirement",
      "status",
      "intent",
      "proposal",
      "proposal_digest",
      "failure",
      "evidence",
    ],
    path,
  );
  const scenarioId = tokenAt(item.scenario_id, `${path}/scenario_id`);
  const title = boundedText(item.title, `${path}/title`, 128);
  const requirement = boundedText(item.input_requirement, `${path}/input_requirement`, MAX_TEXT);
  if (item.status === "success") {
    if (item.failure !== null) fail("Successful scenarios cannot contain a failure.", `${path}/failure`);
    const intent = parseIntent(item.intent, `${path}/intent`);
    const proposal = parseProposal(item.proposal, `${path}/proposal`);
    const proposalDigest = boundedText(item.proposal_digest, `${path}/proposal_digest`, 64);
    if (!SHA256.test(proposalDigest)) fail("Proposal digest must be lowercase SHA-256.", `${path}/proposal_digest`);
    if (JSON.stringify(intent) !== JSON.stringify(proposal.intent)) {
      fail("Scenario intent must exactly equal proposal intent.", `${path}/proposal/intent`);
    }
    const evidence = parseEvidence(item.evidence, `${path}/evidence`);
    const cpSatEvidence = evidence.systems.find((system) => system.system_id === "cp-sat-v2");
    if (!cpSatEvidence || cpSatEvidence.proposal_digest !== proposalDigest) {
      fail("Scenario proposal must match its CP-SAT evidence digest.", `${path}/evidence/systems`);
    }
    return {
      scenario_id: scenarioId,
      title,
      input_requirement: requirement,
      status: "success",
      intent,
      proposal,
      proposal_digest: proposalDigest,
      failure: null,
      evidence,
    };
  }
  if (item.status !== "rejected") fail("Scenario status is unsupported.", `${path}/status`);
  if (item.proposal !== null || item.proposal_digest !== null) {
    fail("Rejected scenarios cannot contain proposal output.", `${path}/proposal`);
  }
  if (item.evidence !== null) fail("Rejected scenarios cannot contain metric evidence.", `${path}/evidence`);
  const intent = item.intent === null ? null : parseIntent(item.intent, `${path}/intent`);
  return {
    scenario_id: scenarioId,
    title,
    input_requirement: requirement,
    status: "rejected",
    intent,
    proposal: null,
    proposal_digest: null,
    failure: parseFailure(item.failure, `${path}/failure`),
    evidence: null,
  };
}

function parseEvidence(value: unknown, path: string): ShowcaseScenarioEvidence {
  const item = objectAt(value, path);
  exactFields(item, ["schema_version", "metric_context", "systems"], path);
  literal(item.schema_version, "1.0.0", `${path}/schema_version`);
  const systems = arrayAt(item.systems, `${path}/systems`, 1, 3).map((system, index) => {
    const systemPath = `${path}/systems/${index}`;
    const systemItem = objectAt(system, systemPath);
    exactFields(systemItem, ["system_id", "strategy", "proposal_digest", "metrics"], systemPath);
    const digest = boundedText(systemItem.proposal_digest, `${systemPath}/proposal_digest`, 64);
    if (!SHA256.test(digest)) fail("Proposal digest must be lowercase SHA-256.", `${systemPath}/proposal_digest`);
    const metricsValue = objectAt(systemItem.metrics, `${systemPath}/metrics`);
    exactFields(
      metricsValue,
      ["constraint_satisfaction", "spatial_efficiency", "circulation", "stability"],
      `${systemPath}/metrics`,
    );
    return {
      system_id: tokenAt(systemItem.system_id, `${systemPath}/system_id`),
      strategy: tokenAt(systemItem.strategy, `${systemPath}/strategy`),
      proposal_digest: digest,
      metrics: {
        constraint_satisfaction: parseMetric(metricsValue.constraint_satisfaction, `${systemPath}/metrics/constraint_satisfaction`),
        spatial_efficiency: parseMetric(metricsValue.spatial_efficiency, `${systemPath}/metrics/spatial_efficiency`),
        circulation: parseMetric(metricsValue.circulation, `${systemPath}/metrics/circulation`),
        stability: parseMetric(metricsValue.stability, `${systemPath}/metrics/stability`),
      },
    };
  });
  const ids = systems.map((system) => system.system_id);
  if (new Set(ids).size !== ids.length) fail("Evidence system IDs must be unique.", `${path}/systems`);
  return {
    schema_version: "1.0.0",
    metric_context: parseMetricContext(item.metric_context, `${path}/metric_context`),
    systems,
  };
}

function parseMetric(value: unknown, path: string): PreviewMetricResult {
  const item = objectAt(value, path);
  exactFields(item, ["name", "value", "applicable", "sample_count", "reason"], path);
  const applicable = booleanAt(item.applicable, `${path}/applicable`);
  const sampleCount = integerAt(item.sample_count, `${path}/sample_count`, 0);
  const name = tokenAt(item.name, `${path}/name`);
  if (!applicable) {
    if (item.value !== null || sampleCount !== 0) fail("Non-applicable metric cannot contain samples.", path);
    return {
      name,
      value: null,
      applicable: false,
      sample_count: 0,
      reason: boundedText(item.reason, `${path}/reason`, 128),
    };
  }
  const metricValue = finiteNumber(item.value, `${path}/value`);
  if (metricValue < 0 || metricValue > 1 || sampleCount < 1 || item.reason !== null) {
    fail("Applicable metric must be normalized and sampled.", path);
  }
  return { name, value: metricValue, applicable: true, sample_count: sampleCount, reason: null };
}

function parseMetricContext(value: unknown, path: string): PreviewMetricContext {
  const item = objectAt(value, path);
  exactFields(
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
  const precisionValue = objectAt(item.precision, `${path}/precision`);
  exactFields(precisionValue, ["linear_tolerance", "decimal_places"], `${path}/precision`);
  const minimumRoomAreas = arrayAt(item.minimum_room_areas, `${path}/minimum_room_areas`, 0, MAX_ROOMS).map(
    (entry, index) => {
      const entryPath = `${path}/minimum_room_areas/${index}`;
      const entryValue = objectAt(entry, entryPath);
      exactFields(entryValue, ["room_type", "minimum_area"], entryPath);
      return {
        room_type: tokenAt(entryValue.room_type, `${entryPath}/room_type`),
        minimum_area: positiveNumber(entryValue.minimum_area, `${entryPath}/minimum_area`),
      };
    },
  );
  return {
    context_id: boundedText(item.context_id, `${path}/context_id`, 128),
    minimum_room_areas: minimumRoomAreas,
    default_minimum_room_area: positiveNumber(item.default_minimum_room_area, `${path}/default_minimum_room_area`),
    minimum_adjacency_contact: positiveNumber(item.minimum_adjacency_contact, `${path}/minimum_adjacency_contact`),
    separation_gap: positiveNumber(item.separation_gap, `${path}/separation_gap`),
    near_distance: positiveNumber(item.near_distance, `${path}/near_distance`),
    precision: {
      linear_tolerance: positiveNumber(precisionValue.linear_tolerance, `${path}/precision/linear_tolerance`),
      decimal_places: integerAt(precisionValue.decimal_places, `${path}/precision/decimal_places`, 0),
    },
    max_runs: integerAt(item.max_runs, `${path}/max_runs`, 1),
  };
}

function parseFailure(value: unknown, path: string): ShowcaseFailure {
  const item = objectAt(value, path);
  exactFields(item, ["stage", "code", "path"], path);
  if (item.stage !== "intent" && item.stage !== "plan") {
    fail("Failure stage is unsupported.", `${path}/stage`);
  }
  const code = boundedText(item.code, `${path}/code`, 96);
  if (!ERROR_CODE.test(code)) fail("Failure code must be canonical.", `${path}/code`);
  const failurePath = stringAt(item.path, `${path}/path`);
  if (failurePath !== "" && !failurePath.startsWith("/")) {
    fail("Failure path must be empty or a JSON Pointer.", `${path}/path`);
  }
  return { stage: item.stage, code, path: failurePath };
}

function parseIntent(value: unknown, path: string): PreviewDesignIntent {
  const item = objectAt(value, path);
  const allowed = ["building_type", "area", "rooms", "orientation", "spatial_constraints"];
  const required = ["building_type", "area", "rooms", "orientation"];
  exactAllowedFields(item, allowed, required, path);
  const rooms = arrayAt(item.rooms, `${path}/rooms`, 1, MAX_ROOMS).map((room, index) =>
    tokenAt(room, `${path}/rooms/${index}`),
  );
  const orientation = nullableCardinal(item.orientation, `${path}/orientation`);
  const baseIntent = {
    building_type: tokenAt(item.building_type, `${path}/building_type`),
    area: positiveNumber(item.area, `${path}/area`),
    rooms,
    orientation,
  };
  if ("spatial_constraints" in item) {
    const spatialConstraints = arrayAt(
      item.spatial_constraints,
      `${path}/spatial_constraints`,
      0,
      MAX_CONSTRAINTS,
    ).map((constraint, index) => parseIntentConstraint(constraint, `${path}/spatial_constraints/${index}`));
    return { ...baseIntent, spatial_constraints: spatialConstraints };
  }
  return baseIntent;
}

function parseIntentConstraint(value: unknown, path: string): PreviewSpatialConstraint {
  const item = objectAt(value, path);
  exactFields(item, ["source_room_type", "relation", "target_room_type", "required"], path);
  const source = tokenAt(item.source_room_type, `${path}/source_room_type`);
  const target = tokenAt(item.target_room_type, `${path}/target_room_type`);
  if (source === target) fail("Constraint endpoints must differ.", `${path}/target_room_type`);
  return {
    source_room_type: source,
    relation: relationAt(item.relation, `${path}/relation`),
    target_room_type: target,
    required: booleanAt(item.required, `${path}/required`),
  };
}

function parseProposal(value: unknown, path: string): DetachedFloorPlanProposal {
  const item = objectAt(value, path);
  exactFields(
    item,
    ["schema_version", "strategy", "intent", "orientation", "rooms", "spatial_constraints", "boundary"],
    path,
  );
  literal(item.schema_version, "2.0.0", `${path}/schema_version`);
  const boundaryValue = objectAt(item.boundary, `${path}/boundary`);
  exactFields(boundaryValue, ["width", "height"], `${path}/boundary`);
  const boundary = {
    width: positiveNumber(boundaryValue.width, `${path}/boundary/width`),
    height: positiveNumber(boundaryValue.height, `${path}/boundary/height`),
  };
  const rooms = arrayAt(item.rooms, `${path}/rooms`, 1, MAX_ROOMS).map((room, index) =>
    parseRoom(room, `${path}/rooms/${index}`, boundary),
  );
  const ids = rooms.map((room) => room.plan_id);
  if (new Set(ids).size !== ids.length) fail("Plan IDs must be unique.", `${path}/rooms`);
  rejectOverlaps(rooms, `${path}/rooms`);
  const constraints = arrayAt(
    item.spatial_constraints,
    `${path}/spatial_constraints`,
    0,
    MAX_CONSTRAINTS,
  ).map((constraint, index) =>
    parseConstraint(constraint, `${path}/spatial_constraints/${index}`, new Set(ids)),
  );
  const intent = parseIntent(item.intent, `${path}/intent`);
  if (intent.rooms.length !== rooms.length || intent.rooms.some((room, index) => room !== rooms[index]?.room_type)) {
    fail("Proposal rooms must preserve the intent room sequence.", `${path}/rooms`);
  }
  const orientation = nullableCardinal(item.orientation, `${path}/orientation`);
  if (orientation !== intent.orientation) fail("Proposal orientation must equal intent orientation.", `${path}/orientation`);
  return {
    schema_version: "2.0.0",
    strategy: tokenAt(item.strategy, `${path}/strategy`),
    intent,
    orientation,
    rooms,
    spatial_constraints: constraints,
    boundary,
  };
}

function parseRoom(
  value: unknown,
  path: string,
  boundary: { readonly width: number; readonly height: number },
): PreviewRoom {
  const item = objectAt(value, path);
  exactFields(item, ["plan_id", "room_type", "target_area", "x", "y", "width", "height", "orientation"], path);
  const x = nonNegativeNumber(item.x, `${path}/x`);
  const y = nonNegativeNumber(item.y, `${path}/y`);
  const width = positiveNumber(item.width, `${path}/width`);
  const height = positiveNumber(item.height, `${path}/height`);
  if (x + width > boundary.width || y + height > boundary.height) {
    fail("Room must remain within the detached planning boundary.", path);
  }
  const orientation = stringAt(item.orientation, `${path}/orientation`);
  if (!ROOM_ORIENTATIONS.has(orientation as RoomOrientation)) {
    fail("Room orientation is unsupported.", `${path}/orientation`);
  }
  return {
    plan_id: tokenAt(item.plan_id, `${path}/plan_id`),
    room_type: tokenAt(item.room_type, `${path}/room_type`),
    target_area: positiveNumber(item.target_area, `${path}/target_area`),
    x,
    y,
    width,
    height,
    orientation: orientation as RoomOrientation,
  };
}

function parseConstraint(value: unknown, path: string, roomIds: ReadonlySet<string>): PreviewConstraint {
  const item = objectAt(value, path);
  exactFields(item, ["source_plan_id", "relation", "target_plan_id", "required"], path);
  const source = tokenAt(item.source_plan_id, `${path}/source_plan_id`);
  const target = tokenAt(item.target_plan_id, `${path}/target_plan_id`);
  if (!roomIds.has(source) || !roomIds.has(target) || source === target) {
    fail("Constraint must reference two known, different rooms.", path);
  }
  return {
    source_plan_id: source,
    relation: relationAt(item.relation, `${path}/relation`),
    target_plan_id: target,
    required: booleanAt(item.required, `${path}/required`),
  };
}

function rejectOverlaps(rooms: readonly PreviewRoom[], path: string): void {
  rooms.forEach((left, leftIndex) => {
    rooms.slice(leftIndex + 1).forEach((right) => {
      const overlaps =
        left.x < right.x + right.width &&
        right.x < left.x + left.width &&
        left.y < right.y + right.height &&
        right.y < left.y + left.height;
      if (overlaps) fail("Detached proposal rooms must not overlap.", path);
    });
  });
}

function nullableCardinal(value: unknown, path: string): CardinalOrientation | null {
  if (value === null) return null;
  const orientation = stringAt(value, path);
  if (!CARDINAL.has(orientation as CardinalOrientation)) fail("Orientation is unsupported.", path);
  return orientation as CardinalOrientation;
}

function relationAt(value: unknown, path: string): SpatialRelation {
  const relation = stringAt(value, path);
  if (!RELATIONS.has(relation as SpatialRelation)) fail("Spatial relation is unsupported.", path);
  return relation as SpatialRelation;
}

function tokenAt(value: unknown, path: string): string {
  const token = boundedText(value, path, 128);
  if (!TOKEN.test(token)) fail("Value must be a canonical lowercase token.", path);
  return token;
}

function positiveNumber(value: unknown, path: string): number {
  const number = finiteNumber(value, path);
  if (number <= 0) fail("Value must be positive.", path);
  return number;
}

function nonNegativeNumber(value: unknown, path: string): number {
  const number = finiteNumber(value, path);
  if (number < 0) fail("Value must be non-negative.", path);
  return number;
}

function finiteNumber(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) fail("Value must be a finite number.", path);
  return value;
}

function integerAt(value: unknown, path: string, minimum: number): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < minimum) {
    fail("Value must be a bounded integer.", path);
  }
  return value;
}

function booleanAt(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") fail("Value must be a boolean.", path);
  return value;
}

function boundedText(value: unknown, path: string, maximum: number): string {
  const text = stringAt(value, path);
  if (!text.trim() || text.length > maximum) fail("Text is empty or exceeds its budget.", path);
  return text;
}

function stringAt(value: unknown, path: string): string {
  if (typeof value !== "string") fail("Value must be a string.", path);
  return value;
}

function arrayAt(value: unknown, path: string, minimum: number, maximum: number): unknown[] {
  if (!Array.isArray(value) || value.length < minimum || value.length > maximum) {
    fail("Array is outside its resource budget.", path);
  }
  return value;
}

function objectAt(value: unknown, path: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    fail("Value must be an object.", path);
  }
  return value as Record<string, unknown>;
}

function exactFields(value: Record<string, unknown>, fields: readonly string[], path: string): void {
  exactAllowedFields(value, fields, fields, path);
}

function exactAllowedFields(
  value: Record<string, unknown>,
  allowed: readonly string[],
  required: readonly string[],
  path: string,
): void {
  const keys = Object.keys(value);
  if (keys.some((key) => !allowed.includes(key)) || required.some((key) => !keys.includes(key))) {
    fail("Object has missing or unexpected fields.", path);
  }
}

function literal<T extends string>(value: unknown, expected: T, path: string): T {
  if (value !== expected) fail(`Expected ${expected}.`, path);
  return expected;
}

function fail(message: string, path: string): never {
  throw new ProposalPreviewAdmissionError(message, path);
}

function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    Object.values(value as Record<string, unknown>).forEach((child) => deepFreeze(child));
  }
  return value;
}
