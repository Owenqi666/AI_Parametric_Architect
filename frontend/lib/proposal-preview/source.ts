import { parsePlanningShowcase } from "./parse";
import type { PlanningShowcaseArtifact } from "./types";

export const DEFAULT_SHOWCASE_SOURCE = "/examples/planning-showcase.preview-1.0.0.json";
export const MAX_SHOWCASE_BYTES = 1024 * 1024;

async function readLimitedText(response: Response): Promise<string> {
  if (!response.body) {
    const text = await response.text();
    if (new TextEncoder().encode(text).byteLength > MAX_SHOWCASE_BYTES) {
      throw new Error("Showcase data exceeds the 1 MiB response budget.");
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
    if (byteLength > MAX_SHOWCASE_BYTES) {
      await reader.cancel();
      throw new Error("Showcase data exceeds the 1 MiB response budget.");
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

export async function loadPlanningShowcase(
  source = DEFAULT_SHOWCASE_SOURCE,
  signal?: AbortSignal,
): Promise<PlanningShowcaseArtifact> {
  const url = new URL(source, window.location.href);
  if (url.origin !== window.location.origin) throw new Error("Showcase data must be same-origin.");
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    signal,
  });
  if (response.url && new URL(response.url).origin !== window.location.origin) {
    throw new Error("Showcase data must be same-origin.");
  }
  if (!response.ok) throw new Error(`Showcase data could not be loaded (${response.status}).`);
  const contentLength = Number(response.headers.get("content-length"));
  if (Number.isFinite(contentLength) && contentLength > MAX_SHOWCASE_BYTES) {
    throw new Error("Showcase data exceeds the 1 MiB response budget.");
  }
  const text = await readLimitedText(response);
  let value: unknown;
  try {
    value = JSON.parse(text) as unknown;
  } catch {
    throw new Error("Showcase data is not valid JSON.");
  }
  return parsePlanningShowcase(value);
}
