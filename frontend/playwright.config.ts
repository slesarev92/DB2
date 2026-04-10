import { defineConfig } from "@playwright/test";

/**
 * Playwright конфигурация для e2e тестов (B-16).
 *
 * Требования:
 * - Docker compose stack запущен (backend + frontend + postgres)
 * - Frontend доступен на http://localhost:3000
 * - Backend доступен на http://localhost:8000
 *
 * Запуск:
 *   cd frontend && npx playwright test
 *   cd frontend && npx playwright test --headed  # с браузером
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: "http://localhost:3000",
    headless: true,
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium" },
    },
  ],
});
