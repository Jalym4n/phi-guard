import { expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { fileURLToPath } from "node:url";

export const TOKEN = "e2e-token-not-secret";
export const fixture = (name: string) => fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url));

export async function open(page: Page) {
  const violations: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") violations.push(m.text());
  });
  await page.goto(`/#token=${TOKEN}`);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  return violations;
}

export async function go(page: Page, name: string) {
  await page.getByRole("navigation", { name: "Main" }).getByRole("button", { name, exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
}

/** The page's own button (not the sidebar link with the same name). */
export function mainButton(page: Page, name: string | RegExp) {
  return page.locator("main").getByRole("button", { name, exact: typeof name === "string" });
}

export async function copySafeText(page: Page): Promise<string> {
  await mainButton(page, "Copy safe text").click();
  await expect(page.getByText("Safe text copied")).toBeVisible();
  return page.evaluate(() => navigator.clipboard.readText());
}

export async function findDetails(page: Page, text: string) {
  await page.getByLabel("Text to make safe").fill(text);
  await page.getByRole("button", { name: "Find patient details" }).click();
  await expect(page.getByTestId("preview")).not.toHaveText("Preparing…");
}

/** Zero serious or critical accessibility violations (WCAG 2.1 A/AA rules). */
export async function expectAccessible(page: Page, context: string) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const bad = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(
    bad.map((v) => `${context}: ${v.id} (${v.impact}) ${v.help} -> ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`),
  ).toEqual([]);
}
