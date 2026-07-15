"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  BenchmarkReportLoadError,
  loadBenchmarkReport,
  loadBenchmarkReportFile,
} from "../../lib/benchmark/source";
import {
  DEFAULT_BENCHMARK_REPORT_SOURCE,
  type BenchmarkReport,
} from "../../lib/benchmark/types";

import styles from "./benchmark.module.css";
import { BenchmarkReportView } from "./benchmark-report-view";

type LoadState =
  | { readonly status: "loading"; readonly report: null; readonly message: string }
  | { readonly status: "error"; readonly report: null; readonly message: string }
  | {
      readonly status: "ready";
      readonly report: BenchmarkReport;
      readonly message: string;
      readonly sourceLabel: string;
    };

const LOADING_STATE: LoadState = {
  status: "loading",
  report: null,
  message: "Admitting the bundled BenchmarkReport…",
};

function loadErrorMessage(error: unknown): string {
  if (error instanceof BenchmarkReportLoadError) return error.message;
  return "The benchmark report could not be admitted.";
}

export function BenchmarkLab() {
  const [reloadToken, setReloadToken] = useState(0);
  const [state, setState] = useState<LoadState>(LOADING_STATE);
  const fileInput = useRef<HTMLInputElement>(null);
  const requestSequence = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const requestId = ++requestSequence.current;
    void loadBenchmarkReport(DEFAULT_BENCHMARK_REPORT_SOURCE, controller.signal)
      .then((report) => {
        if (requestSequence.current !== requestId) return;
        setState({
          status: "ready",
          report,
          sourceLabel: "bundled offline fixture",
          message: "BenchmarkReport 1.0.0 admitted.",
        });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || requestSequence.current !== requestId) return;
        setState({ status: "error", report: null, message: loadErrorMessage(error) });
      });
    return () => controller.abort();
  }, [reloadToken]);

  const importFile = useCallback(async (file: File) => {
    const requestId = ++requestSequence.current;
    setState({ status: "loading", report: null, message: `Admitting ${file.name}…` });
    try {
      const report = await loadBenchmarkReportFile(file);
      if (requestSequence.current !== requestId) return;
      setState({
        status: "ready",
        report,
        sourceLabel: `local import · ${file.name}`,
        message: "BenchmarkReport 1.0.0 admitted.",
      });
    } catch (error) {
      if (requestSequence.current !== requestId) return;
      setState({ status: "error", report: null, message: loadErrorMessage(error) });
    } finally {
      if (fileInput.current) fileInput.current.value = "";
    }
  }, []);

  return (
    <div className={styles.lab}>
      <header className={styles.labHeader}>
        <div className={styles.reportContext}>
          <span aria-hidden="true">BR</span>
          <span>
            <small>Detached evidence workspace</small>
            <strong>Reproducible comparison</strong>
          </span>
        </div>

        <div className={styles.headerActions}>
          <label className={styles.importButton}>
            <span>Import report</span>
            <input
              ref={fileInput}
              type="file"
              accept="application/json,.json"
              onChange={(event) => {
                const file = event.currentTarget.files?.[0];
                if (file) void importFile(file);
              }}
            />
          </label>
          <button
            className={styles.secondaryButton}
            type="button"
            onClick={() => {
              setState(LOADING_STATE);
              setReloadToken((value) => value + 1);
            }}
          >
            Load bundled report
          </button>
        </div>
      </header>

      <div className={styles.labBody}>
        <section className={styles.hero} aria-labelledby="benchmark-lab-heading">
          <div>
            <p className={styles.kicker}>Planning evidence / BenchmarkReport 1.0.0</p>
            <h1 id="benchmark-lab-heading">Compare planners without crossing the commit boundary.</h1>
          </div>
          <p>
            Inspect detached benchmark evidence locally. Imported JSON is validated, bounded and
            frozen in memory; this lab never writes World Model state.
          </p>
        </section>

        <p className={styles.loadStatus} role="status" aria-live="polite" data-status={state.status}>
          <span aria-hidden="true" />
          {state.message}
        </p>

        {state.status === "loading" ? (
          <section className={styles.statePanel} aria-label="Loading benchmark report">
            <div className={styles.loader} aria-hidden="true" />
            <h2>Checking contract and evidence matrix</h2>
            <p>Large or malformed reports are rejected before visualization.</p>
          </section>
        ) : null}

        {state.status === "error" ? (
          <section className={styles.errorPanel} role="alert">
            <p className={styles.kicker}>Admission rejected</p>
            <h2>Report unavailable</h2>
            <p>{state.message}</p>
            <p>
              Select a valid BenchmarkReport 1.0.0 JSON file, or retry the bundled offline fixture.
            </p>
          </section>
        ) : null}

        {state.status === "ready" ? (
          <BenchmarkReportView report={state.report} sourceLabel={state.sourceLabel} />
        ) : null}
      </div>
    </div>
  );
}
