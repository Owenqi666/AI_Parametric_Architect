import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { parseRenderIr } from "../lib/render-ir/parse";

describe("showcase World Model projection", () => {
  it("admits a multi-floor backend-generated Render IR fixture", () => {
    const input = JSON.parse(
      readFileSync(resolve(process.cwd(), "public/examples/showcase-house.render-ir.json"), "utf8"),
    ) as unknown;

    const renderIr = parseRenderIr(input);

    expect(renderIr.source_model.model_id).toBe("mdl_showcase_house");
    expect(renderIr.source_model.revision).toBe(7);
    expect(renderIr.floors).toHaveLength(2);
    expect(renderIr.objects.filter((item) => item.entity_type === "room")).toHaveLength(7);
    expect(renderIr.objects.some((item) => item.entity_type === "door")).toBe(true);
    expect(renderIr.objects.some((item) => item.entity_type === "window")).toBe(true);
    expect(Object.isFrozen(renderIr)).toBe(true);
    expect(Object.isFrozen(renderIr.objects)).toBe(true);
  });
});

