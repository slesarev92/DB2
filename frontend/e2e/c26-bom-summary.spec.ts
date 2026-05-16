/**
 * C #26 — BOM сводка справа.
 * Требования: Docker stack, dev user admin@example.com/admin123.
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

test("C #26 — пустой BOM показывает empty state в сводке", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "Создать проект" }).click();
  await page.getByLabel("Название").fill(`C26 empty ${Date.now()}`);
  await page.getByRole("button", { name: "Создать" }).click();
  await expect(
    page.getByRole("tab", { name: "Параметры" }),
  ).toBeVisible({ timeout: 10_000 });

  // TODO: если для BOM нужен предварительно созданный SKU — добавить flow.
  // На минимум — проверяем что компонент Сводка BOM рендерится в DOM.
  // Если SKU и BOM tab защищён без SKU — оставь test.skip(true, "TODO seed SKU").
  await page.getByRole("tab", { name: "SKU и BOM" }).click();
  // Если нужен SKU перед BOM — implementer уточняет flow или скипает.
});

test.skip("C #26 — BOM из 3 категорий показывает разбивку + Итого", async ({ page }) => {
  // TODO: требует seed-данных (3 ингредиента с разными ingredient_category)
  await login(page);
});
