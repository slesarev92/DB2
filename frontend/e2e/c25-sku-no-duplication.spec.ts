/**
 * C #25 — Дублирование ввода SKU между табами устранено.
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
  "C #25 — на вкладке Каналы диалог только в existing-режиме",
  async ({ page }) => {
    // TODO: требует seed-данных (проект с минимум 1 SKU в каталоге).
    // Ожидаемое: tab Каналы → кнопка «+ Привязать SKU» → диалог
    // «Привязать SKU к проекту» без mode toggle, только Select из каталога.
    await login(page);
  },
);

test.skip(
  "C #25 — на вкладке SKU и BOM оба режима доступны",
  async ({ page }) => {
    // TODO: tab SKU и BOM → «+ Добавить» → диалог «Добавить SKU в проект»
    // с mode toggle (existing / new).
    await login(page);
  },
);
