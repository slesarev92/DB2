/**
 * C #20 — Раскраска чувствительности с настраиваемыми порогами.
 */
import { expect, test } from "@playwright/test";

const EMAIL = "admin@example.com";
const PASSWORD = "admin123";

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Пароль").fill(PASSWORD);
  await page.getByRole("button", { name: "Войти" }).click();
  await page.waitForURL("**/projects", { timeout: 10_000 });
}

test.skip(
  "C #20 — изменение порога меняет раскраску ячеек",
  async ({ page }) => {
    // TODO: требует проект с рассчитанной чувствительностью.
    // 1. Открыть вкладку Чувствительность
    // 2. Видны input «Зелёный ≥ %» и «Красный ≤ −%» (default 5/5)
    // 3. Поднять green до 50 → ячейки с delta < +50% становятся нейтральными
    // 4. Reset → 5/5
    // 5. Reload → localStorage сохранил
    await login(page);
  },
);

test.skip(
  "C #20 — пороги сохраняются в localStorage между сессиями",
  async ({ page }) => {
    // TODO: установить, перезагрузить, проверить.
    await login(page);
  },
);
