import { defineConfig } from "@playwright/test";
const apiPort = process.env.BIGFISH_E2E_API_PORT || '8092';
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:4173",
    channel: "chrome",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: ".venv\\Scripts\\python.exe tests/webui_server.py",
      cwd: "..",
      env: { PYTHONPATH: "." },
      url: `http://127.0.0.1:${apiPort}/health`,
      reuseExistingServer: false,
    },
    {
      command: "npm.cmd run dev -- --port 4173 --strictPort",
      env: { BIGFISH_API: `http://127.0.0.1:${apiPort}` },
      url: "http://127.0.0.1:4173",
      reuseExistingServer: false,
    },
  ],
});
