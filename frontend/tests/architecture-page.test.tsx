import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import ArchitectureSafetyPage from "../app/architecture/page";

afterEach(cleanup);

describe("ArchitectureSafetyPage", () => {
  it("explains the advisory and authoritative pipelines with exact boundary labels", () => {
    render(<ArchitectureSafetyPage />);

    expect(
      screen.getByRole("heading", { name: "Intelligence proposes. Deterministic controls decide." }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("list", { name: "Requirement to detached proposal pipeline" }),
    ).toHaveTextContent("Natural-language requirement");
    expect(
      screen.getByRole("list", { name: "Requirement to detached proposal pipeline" }),
    ).toHaveTextContent("FloorPlanProposal v2");

    const note = screen.getByRole("note");
    expect(note).toHaveTextContent("Detached Planning Sandbox");
    expect(note).toHaveTextContent("Detached Proposal");
    expect(note).toHaveTextContent("Not committed to World Model");
    expect(note).toHaveTextContent("Advisory planning output");

    const writePath = screen.getByRole("list", { name: "Mandatory authoritative write path" });
    for (const stage of [
      "PatchProposal",
      "Authorization",
      "Validation",
      "CAS Commit",
      "JSON Revision",
      "Trusted Audit",
    ]) {
      expect(within(writePath).getByText(stage)).toBeInTheDocument();
    }
  });

  it("presents exactly five named trust categories without relying on color", () => {
    const { container } = render(<ArchitectureSafetyPage />);

    const categories = container.querySelectorAll("[data-trust-category]");
    expect(categories).toHaveLength(5);
    for (const label of [
      "Untrusted input",
      "Typed advisory",
      "Trusted control",
      "Authoritative state",
      "Derived read-only",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText("Persisted JSON Revision")).toBeInTheDocument();
    const invariant = screen.getByRole("complementary", {
      name: "World Model authority invariant",
    });
    expect(
      within(invariant).getByText("Authoritative World Model", { selector: "small" }),
    ).toBeInTheDocument();
  });

  it("documents all six safety boundaries and exposes no write action", () => {
    render(<ArchitectureSafetyPage />);

    for (const heading of [
      "LLM interprets intent—not geometry",
      "Solver output stays detached",
      "Evaluation is not authorization",
      "Render IR is a read-only projection",
      "CAS prevents stale writes",
      "Audit identity travels separately",
    ]) {
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    }

    expect(screen.getByText(/no World Model, revision, geometry, repository/i)).toBeInTheDocument();
    expect(screen.getByText(/cannot enter the World Model Render IR projector/i)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("provides a skip link, home links, and a textual alternative to the visual paths", () => {
    render(<ArchitectureSafetyPage />);

    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute(
      "href",
      "#main-content",
    );
    expect(screen.getByRole("link", { name: "AI Parametric Architect Studio home" })).toHaveAttribute(
      "href",
      "/",
    );
    expect(
      screen.getByRole("list", { name: "Authoritative World Model visualization path" }),
    ).toHaveTextContent("Render IR 1.0.0");
    expect(screen.getByRole("link", { name: /Return to Design Studio/ })).toHaveAttribute(
      "href",
      "/",
    );
  });
});
