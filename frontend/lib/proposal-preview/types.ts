export type CardinalOrientation = "north" | "south" | "east" | "west";
export type RoomOrientation = CardinalOrientation | "interior";
export type SpatialRelation =
  | "adjacent_to"
  | "near"
  | "separated_from"
  | "north_of"
  | "south_of"
  | "east_of"
  | "west_of";

export interface PreviewSpatialConstraint {
  readonly source_room_type: string;
  readonly relation: SpatialRelation;
  readonly target_room_type: string;
  readonly required: boolean;
}

export interface PreviewDesignIntent {
  readonly building_type: string;
  readonly area: number;
  readonly rooms: readonly string[];
  readonly orientation: CardinalOrientation | null;
  readonly spatial_constraints?: readonly PreviewSpatialConstraint[];
}

export interface PreviewRoom {
  readonly plan_id: string;
  readonly room_type: string;
  readonly target_area: number;
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
  readonly orientation: RoomOrientation;
}

export interface PreviewConstraint {
  readonly source_plan_id: string;
  readonly relation: SpatialRelation;
  readonly target_plan_id: string;
  readonly required: boolean;
}

export interface DetachedFloorPlanProposal {
  readonly schema_version: "2.0.0";
  readonly strategy: string;
  readonly intent: PreviewDesignIntent;
  readonly orientation: CardinalOrientation | null;
  readonly rooms: readonly PreviewRoom[];
  readonly spatial_constraints: readonly PreviewConstraint[];
  readonly boundary: {
    readonly width: number;
    readonly height: number;
  };
}

export interface ShowcaseExecution {
  readonly mode: "deterministic_offline_replay";
  readonly intent_parser: {
    readonly name: string;
    readonly version: string;
  };
  readonly planner: {
    readonly name: string;
    readonly version: string;
    readonly strategy: "cp-sat-rectilinear-v1";
    readonly rules_version: string;
    readonly random_seed: number;
  };
}

export interface ShowcaseFailure {
  readonly stage: "intent" | "plan";
  readonly code: string;
  readonly path: string;
}

export interface PreviewMetricResult {
  readonly name: string;
  readonly value: number | null;
  readonly applicable: boolean;
  readonly sample_count: number;
  readonly reason: string | null;
}

export interface PreviewMetricContext {
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

export interface ShowcaseScenarioEvidence {
  readonly schema_version: "1.0.0";
  readonly metric_context: PreviewMetricContext;
  readonly systems: readonly {
    readonly system_id: string;
    readonly strategy: string;
    readonly proposal_digest: string;
    readonly metrics: {
      readonly constraint_satisfaction: PreviewMetricResult;
      readonly spatial_efficiency: PreviewMetricResult;
      readonly circulation: PreviewMetricResult;
      readonly stability: PreviewMetricResult;
    };
  }[];
}

interface ShowcaseScenarioBase {
  readonly scenario_id: string;
  readonly title: string;
  readonly input_requirement: string;
}

export interface SuccessfulShowcaseScenario extends ShowcaseScenarioBase {
  readonly status: "success";
  readonly intent: PreviewDesignIntent;
  readonly proposal: DetachedFloorPlanProposal;
  readonly proposal_digest: string;
  readonly failure: null;
  readonly evidence: ShowcaseScenarioEvidence;
}

export interface RejectedShowcaseScenario extends ShowcaseScenarioBase {
  readonly status: "rejected";
  readonly intent: PreviewDesignIntent | null;
  readonly proposal: null;
  readonly proposal_digest: null;
  readonly failure: ShowcaseFailure;
  readonly evidence: null;
}

export type ShowcaseScenario = SuccessfulShowcaseScenario | RejectedShowcaseScenario;

export interface PlanningShowcaseArtifact {
  readonly schema_version: "1.0.0";
  readonly artifact_kind: "detached_floor_plan_showcase";
  readonly execution: ShowcaseExecution;
  readonly scenarios: readonly ShowcaseScenario[];
}
