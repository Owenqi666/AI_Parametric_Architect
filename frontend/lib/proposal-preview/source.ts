import { parsePlanningShowcase } from "./parse";
import type { PlanningShowcaseArtifact } from "./types";

export const DEFAULT_SHOWCASE_SOURCE = "/examples/planning-showcase.preview-1.0.0.json";
const MAX_SHOWCASE_BYTES = 1024 * 1024;

export async function loadPlanningShowcase(
  source = DEFAULT_SHOWCASE_SOURCE,
  signal?: AbortSignal,
): Promise<PlanningShowcaseArtifact> {
  const url = new URL(source, window.location.href);
  if (url.origin !== window.location.origin) throw new Error("Showcase data must be same-origin.");
  const response = await fetch(url, { credentials: "same-origin", signal });
  if (!response.ok) throw new Error(`Showcase data could not be loaded (${response.status}).`);
  const contentLength = response.headers.get("content-length");
  if (contentLength !== null && Number(contentLength) > MAX_SHOWCASE_BYTES) {
    throw new Error("Showcase data exceeds the 1 MiB response budget.");
  }
  const text = await response.text();
  if (new TextEncoder().encode(text).byteLength > MAX_SHOWCASE_BYTES) {
    throw new Error("Showcase data exceeds the 1 MiB response budget.");
  }
  let value: unknown;
  try {
    value = JSON.parse(text) as unknown;
  } catch {
    throw new Error("Showcase data is not valid JSON.");
  }
  return parsePlanningShowcase(value);
}

