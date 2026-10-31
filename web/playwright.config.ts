import { existsSync } from "node:fs";
import { defineConfig, devices } from "@playwright/test";

function resolveLocalBrowserExecutable(): string | undefined {
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) {
    return process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  }
  if (process.env.CI) {
    return undefined;
  }
  for (const candidate of ["/usr/bin/chromium", "/usr/bin/google-chrome-stable"]) {
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  return undefined;
}

const executablePath = resolveLocalBrowserExecutable();

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:3011",
    trace: "on-first-retry",
    launchOptions: {
      ...(executablePath ? { executablePath } : {}),
      args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
    },
  },
  webServer: {
    command: "APP_USE_FAKE_ONLY=true PORT_WEB=3011 HOST_WEB=127.0.0.1 npm run start",
    url: "http://127.0.0.1:3011/health",
    reuseExistingServer: !process.env.CI,
    timeout: 15000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
