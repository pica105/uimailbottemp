import { test, expect, Page } from "@playwright/test";

test("includes the official Telegram WebApp SDK", async ({ page }) => {
  await page.goto("/inbox");
  await expect(
    page.locator('script[src^="https://telegram.org/js/telegram-web-app.js"]'),
  ).toHaveCount(1);
});

// Without the Telegram SDK the app shows a placeholder instead of hitting
// the API (which would 401 without initData).
test("outside Telegram shows the placeholder", async ({ page }) => {
  await page.goto("/inbox");
  await expect(page.getByText("Open MailHub in Telegram").first()).toBeVisible();
});

// Inject a fake Telegram WebApp SDK before the app loads, like the real
// Telegram client does. The API calls will 401 (fake initData), but the
// shell, tabs and navigation must still render.
async function injectTelegram(page: Page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: "auth_date=1&query_id=test&user=%7B%22id%22%3A42%7D&hash=fake",
        colorScheme: "light",
        themeParams: {},
        ready: () => {},
        expand: () => {},
        BackButton: {
          show: () => {},
          hide: () => {},
          onClick: () => {},
          offClick: () => {},
        },
        HapticFeedback: {
          impactOccurred: () => {},
          notificationOccurred: () => {},
        },
        onEvent: () => {},
        offEvent: () => {},
      },
    };
  });
}

test("inbox shell sends initData to protected API", async ({ page }) => {
  await injectTelegram(page);
  const apiRequest = page.waitForRequest((request) =>
    request.url().includes("/api/accounts"),
  );
  await page.goto("/inbox");
  const request = await apiRequest;
  expect(request.headers()["x-telegram-init-data"]).toContain("auth_date=1");
});

test("inbox shell renders and navigates to settings", async ({ page }) => {
  await injectTelegram(page);
  await page.goto("/inbox");
  await expect(page.getByText("MailHub").first()).toBeVisible();
  await expect(page.getByText("All").first()).toBeVisible();
  await expect(page.getByText("Important").first()).toBeVisible();

  await page.getByText("Settings", { exact: true }).click();
  await expect(page).toHaveURL(/\/settings$/);
});

test("root page redirects to inbox", async ({ page }) => {
  await injectTelegram(page);
  await page.goto("/");
  await expect(page).toHaveURL(/\/inbox/);
});
