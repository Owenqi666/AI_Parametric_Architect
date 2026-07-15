import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loadRenderIr } from "../lib/render-ir/source";
import { validRenderIrInput } from "./fixtures";

describe("loadRenderIr", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/viewer");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("rejects cross-origin sources before issuing a request", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(loadRenderIr("https://attacker.example/model.json")).rejects.toEqual(
      expect.objectContaining({
        name: "RenderIrLoadError",
        message: "Render IR must be loaded from the viewer origin.",
      }),
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("loads and validates same-origin JSON with constrained fetch options", async () => {
    const response = new Response(JSON.stringify(validRenderIrInput()), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(response);
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    const result = await loadRenderIr("/api/render-ir", controller.signal);

    expect(result.source_model.model_id).toBe("model-test");
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, options] = fetchMock.mock.calls[0]!;
    expect(url).toBeInstanceOf(URL);
    expect((url as URL).origin).toBe(window.location.origin);
    expect((url as URL).pathname).toBe("/api/render-ir");
    expect(options?.credentials).toBe("same-origin");
    expect(options?.signal).toBe(controller.signal);
    expect(new Headers(options?.headers).get("accept")).toBe("application/json");
  });

  it("uses one generic load error for invalid JSON and invalid contracts", async () => {
    const invalidJsonFetch = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response("{", { status: 200 }));
    vi.stubGlobal("fetch", invalidJsonFetch);
    await expect(loadRenderIr("/broken-json")).rejects.toEqual(
      expect.objectContaining({
        name: "RenderIrLoadError",
        message: "The visualization source is not valid Render IR.",
      }),
    );

    const invalidContractFetch = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", invalidContractFetch);
    await expect(loadRenderIr("/broken-contract")).rejects.toEqual(
      expect.objectContaining({
        name: "RenderIrLoadError",
        message: "The visualization source is not valid Render IR.",
      }),
    );
  });

  it("rejects responses whose declared size exceeds the viewer budget", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response("{}", {
        status: 200,
        headers: { "content-length": String(2 * 1024 * 1024 + 1) },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(loadRenderIr("/oversized")).rejects.toThrow(
      "The visualization source exceeds the supported size.",
    );
  });
});
