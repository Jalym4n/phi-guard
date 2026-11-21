// Regenerate README/Help screenshots and GIF frames from the real app.
//   1. Start Studio:  PHI_GUARD_STUDIO_TOKEN=shots phi-guard-studio --no-browser --port 8790 --data-dir <empty dir>
//   2. node scripts/screenshots.mjs <docs/screenshots dir> <gif frames dir> <help images dir>
// All content shown is synthetic.
import { chromium } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const [shotsDir, framesDir, helpDir] = process.argv.slice(2);
const BASE = "http://127.0.0.1:8790";
const START = `${BASE}/#token=shots`;
const NOTE = readFileSync(new URL("../../examples/sample_note.txt", import.meta.url), "utf8");
const POISONED = readFileSync(new URL("../../examples/poisoned_doc.txt", import.meta.url), "utf8");
for (const d of [shotsDir, framesDir, helpDir]) mkdirSync(d, { recursive: true });

const browser = await chromium.launch();

async function nav(page, name) {
  await page.getByRole("navigation", { name: "Main" }).getByRole("button", { name, exact: true }).click();
  await page.getByRole("heading", { level: 1, name }).waitFor();
}

// Scroll the page (not an inner panel) so `locator` sits near the top of the window.
async function scrollTo(locator, offset = 90) {
  await locator.evaluate((el, off) => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - off), offset);
  await locator.page().waitForTimeout(250);
}

async function review(page) {
  await page.getByLabel("Text to make safe").fill(NOTE);
  await page.getByRole("button", { name: "Find patient details" }).click();
  await page.getByTestId("preview").getByText("[PATIENT_NAME_").first().waitFor();
}

for (const scheme of ["light", "dark"]) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2, colorScheme: scheme });
  const shot = (name) => page.screenshot({ path: join(shotsDir, `${name}-${scheme}.png`) });
  await page.goto(START);
  await page.getByRole("heading", { level: 1 }).waitFor();
  await review(page);
  await scrollTo(page.getByRole("heading", { name: /Found \d+ patient details/ }), 24);
  await shot("1-remove");
  if (scheme === "light") await page.screenshot({ path: join(helpDir, "remove.png") });
  const coded = await page.getByTestId("preview").textContent();

  await page.getByRole("tab", { name: "Many files (batch)" }).click();
  await shot("2-batch");
  await page.getByRole("tab", { name: "One document" }).click();

  await nav(page, "Check a document");
  await page.getByLabel("Document to check").fill(POISONED);
  await page.getByRole("button", { name: "Check this document" }).click();
  await page.locator("[data-verdict]").waitFor();
  await scrollTo(page.locator("[data-verdict]"), 24);
  await shot("3-check");
  if (scheme === "light") await page.screenshot({ path: join(helpDir, "check.png") });

  await nav(page, "Restore names");
  await page.getByLabel("AI answer with codes").fill(`Discharge summary draft:\n${coded.split("\n").slice(3, 9).join("\n")}\nAlso see [SIN_0badc0de].`);
  await page.locator("main").getByRole("button", { name: "Restore names", exact: true }).click();
  await page.getByTestId("restored").waitFor();
  await scrollTo(page.getByRole("heading", { name: /Restored \d+ of/ }), 24);
  await shot("4-restore");

  await nav(page, "Activity log");
  await page.getByRole("button", { name: "Check the log hasn't been changed" }).click();
  await page.getByText("Log is intact").waitFor();
  await shot("5-activity");

  await nav(page, "Settings");
  await page.locator("#kind-SIN").waitFor();
  await shot("6-settings");

  await nav(page, "Help");
  await shot("7-help");
  await page.close();
}

// GIF frames: paste, find, review, keep one item, copy.  1x scale keeps the GIF small.
const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, colorScheme: "light" });
let n = 0;
const frame = async (holdMs) => {
  await page.waitForTimeout(150);
  await page.screenshot({ path: join(framesDir, `${String(n++).padStart(2, "0")}-${holdMs}.png`) });
};
await page.goto(START);
await page.getByRole("button", { name: "Start over" }).first().click().catch(() => undefined);
await page.getByRole("heading", { level: 1 }).waitFor();
await frame(1200);
await page.getByLabel("Text to make safe").fill(NOTE);
await frame(1500);
await page.getByRole("button", { name: "Find patient details" }).hover();
await frame(700);
await page.getByRole("button", { name: "Find patient details" }).click();
await page.getByTestId("preview").getByText("[PATIENT_NAME_").first().waitFor();
await frame(1800);
await scrollTo(page.getByRole("heading", { name: "Original (only shown on this computer)" }), 16);
await frame(2600);
await scrollTo(page.getByRole("heading", { name: "Review each detail" }), 16);
await frame(1500);
const chip = page.getByRole("group", { name: /Phone number/ });
await chip.getByRole("button", { name: "Keep" }).click();
await page.waitForTimeout(400);
await frame(1800);
await page.evaluate(() => window.scrollTo(0, 0));
await page.getByRole("button", { name: "Copy safe text" }).click();
await page.getByText("Safe text copied").waitFor();
await frame(2600);
await browser.close();
console.log("done");
