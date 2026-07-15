import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DesignStudioClient } from "../app/design-studio-client";

const showcaseText = readFileSync(
  resolve(process.cwd(), "public/examples/planning-showcase.preview-1.0.0.json"),
  "utf8",
);

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.includes("planning-showcase")) {
        return new Response(showcaseText, {
          status: 200,
          headers: { "content-type": "application/json", "content-length": String(showcaseText.length) },
        });
      }
      return new Response(null, { status: 404 });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Design Studio", () => {
  it("opens with a detached offline proposal and explicit authority labels", async () => {
    render(<DesignStudioClient />);

    expect(await screen.findByRole("heading", { name: "Design Studio" })).toBeInTheDocument();
    const viewport = screen.getByRole("region", { name: "Planning and World Model viewport" });
    expect(within(viewport).getByText("Detached Proposal")).toBeInTheDocument();
    expect(within(viewport).getByText("Not committed to World Model")).toBeInTheDocument();
    expect(within(viewport).getByText("Advisory planning output")).toBeInTheDocument();
    expect(screen.getByText("Recorded deterministic showcase")).toBeInTheDocument();
    expect(screen.getByText(/No provider or solver executes in the browser/)).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /OpenAI live/ })).not.toBeInTheDocument();
  });

  it("shows only observable pipeline states and typed proposal values", async () => {
    render(<DesignStudioClient />);
    await screen.findByRole("heading", { name: "Design Studio" });

    const pipeline = screen.getByRole("complementary", { name: "Planning input and execution pipeline" });
    expect(within(pipeline).getByText("Observable pipeline")).toBeInTheDocument();
    expect(within(pipeline).getByText("No hidden reasoning")).toBeInTheDocument();
    expect(within(pipeline).getByText("Constraint Planning")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Parsed DesignIntent" })).toBeInTheDocument();
    expect(screen.getByText("120.0 m²")).toBeInTheDocument();
    expect(screen.getByText(/cp-sat-rectilinear-v1 · 1 constraints/)).toBeInTheDocument();
    expect(screen.getByText("No write authority")).toBeInTheDocument();

    const roomButtons = screen.getAllByRole("button", { name: /square metres/ });
    fireEvent.click(roomButtons[0]!);
    expect(screen.getByText("Solved placement")).toBeInTheDocument();
    expect(screen.getByText("Advisory only")).toBeInTheDocument();

    const proposalTab = screen.getByRole("tab", { name: "Proposal" });
    fireEvent.keyDown(proposalTab, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "World Model" })).toHaveAttribute("aria-selected", "true");
  });

  it("fails closed when requirement text leaves the curated replay", async () => {
    render(<DesignStudioClient />);
    const input = await screen.findByRole("textbox", { name: "Natural-language requirement" });
    fireEvent.change(input, { target: { value: "Invent an unsupported design." } });
    fireEvent.click(screen.getByRole("button", { name: "Run planning" }));

    await waitFor(() => {
      expect(screen.getAllByText("SHOWCASE_INPUT_NOT_RECORDED")).toHaveLength(2);
    });
    expect(screen.getByText("No recorded output for edited input")).toBeInTheDocument();
  });

  it("keeps the parsed conflicting intent and marks planning as failed", async () => {
    render(<DesignStudioClient />);
    const scenario = await screen.findByRole("combobox", { name: "Showcase scenario" });
    fireEvent.change(scenario, { target: { value: "constraint-conflict" } });

    const pipeline = screen.getByRole("complementary", { name: "Planning input and execution pipeline" });
    expect(within(pipeline).getByText("Requirement").closest("li")).toHaveAttribute("data-status", "succeeded");
    expect(within(pipeline).getByText("Design Intent").closest("li")).toHaveAttribute("data-status", "succeeded");
    expect(within(pipeline).getByText("Constraint Planning").closest("li")).toHaveAttribute("data-status", "failed");
    expect(screen.getByText("40.0 m²")).toBeInTheDocument();
    expect(screen.getAllByText("PLANNING_SOLVER_FAILED")).toHaveLength(2);

    fireEvent.change(screen.getByRole("combobox", { name: "Execution mode" }), {
      target: { value: "offline" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run planning" }));
    await waitFor(() => {
      expect(within(pipeline).getByText("Constraint Planning").closest("li"))
        .toHaveAttribute("data-status", "failed");
    });
    expect(screen.getByText("Constraint planning failed closed")).toBeInTheDocument();
  });
});
