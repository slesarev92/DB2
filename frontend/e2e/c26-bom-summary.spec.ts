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

test.skip(
  "C #26 — пустой BOM показывает empty state в сводке",
  async ({ page }) => {
    // TODO: требует SKU создать через UI flow перед тем как BomPanel
    // отрендерится с пустым BOM. Прямого пути от нового проекта к BOM
    // без SKU нет — нужен seed либо preliminary шаг создания SKU.
    await login(page);
    await page.getByRole("button", { name: "Создать проект" }).click();
    await page.getByLabel("Название").fill(`C26 empty ${Date.now()}`);
    await page.getByRole("button", { name: "Создать" }).click();
    await expect(
      page.getByRole("tab", { name: "Параметры" }),
    ).toBeVisible({ timeout: 10_000 });
    await page.getByRole("tab", { name: "SKU и BOM" }).click();
    // После создания SKU и выбора:
    // await expect(page.getByText("Сводка BOM")).toBeVisible();
    // await expect(page.getByText("Добавьте позиции BOM для расчёта")).toBeVisible();
  },
);

test.skip(
  "C #26 — BOM из 3 категорий показывает разбивку + Итого",
  async ({ page }) => {
    // TODO: требует seed-данных (3 ингредиента с разными
    // ingredient_category: raw_material/packaging/other).
    // Ожидаемые assertions при наличии seed:
    //   await expect(page.getByText("Сводка BOM")).toBeVisible();
    //   await expect(page.getByText("Сырьё")).toBeVisible();
    //   await expect(page.getByText("Упаковка")).toBeVisible();
    //   await expect(page.getByText("Прочее")).toBeVisible();
    //   await expect(page.getByText(/Итого/)).toBeVisible();
    //   // Проверка процентов: каждая категория > 0%, сумма ≈ 100%.
    await login(page);
  },
);
