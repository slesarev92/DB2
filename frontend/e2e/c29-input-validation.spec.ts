/**
 * C #29 — Валидация вводных (minimum protection).
 *
 * 5 тестов: 4 positive (warning появляется при 0, не блокирует)
 *           + 1 negative (нечисловой ввод блокирует сохранение).
 *
 * Требования:
 * - Docker compose stack запущен
 * - Dev user создан (admin@example.com / admin123)
 *
 * Запуск:
 *   cd frontend && npx playwright test e2e/c29-input-validation.spec.ts
 */
import { expect, test } from "@playwright/test";

const EMAIL = "admin@example.com";
const PASSWORD = "admin123";

// ============================================================
// Helpers
// ============================================================

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Пароль").fill(PASSWORD);
  await page.getByRole("button", { name: "Войти" }).click();
  await page.waitForURL("**/projects", { timeout: 10_000 });
}

async function createProjectAndOpen(
  page: import("@playwright/test").Page,
  prefix: string,
) {
  await login(page);
  await page.getByRole("button", { name: "Создать проект" }).click();
  await page.getByLabel("Название").fill(`${prefix} ${Date.now()}`);
  await page.getByRole("button", { name: "Создать" }).click();
  await expect(
    page.getByRole("tab", { name: "Параметры" }),
  ).toBeVisible({ timeout: 10_000 });
}

// ============================================================
// Test 1: shelf_price_reg = 0 → amber warning, save not blocked
// ============================================================

test("C#29 — shelf_price_reg=0 показывает amber warning, не блокирует", async ({
  page,
}) => {
  // TODO: Этот тест требует seed-данных: хотя бы один канал в каталоге
  // и хотя бы один SKU в проекте. Без них нельзя добраться до ChannelForm.
  //
  // Flow:
  // 1. Создать проект → добавить SKU → перейти на вкладку «Каналы»
  // 2. Нажать «+ Привязать канал» → выбрать канал в phase=pick → «Далее →»
  // 3. В phase=defaults найти поле «Цена полки» → ввести 0 → blur
  // 4. Проверить: появился текст "Цена полки 0 ₽ — выручка обнулится"
  // 5. Кнопка submit NOT disabled
  //
  // Полная реализация требует seed-скрипта или предварительно созданных данных.
  test.skip(
    true,
    "TODO: requires seeded channel catalog + SKU in project (no seed script yet)",
  );

  await createProjectAndOpen(page, "C29 shelf_price");
  await page.getByRole("tab", { name: "Каналы" }).click();

  // Open AddChannelsDialog phase=pick
  await page.getByRole("button", { name: "+ Привязать канал" }).click();
  await expect(
    page.getByRole("dialog").getByText("Выбор каналов"),
  ).toBeVisible({ timeout: 5_000 });

  // Select first available checkbox and proceed
  const firstCheckbox = page
    .getByRole("dialog")
    .locator('input[type="checkbox"]:not(:disabled)')
    .first();
  await firstCheckbox.check();
  await page.getByRole("button", { name: "Далее →" }).click();

  // phase=defaults: fill shelf_price_reg = 0
  const shelfInput = page.getByLabel("Цена полки (с НДС), ₽/ед.");
  await shelfInput.fill("0");
  await shelfInput.blur();

  // Warning must be visible
  await expect(
    page.getByText("Цена полки 0 ₽ — выручка обнулится"),
  ).toBeVisible();

  // Submit button must NOT be disabled (warnings don't block)
  const submitBtn = page
    .getByRole("dialog")
    .getByRole("button", { name: /Привязать/ });
  await expect(submitBtn).not.toBeDisabled();
});

// ============================================================
// Test 2: offtake_target = 0 → amber warning, save not blocked
// ============================================================

test("C#29 — offtake_target=0 показывает amber warning, не блокирует", async ({
  page,
}) => {
  // TODO: same seed requirements as Test 1.
  test.skip(
    true,
    "TODO: requires seeded channel catalog + SKU in project (no seed script yet)",
  );

  await createProjectAndOpen(page, "C29 offtake");
  await page.getByRole("tab", { name: "Каналы" }).click();

  await page.getByRole("button", { name: "+ Привязать канал" }).click();
  await expect(
    page.getByRole("dialog").getByText("Выбор каналов"),
  ).toBeVisible({ timeout: 5_000 });

  const firstCheckbox = page
    .getByRole("dialog")
    .locator('input[type="checkbox"]:not(:disabled)')
    .first();
  await firstCheckbox.check();
  await page.getByRole("button", { name: "Далее →" }).click();

  // phase=defaults: fill offtake_target = 0
  const offtakeInput = page.getByLabel("Офтейк (ед./точка/мес.)");
  await offtakeInput.fill("0");
  await offtakeInput.blur();

  await expect(
    page.getByText("Целевой offtake 0 — продаж не будет"),
  ).toBeVisible();

  const submitBtn = page
    .getByRole("dialog")
    .getByRole("button", { name: /Привязать/ });
  await expect(submitBtn).not.toBeDisabled();
});

