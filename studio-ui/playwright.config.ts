import { defineConfig, devices } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// E2E tests drive the real Python server.  Each run gets a fresh data folder so
// settings, the key and the activity log start empty.
export const PORT = 8798;
export const TOKEN = "e2e-token-not-secret";
const studio = process.env.STUDIO_CMD ?? "phi-guard-studio";
const dataDir = process.env.STUDIO_DATA_DIR ?? mkdtempSync(join(tmpdir(), "phi-guard-e2e-"));
process.env.STUDIO_DATA_DIR = dataDir; // workers re-read the config; keep one folder per run

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1, // tests share one server (vault, settings, log)
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "off",
    viewport: { width: 1280, height: 720 },
    permissions: ["clipboard-read", "clipboard-write"],
    acceptDownloads: true,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 720 } } }],
  webServer: {
    command: `${studio} --no-browser --port ${PORT} --data-dir "${dataDir}"`,
    url: `http://127.0.0.1:${PORT}/`,
    env: { PHI_GUARD_STUDIO_TOKEN: TOKEN },
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
