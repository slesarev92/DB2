/**
 * E2E smoke tests (B-16) — критический flow приложения.
 *
 * Требования:
 * - Docker compose stack запущен
 * - Dev user создан (admin@example.com / admin123)
 *
 * Запуск:
 *   cd frontend && npx playwright test
 */
import { expect, test } from "@playwright/test";

const EMAIL = "admin@example.com";
const PASSWORD = "admin123";

// ============================================================
// Helper: login through the UI
// ============================================================

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Пароль").fill(PASSWORD);
  await page.getByRole("button", { name: "Войти" }).click();
  // Wait for redirect to /projects
  await page.waitForURL("**/projects", { timeout: 10_000 });
}

// ============================================================
// 1. Login → project list visible
// ============================================================

test("login and see project list", async ({ page }) => {
  await login(page);
  // Should see the projects page heading
  await expect(
    page.getByRole("heading", { name: "Проекты" }),
  ).toBeVisible({ timeout: 5_000 });
});

// ============================================================
// 2. Create project → tabs visible
// ============================================================

test("create project and see tabs", async ({ page }) => {
  await login(page);

  // Click create project button
  await page.getByRole("button", { name: "Создать проект" }).click();

  // Fill project name in dialog/form
  await page.getByLabel("Название").fill("E2E Smoke " + Date.now());

  // Submit
  await page.getByRole("button", { name: "Создать" }).click();

  // Wait for project page to load (should see tab bar)
  await expect(
    page.getByRole("tab", { name: "Параметры" }),
  ).toBeVisible({ timeout: 10_000 });

  // Verify key tabs exist
  await expect(page.getByRole("tab", { name: "SKU и BOM" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Каналы" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Периоды" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Результаты" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Сценарии" })).toBeVisible();
});

// ============================================================
// 3. Health check — backend reachable
// ============================================================

test("backend health check returns ok", async ({ request }) => {
  const resp = await request.get("http://localhost:8000/health");
  expect(resp.ok()).toBeTruthy();
  const body = await resp.json();
  expect(body.status).toBe("ok");
});

// ============================================================
// 4. Login page renders correctly
// ============================================================

test("login page shows form", async ({ page }) => {
  await page.goto("/login");
  await expect(page.locator('button[type="submit"]')).toBeVisible();
});

// ============================================================
// 5. Unauthorized redirect
// ============================================================

test("unauthenticated user redirected to login", async ({ page }) => {
  await page.goto("/projects");
  // Should redirect to /login (auth provider)
  await page.waitForURL("**/login", { timeout: 10_000 });
});
