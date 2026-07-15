import vinext from "vinext";
import { defineConfig } from "vite";
import { sites } from "./site-support/sites-vite-plugin";

const isCodexSeatbeltSandbox = process.env.CODEX_SANDBOX === "seatbelt";

const localBindingConfig = {
  main: "./worker/index.ts",
  compatibility_flags: ["nodejs_compat"],
  d1_databases: [],
  r2_buckets: [],
};

export default defineConfig(async () => {
  process.env.WRANGLER_WRITE_LOGS ??= "false";
  process.env.WRANGLER_LOG_PATH ??= ".wrangler/logs";
  process.env.MINIFLARE_REGISTRY_PATH ??= ".wrangler/registry";
  const { cloudflare } = await import("@cloudflare/vite-plugin");
  const apiOrigin = process.env.SHOWCASE_API_ORIGIN ?? "http://127.0.0.1:8000";

  const server = {
    ...(isCodexSeatbeltSandbox
      ? { watch: { useFsEvents: false, usePolling: true } }
      : {}),
    proxy: {
      "/v1": { target: apiOrigin, changeOrigin: false },
      "/health": { target: apiOrigin, changeOrigin: false },
    },
  };

  return {
    server,
    plugins: [
      vinext(),
      sites(),
      cloudflare({
        viteEnvironment: { name: "rsc", childEnvironments: ["ssr"] },
        config: localBindingConfig,
      }),
    ],
  };
});
