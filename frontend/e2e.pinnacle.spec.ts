import { test, expect } from "@playwright/test";

test.describe("Pinnacle UI", () => {
  test("labels toggle and filter work", async ({ page }) => {
    await page.goto("/pinnacle");

    // Toggle labels via toolbar link (appends ?labels=1)
    await page.getByTestId("toolbar-toggle-labels").click();
    await expect(page).toHaveURL(/labels=1/);

    // A known label chip should appear for the hero title
    await expect(page.getByText("Hero: Hero Header").first()).toBeVisible();

    // Click label chip should focus target element
    await page.getByText("Hero: Hero Header").first().click();
    await expect(page.getByTestId("hero-title")).toBeFocused();

    // Filter with q=Primary
    await page.goto("/pinnacle?q=Primary&labels=1");
    // Only elements matching "Primary" remain visible in Actions
    await expect(page.getByTestId("act-primary")).toBeVisible();
    await expect(page.getByTestId("act-secondary")).toHaveCount(0);
  });
});
