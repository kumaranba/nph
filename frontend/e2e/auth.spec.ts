import { expect, test } from "@playwright/test";

// These tests assume the Django backend is running on :8000 and that a user
// admin@nph.test / secret123 (role ADMIN) exists. CI seeds this user.

test("login page renders the sign-in form", async ({ page }) => {
  await page.goto("/login");
  // CardTitle/CardDescription render as <div>s, so assert by text, not role.
  await expect(page.getByText("Access the NPH dashboard")).toBeVisible();
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByLabel("Password")).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
});

test("user can log in and land on the authenticated dashboard", async ({ page }) => {
  await page.goto("/login");

  await page.getByLabel("Email").fill("admin@nph.test");
  await page.getByLabel("Password").fill("secret123");
  await page.getByRole("button", { name: "Sign in" }).click();

  // Redirected to the dashboard. The app shell (sidebar/topbar) shows the
  // authenticated user from the `me` query: email plus the friendly role
  // label ("Administrator" for ADMIN). The role label appears in both the
  // sidebar and topbar, so match the first occurrence.
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByText("admin@nph.test")).toBeVisible();
  await expect(page.getByText("Administrator").first()).toBeVisible();
});

test("invalid credentials show an error and stay on the login page", async ({ page }) => {
  await page.goto("/login");

  await page.getByLabel("Email").fill("admin@nph.test");
  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByText(/Invalid email or password/i)).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});
