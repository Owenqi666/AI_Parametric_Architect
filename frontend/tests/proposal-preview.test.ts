import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { parseRenderIr } from "../lib/render-ir/parse";
import {
  parsePlanningShowcase,
  ProposalPreviewAdmissionError,
} from "../lib/proposal-preview/parse";

function rawShowcase(): Record<string, unknown> {
  return JSON.parse(
    readFileSync(resolve(process.cwd(), "public/examples/planning-showcase.preview-1.0.0.json"), "utf8"),
  ) as Record<string, unknown>;
}

describe("detached proposal preview admission", () => {
  it("admits and deeply freezes the generated offline artifact", () => {
    const artifact = parsePlanningShowcase(rawShowcase());

    expect(artifact.schema_version).toBe("1.0.0");
    expect(artifact.artifact_kind).toBe("detached_floor_plan_showcase");
    expect(artifact.scenarios).toHaveLength(3);
    expect(Object.isFrozen(artifact)).toBe(true);
    expect(Object.isFrozen(artifact.scenarios)).toBe(true);
    const solved = artifact.scenarios.find((scenario) => scenario.status === "success");
    expect(solved?.proposal.schema_version).toBe("2.0.0");
    expect(Object.isFrozen(solved?.proposal.rooms)).toBe(true);
    expect(solved?.evidence.systems[0]?.metrics.stability.applicable).toBe(false);
  });

  it("keeps Proposal Preview and World Model Render IR mutually inadmissible", () => {
    const raw = rawShowcase();
    expect(() => parseRenderIr(raw)).toThrow();

    const renderIr = JSON.parse(
      readFileSync(resolve(process.cwd(), "public/examples/simple-house.render-ir.json"), "utf8"),
    ) as unknown;
    expect(() => parsePlanningShowcase(renderIr)).toThrow(ProposalPreviewAdmissionError);
  });

  it("rejects unexpected fields and geometry overlap", () => {
    const unexpected = rawShowcase();
    unexpected.authoritative_model_id = "mdl_forbidden";
    expect(() => parsePlanningShowcase(unexpected)).toThrow(/unexpected fields/);

    const overlapping = rawShowcase();
    const scenarios = overlapping.scenarios as Record<string, unknown>[];
    const success = scenarios.find((scenario) => scenario.status === "success");
    const proposal = success?.proposal as Record<string, unknown>;
    const rooms = proposal.rooms as Record<string, unknown>[];
    if (rooms[0] && rooms[1]) {
      rooms[1].x = rooms[0].x;
      rooms[1].y = rooms[0].y;
    }
    expect(() => parsePlanningShowcase(overlapping)).toThrow(/must not overlap/);
  });

  it("requires rejected scenarios to remain output-free", () => {
    const raw = rawShowcase();
    const scenarios = raw.scenarios as Record<string, unknown>[];
    const rejected = scenarios.find((scenario) => scenario.status === "rejected");
    rejected!.proposal_digest = "0".repeat(64);
    expect(() => parsePlanningShowcase(raw)).toThrow(/cannot contain proposal output/);
  });
});
