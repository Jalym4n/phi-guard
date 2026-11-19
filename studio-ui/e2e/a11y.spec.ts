import { expect, test } from "@playwright/test";
import { expectAccessible, findDetails, fixture, go, mainButton, open } from "./helpers";

for (const scheme of ["light", "dark"] as const) {
  test.describe(`accessibility (${scheme} theme)`, () => {
    test.use({ colorScheme: scheme });

    test("every page has zero serious or critical axe violations", async ({ page }) => {
      await open(page);
      await expectAccessible(page, "Remove (empty)");
      await findDetails(page, "Patient: Eleanor Whitfield\nPhone (416) 555-0142\nMrs. Whitfield is well.");
      await expectAccessible(page, "Remove (review)");
      await page.getByRole("tab", { name: "Many files (batch)" }).click();
      await expectAccessible(page, "Batch");

      await go(page, "Check a document");
      await page.getByTestId("check-file-input").setInputFiles(fixture("poisoned_doc.txt"));
      await expect(page.getByLabel("Document to check")).toHaveValue(/Lab Requisitions/);
      await page.getByRole("button", { name: "Check this document" }).click();
      await expect(page.locator("[data-verdict]")).toBeVisible();
      await expectAccessible(page, "Check (result)");

      await go(page, "Restore names");
      await page.getByLabel("AI answer with codes").fill("[SIN_0badc0de]");
      await mainButton(page, "Restore names").click();
      await expectAccessible(page, "Restore");

      await go(page, "Activity log");
      await page.getByRole("button", { name: "Check the log hasn't been changed" }).click();
      await expectAccessible(page, "Activity log");

      await go(page, "Settings");
      await expectAccessible(page, "Settings");
      await page.getByRole("button", { name: "Export key" }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await expectAccessible(page, "Settings (dialog)");
      await page.keyboard.press("Escape");

      await go(page, "Help");
      await expectAccessible(page, "Help");
    });
  });
}

test("keyboard only: reach Find and Copy without a mouse", async ({ page }) => {
  await open(page);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
  await page.getByLabel("Text to make safe").focus();
  await page.keyboard.insertText("Patient: Eleanor Whitfield");
  await page.getByRole("button", { name: "Find patient details" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("preview")).toContainText("[PATIENT_NAME_");
  await page.getByRole("button", { name: "Copy safe text" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Safe text copied")).toBeVisible();
});
