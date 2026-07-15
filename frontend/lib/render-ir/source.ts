import { parseRenderIr, RenderIrContractError } from "./parse";
import type { RenderIr } from "./types";

export const DEFAULT_RENDER_IR_SOURCE = "/examples/showcase-house.render-ir.json";
const MAX_RESPONSE_BYTES = 2 * 1024 * 1024;

export class RenderIrLoadError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RenderIrLoadError";
  }
}

async function readLimitedText(response: Response): Promise<string> {
  if (!response.body) {
    const text = await response.text();
    if (new TextEncoder().encode(text).byteLength > MAX_RESPONSE_BYTES) {
      throw new RenderIrLoadError("The visualization source exceeds the supported size.");
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
    if (byteLength > MAX_RESPONSE_BYTES) {
      await reader.cancel();
      throw new RenderIrLoadError("The visualization source exceeds the supported size.");
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

export async function loadRenderIr(
  source = DEFAULT_RENDER_IR_SOURCE,
  signal?: AbortSignal,
): Promise<RenderIr> {
  const url = new URL(source, window.location.href);
  if (url.origin !== window.location.origin) {
    throw new RenderIrLoadError("Render IR must be loaded from the viewer origin.");
  }
  const response = await fetch(url, {
    signal,
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (response.url && new URL(response.url).origin !== window.location.origin) {
    throw new RenderIrLoadError("Render IR must be loaded from the viewer origin.");
  }
  if (!response.ok) throw new RenderIrLoadError("The visualization source could not be loaded.");
  const declaredLength = Number(response.headers.get("content-length"));
  if (Number.isFinite(declaredLength) && declaredLength > MAX_RESPONSE_BYTES) {
    throw new RenderIrLoadError("The visualization source exceeds the supported size.");
  }
  const text = await readLimitedText(response);
  try {
    return parseRenderIr(JSON.parse(text));
  } catch (error) {
    if (error instanceof RenderIrContractError || error instanceof SyntaxError) {
      throw new RenderIrLoadError("The visualization source is not valid Render IR.");
    }
    throw error;
  }
}
