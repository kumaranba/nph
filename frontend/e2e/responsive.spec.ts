import { expect, test, type Page } from "@playwright/test";

// Assumes the Django backend is running on :8000 with admin@nph.test / secret123.

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@nph.test");
  await page.getByLabel("Password").fill("secret123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

test("mobile viewport shows the mobile nav shell, not the sidebar", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await login(page);

  // The mobile top bar (menu button) and bottom tab bar are present.
  await expect(page.getByRole("button", { name: "Open menu" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Home" })).toBeVisible();

  // Opening the drawer reveals the full navigation.
  await page.getByRole("button", { name: "Open menu" }).click();
  await expect(page.getByRole("link", { name: "Users & roles" })).toBeVisible();
});

test("desktop viewport shows the sidebar, not the mobile menu", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await login(page);

  // No mobile menu button at desktop widths.
  await expect(page.getByRole("button", { name: "Open menu" })).toBeHidden();
  // The sidebar's Dashboard link is visible.
  await expect(
    page.getByRole("link", { name: "Dashboard" }).first()
  ).toBeVisible();
});
