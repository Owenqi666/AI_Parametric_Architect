import {
  BenchmarkReportContractError,
  MAX_BENCHMARK_REPORT_BYTES,
  parseBenchmarkReport,
} from "./parse";
import {
  DEFAULT_BENCHMARK_REPORT_SOURCE,
  type BenchmarkReport,
} from "./types";

export class BenchmarkReportLoadError extends Error {
  readonly path: string | null;

  constructor(message: string, path: string | null = null) {
    super(message);
    this.name = "BenchmarkReportLoadError";
    this.path = path;
  }
}

async function readLimitedResponse(response: Response): Promise<string> {
  if (!response.body) {
    const text = await response.text();
    if (new TextEncoder().encode(text).byteLength > MAX_BENCHMARK_REPORT_BYTES) {
      throw new BenchmarkReportLoadError("The benchmark report exceeds the browser budget.");
    }
    return text;
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let byteLength = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    byteLength += value.byteLength;
    if (byteLength > MAX_BENCHMARK_REPORT_BYTES) {
      await reader.cancel();
      throw new BenchmarkReportLoadError("The benchmark report exceeds the browser budget.");
    }
    chunks.push(value);
  }
  const payload = new Uint8Array(byteLength);
  let offset = 0;
  for (const chunk of chunks) {
    payload.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(payload);
}

export function parseBenchmarkReportJson(text: string): BenchmarkReport {
  try {
    return parseBenchmarkReport(JSON.parse(text));
  } catch (error) {
    if (error instanceof BenchmarkReportContractError) {
      throw new BenchmarkReportLoadError(
        `The report violates BenchmarkReport 1.0.0 at ${error.path}.`,
        error.path,
      );
    }
    if (error instanceof SyntaxError) {
      throw new BenchmarkReportLoadError("The selected file is not valid JSON.");
    }
    throw error;
  }
}

export async function loadBenchmarkReport(
  source = DEFAULT_BENCHMARK_REPORT_SOURCE,
  signal?: AbortSignal,
): Promise<BenchmarkReport> {
  const url = new URL(source, window.location.href);
  if (url.origin !== window.location.origin) {
    throw new BenchmarkReportLoadError("Benchmark reports must load from this origin.");
  }
  const response = await fetch(url, {
    signal,
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (response.url && new URL(response.url).origin !== window.location.origin) {
    throw new BenchmarkReportLoadError("Benchmark reports must load from this origin.");
  }
  if (!response.ok) {
    throw new BenchmarkReportLoadError("The bundled benchmark report could not be loaded.");
  }
  const declaredLength = Number(response.headers.get("content-length"));
  if (Number.isFinite(declaredLength) && declaredLength > MAX_BENCHMARK_REPORT_BYTES) {
    throw new BenchmarkReportLoadError("The benchmark report exceeds the browser budget.");
  }
  return parseBenchmarkReportJson(await readLimitedResponse(response));
}

export async function loadBenchmarkReportFile(file: File): Promise<BenchmarkReport> {
  if (file.size > MAX_BENCHMARK_REPORT_BYTES) {
    throw new BenchmarkReportLoadError("The selected report exceeds the browser budget.");
  }
  const text = await file.text();
  if (new TextEncoder().encode(text).byteLength > MAX_BENCHMARK_REPORT_BYTES) {
    throw new BenchmarkReportLoadError("The selected report exceeds the browser budget.");
  }
  return parseBenchmarkReportJson(text);
}
