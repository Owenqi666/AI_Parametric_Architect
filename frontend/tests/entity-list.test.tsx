import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EntityList } from "../app/entity-list";
import type { RenderObject } from "../lib/render-ir/types";
import { validRenderIr } from "./fixtures";

describe("EntityList", () => {
  it("renders untrusted names as inert text and reports the selected entity ID", () => {
    const attack = '<img src=x onerror="window.__renderIrAttack=true"><script>bad()</script>';
    const source = validRenderIr().objects[0];
    if (!source) throw new Error("Fixture object is missing.");
    const maliciousObject: RenderObject = { ...source, name: attack };
    const onSelect = vi.fn();

    const { container } = render(
      <EntityList
        objects={[maliciousObject]}
        visibleFloorId={null}
        selectedId={maliciousObject.entity_id}
        onSelect={onSelect}
      />,
    );

    const renderedName = screen.getByText(attack, { exact: true });
    expect(renderedName).toHaveTextContent(attack);
    expect(container.querySelector("img, script")).toBeNull();
    const button = renderedName.closest("button");
    expect(button).toHaveAttribute("aria-pressed", "true");

    if (!button) throw new Error("Entity button is missing.");
    fireEvent.click(button);
    expect(onSelect).toHaveBeenCalledOnce();
    expect(onSelect).toHaveBeenCalledWith(maliciousObject.entity_id);
  });

  it("shows only entities on the visible floor", () => {
    const renderIr = validRenderIr();

    render(
      <EntityList
        objects={renderIr.objects}
        visibleFloorId="floor-upper"
        selectedId={null}
        onSelect={() => undefined}
      />,
    );

    expect(screen.getByText("Upper room")).toBeInTheDocument();
    expect(screen.queryByText("Ground room")).not.toBeInTheDocument();
    expect(screen.queryByText("South wall")).not.toBeInTheDocument();
  });
});