// ============================================================
// Test 3: BOM price_per_unit = 0 → amber warning in inline form
// ============================================================

test("C#29 — price_per_unit=0 показывает amber warning в BOM-форме", async ({
  page,
}) => {
  // TODO: requires a project with a SKU already added.
  // The BOM inline form is visible once a PSK is selected in the SKU&BOM tab.
  test.skip(
    true,
    "TODO: requires project with existing SKU to access BOM panel (no seed script yet)",
  );

  await createProjectAndOpen(page, "C29 bom_price");
  await page.getByRole("tab", { name: "SKU и BOM" }).click();

  // Select first SKU tab / card so BomPanel renders
  // (exact locator depends on SKU list structure — using first item)
  const firstSkuButton = page
    .locator("[data-testid='psk-item'], .psk-item")
    .first();
  if (await firstSkuButton.isVisible()) {
    await firstSkuButton.click();
  }

  // Inline BOM form: fill price_per_unit = 0, trigger blur
  const priceInput = page.getByLabel("Цена/ед, ₽ (без НДС)");
  await priceInput.fill("0");
  await priceInput.blur();

  await expect(
    page.getByText("Цена сырья 0 — компонент не попадёт в COGS"),
  ).toBeVisible();
});

// ============================================================
// Test 4: volume_l = 0 in AddSkuDialog → amber warning
// ============================================================

test("C#29 — volume_l=0 показывает amber warning в AddSkuDialog", async ({
  page,
}) => {
  await createProjectAndOpen(page, "C29 volume_l");
  await page.getByRole("tab", { name: "SKU и BOM" }).click();

  // Click "+ Добавить" button that opens AddSkuDialog
  await page.getByRole("button", { name: "+ Добавить" }).click();

  // Dialog should be visible
  await expect(
    page.getByRole("dialog").getByText("Добавить SKU в проект"),
  ).toBeVisible({ timeout: 5_000 });

  // Switch to "new" mode
  await page.getByRole("button", { name: "Создать новый" }).click();

  // Fill volume_l = 0 and blur
  const volumeInput = page.getByLabel("Объём / масса");
  await volumeInput.fill("0");
  await volumeInput.blur();

  // Warning must appear
  await expect(
    page.getByText("Объём 0 — расчёты per-unit некорректны"),
  ).toBeVisible();

  // Submit button remains enabled (warnings don't block)
  const submitBtn = page
    .getByRole("dialog")
    .getByRole("button", { name: "Добавить" });
  await expect(submitBtn).not.toBeDisabled();
});

// ============================================================
// Test 5 (negative): нечисловое значение в shelf_price_reg
//                    → error message, submit кнопка недоступна
// ============================================================

test("C#29 — нечисловое значение показывает error и блокирует submit", async ({
  page,
}) => {
  // TODO: same seed requirements as Test 1 — needs channel + SKU.
  test.skip(
    true,
    "TODO: requires seeded channel catalog + SKU in project (no seed script yet)",
  );

  await createProjectAndOpen(page, "C29 invalid input");
  await page.getByRole("tab", { name: "Каналы" }).click();

  await page.getByRole("button", { name: "+ Привязать канал" }).click();
  await expect(
    page.getByRole("dialog").getByText("Выбор каналов"),
  ).toBeVisible({ timeout: 5_000 });

  const firstCheckbox = page
    .getByRole("dialog")
    .locator('input[type="checkbox"]:not(:disabled)')
    .first();
  await firstCheckbox.check();
  await page.getByRole("button", { name: "Далее →" }).click();

  // Enter non-numeric value in shelf_price_reg
  const shelfInput = page.getByLabel("Цена полки (с НДС), ₽/ед.");
  await shelfInput.fill("abc");
  await shelfInput.blur();

  // Error message (not warning) must appear
  await expect(page.getByText("Введите число")).toBeVisible();

  // No warning message (error takes priority)
  await expect(
    page.getByText("Цена полки 0 ₽ — выручка обнулится"),
  ).not.toBeVisible();

  // On submit attempt, validateAll fires → button remains enabled but form
  // does NOT proceed (errors block save, checked via error staying visible)
  const submitBtn = page
    .getByRole("dialog")
    .getByRole("button", { name: /Привязать/ });
  await submitBtn.click();
  // Error still visible after click = form was blocked
  await expect(page.getByText("Введите число")).toBeVisible();
});
