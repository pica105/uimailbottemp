import { test, expect } from "@playwright/test";

// The Mini App requires Telegram initData; without it the API calls 401 and
// the UI shows the empty/error states. These tests verify the shell and
// navigation render correctly in a plain browser.
test("inbox shell renders and navigates to settings", async ({ page }) => {
  await page.goto("/inbox");
  await expect(page.getByText("MailHub").first()).toBeVisible();
  await expect(page.getByText("All").first()).toBeVisible();
  await expect(page.getByText("Important").first()).toBeVisible();

  await page.getByText("Settings", { exact: true }).click();
  await expect(page).toHaveURL(/\/settings$/);
});

test("root page redirects to inbox", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/inbox/);
});
