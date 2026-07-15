import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BenchmarkLab } from "../app/benchmark/benchmark-lab";
import { BenchmarkReportView } from "../app/benchmark/benchmark-report-view";
import {
  BenchmarkReportContractError,
  MAX_BENCHMARK_REPORT_BYTES,
  parseBenchmarkReport,
} from "../lib/benchmark/parse";
import {
  BenchmarkReportLoadError,
  loadBenchmarkReport,
} from "../lib/benchmark/source";

const REPORT_TEXT = readFileSync(
  resolve(process.cwd(), "public/examples/planning-core.benchmark-report-1.0.0.json"),
  "utf8",
);

function reportInput() {
  return JSON.parse(REPORT_TEXT);
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("BenchmarkReport 1.0.0 admission", () => {
  it("admits the generated offline fixture and deeply freezes the result", () => {
    const report = parseBenchmarkReport(reportInput());

    expect(report.schema_version).toBe("1.0.0");
    expect(report.dataset.dataset_id).toBe("planning-core");
    expect(report.observations).toHaveLength(
      report.dataset.case_count * report.configuration.trials * report.systems.length,
    );
    expect(Object.isFrozen(report)).toBe(true);
    expect(Object.isFrozen(report.systems)).toBe(true);
    expect(Object.isFrozen(report.systems[0]?.tracks.oracle_intent.metrics)).toBe(true);
    expect(Object.isFrozen(report.observations[0]?.tracks.end_to_end.runtime_ns)).toBe(true);
  });

  it.each([
    {
      name: "an unknown root field",
      mutate: (value: ReturnType<typeof reportInput>) => {
        value.untrusted_extension = true;
      },
      path: "/",
    },
    {
      name: "a different schema version",
      mutate: (value: ReturnType<typeof reportInput>) => {
        value.schema_version = "1.0.1";
      },
      path: "/schema_version",
    },
    {
      name: "a non-finite metric-context number",
      mutate: (value: ReturnType<typeof reportInput>) => {
        value.configuration.metric_context.default_minimum_room_area = Number.POSITIVE_INFINITY;
      },
      path: "/configuration/metric_context/default_minimum_room_area",
    },
    {
      name: "a browser budget beyond the hard cap",
      mutate: (value: ReturnType<typeof reportInput>) => {
        value.configuration.budget.max_cases = 257;
      },
      path: "/configuration/budget/max_cases",
    },
    {
      name: "coverage that disagrees with its denominator",
      mutate: (value: ReturnType<typeof reportInput>) => {
        value.systems[0].intent_extraction_accuracy.coverage = 0.5;
      },
      path: "/systems/0/intent_extraction_accuracy/coverage",
    },
    {
      name: "an incomplete attempt matrix",
      mutate: (value: ReturnType<typeof reportInput>) => {
        value.observations.pop();
      },
      path: "/observations",
    },
  ])("rejects $name", ({ mutate, path }) => {
    const input = reportInput();
    mutate(input);

    try {
      parseBenchmarkReport(input);
      throw new Error("Expected report admission to fail.");
    } catch (error) {
      expect(error).toBeInstanceOf(BenchmarkReportContractError);
      expect((error as BenchmarkReportContractError).path).toBe(path);
    }
  });
});

describe("benchmark report loading boundary", () => {
  it("rejects cross-origin report URLs before fetching", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(loadBenchmarkReport("https://untrusted.example/report.json")).rejects.toEqual(
      expect.objectContaining<Partial<BenchmarkReportLoadError>>({
        message: "Benchmark reports must load from this origin.",
      }),
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects a response whose declared size exceeds the browser budget", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("{}", {
          status: 200,
          headers: { "content-length": String(MAX_BENCHMARK_REPORT_BYTES + 1) },
        }),
      ),
    );

    await expect(loadBenchmarkReport("/oversized.json")).rejects.toEqual(
      expect.objectContaining<Partial<BenchmarkReportLoadError>>({
        message: "The benchmark report exceeds the browser budget.",
      }),
    );
  });
});

describe("Benchmark Lab evidence presentation", () => {
  it("renders both tracks, explicit denominators, text equivalents and detached digests", () => {
    const report = parseBenchmarkReport(reportInput());
    render(<BenchmarkReportView report={report} sourceLabel="test fixture" />);

    expect(screen.getByRole("heading", { name: /planning-core/ })).toBeInTheDocument();
    expect(screen.getByText("Detached evidence only.")).toBeInTheDocument();
    expect(screen.getByText(/report data contains no proposal geometry/i)).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /Text equivalent/ })).toBeInTheDocument();
    expect(screen.getAllByText(/16\/16 covered/).length).toBeGreaterThan(0);
    expect(screen.queryByText("Report declares OpenAI Responses evidence.")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Oracle intent/ }));
    expect(screen.getAllByText(/N\/A · NO_RUNTIME_SAMPLES/).length).toBeGreaterThan(0);
    expect(screen.getByRole("table", { name: /End-to-end and oracle-intent observations/ }))
      .toBeInTheDocument();
  });

  it("shows the OpenAI evidence notice only when admitted metadata identifies it", () => {
    const input = reportInput();
    input.systems[0].descriptor.execution_mode = "real_nondeterministic";
    input.systems[0].descriptor.deterministic = false;
    input.systems[0].descriptor.provider = "openai-responses";
    input.systems[0].descriptor.model = "gpt-test";
    const report = parseBenchmarkReport(input);

    render(<BenchmarkReportView report={report} sourceLabel="test fixture" />);

    expect(screen.getByText("Report declares OpenAI Responses evidence.")).toBeInTheDocument();
    expect(screen.getByText(/marks .* as real nondeterministic/)).toBeInTheDocument();
  });

  it("loads the bundled same-origin report and exposes local JSON import", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(REPORT_TEXT, {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { container } = render(<BenchmarkLab />);

    expect(screen.getByText("Import report")).toBeInTheDocument();
    expect(container.querySelector('input[type="file"][accept*="application/json"]'))
      .toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("BenchmarkReport 1.0.0 admitted.")).toBeInTheDocument();
    });
    expect(screen.getByText(/Admitted report · bundled offline fixture/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledOnce();
  });
});
