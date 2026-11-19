import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { copySafeText, findDetails, fixture, go, mainButton, open, TOKEN } from "./helpers";

const NOTE = `SYNTHETIC NOTE
Patient: Eleanor Whitfield
DOB: 1957-04-23
Phone: (416) 555-0142
Seen at Lakeview Family Health Team. Follow-up in 3 weeks.
`;

test.beforeEach(async ({ page }) => {
  await open(page);
});

test("paste, find and copy a safe version in three steps", async ({ page }) => {
  await findDetails(page, NOTE);
  await expect(page.getByRole("heading", { name: /Found 3 patient details: 1 name, 1 date of birth, 1 phone number/ })).toBeVisible();
  const preview = page.getByTestId("preview");
  await expect(preview).not.toContainText("Whitfield");
  await expect(preview).toContainText("[PATIENT_NAME_");
  const clip = await copySafeText(page);
  expect(clip).toContain("Follow-up in 3 weeks");
  expect(clip).not.toContain("Whitfield");
  expect(clip).not.toContain("555-0142");
});

test("remove permanently uses type labels", async ({ page }) => {
  await findDetails(page, NOTE);
  await page.getByLabel(/Remove permanently/).check();
  await expect(page.getByTestId("preview")).toContainText("Patient: [PATIENT_NAME]");
});

test("Keep toggle is honoured in the output", async ({ page }) => {
  await findDetails(page, NOTE);
  const chip = page.getByRole("group", { name: /Phone number/ });
  await chip.getByRole("button", { name: "Keep" }).click();
  await expect(chip.getByRole("button", { name: "Keep" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("preview")).toContainText("(416) 555-0142");
  await expect(page.getByTestId("preview")).not.toContainText("Whitfield");
  expect(await copySafeText(page)).toContain("(416) 555-0142");
});

test("manual additions: typed phrase and text selection", async ({ page }) => {
  await findDetails(page, NOTE);
  await page.getByLabel("Add a word or phrase to remove").fill("Lakeview Family Health Team");
  await page.getByRole("button", { name: "Also remove this" }).click();
  await expect(page.getByTestId("preview")).not.toContainText("Lakeview");
  await expect(page.getByText("Added by you")).toBeVisible();

  // Select "3 weeks" with the mouse-style selection API, then use the selection toolbar.
  await page.evaluate(() => {
    const region = document.querySelector('[aria-label="Original text with patient details highlighted"]')!;
    const walker = document.createTreeWalker(region, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const i = (n.textContent ?? "").indexOf("3 weeks");
      if (i >= 0) {
        const r = document.createRange();
        r.setStart(n, i);
        r.setEnd(n, i + "3 weeks".length);
        const sel = window.getSelection()!;
        sel.removeAllRanges();
        sel.addRange(r);
        region.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
        return;
      }
    }
    throw new Error("text not found");
  });
  const bar = page.getByRole("group", { name: "Also remove the selected text" });
  await expect(bar).toContainText("“3 weeks”");
  await bar.getByRole("button", { name: "Other" }).click();
  await expect(page.getByTestId("preview")).toContainText("Follow-up in [OTHER_");
});

test("clicking a finding scrolls to and flashes the highlight", async ({ page }) => {
  await findDetails(page, NOTE);
  await page.getByRole("button", { name: /Show in text: Phone number/ }).click();
  await expect(page.locator("mark[data-kind=PHONE]")).toHaveClass(/outline-blue-600/);
});

test("try an example and start over clears everything", async ({ page }) => {
  await page.getByRole("button", { name: "Try an example" }).click();
  await page.getByRole("button", { name: "Find patient details" }).click();
  await expect(page.getByRole("heading", { name: /Found \d+ patient details/ })).toBeVisible();
  await page.getByRole("button", { name: "Start over" }).first().click();
  await expect(page.getByLabel("Text to make safe")).toHaveValue("");
  await expect(page.getByText(/Everything was cleared/)).toBeVisible();
});

test("upload a .docx and download a redacted .docx", async ({ page, request }) => {
  await page.getByTestId("file-input").setInputFiles(fixture("referral.docx"));
  await expect(page.getByText("referral.docx")).toBeVisible();
  await expect(page.getByLabel("Text to make safe")).toHaveValue(/Patient: Eleanor Whitfield/);
  await page.getByRole("button", { name: "Find patient details" }).click();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download Word file" }).click()]);
  expect(download.suggestedFilename()).toBe("referral-redacted.docx");
  const body = readFileSync((await download.path())!);
  // Read the downloaded file back through Studio itself to check its text.
  const r = await request.post("/api/extract", {
    headers: { "X-PHI-Guard-Token": TOKEN },
    multipart: { file: { name: "out.docx", mimeType: "application/octet-stream", buffer: body } },
  });
  const text = (await r.json()).text as string;
  expect(text).toContain("Patient: [PATIENT_NAME_");
  expect(text).not.toContain("Whitfield");
  expect(text).toContain("Please assess for persistent cough.");
});

test("upload a text PDF; a scanned PDF gets a friendly message", async ({ page }) => {
  await page.getByTestId("file-input").setInputFiles(fixture("lab-report.pdf"));
  await expect(page.getByLabel("Text to make safe")).toHaveValue(/Eleanor Whitfield/);
  await page.getByTestId("file-input").setInputFiles(fixture("scanned.pdf"));
  await expect(page.getByRole("alert")).toContainText("scanned image");
});

test("injection check: tampered document is red, normal policy is green", async ({ page }) => {
  await go(page, "Check a document");
  await page.getByTestId("check-file-input").setInputFiles(fixture("poisoned_doc.txt"));
  await expect(page.getByLabel("Document to check")).toHaveValue(/Lab Requisitions/);
  await page.getByRole("button", { name: "Check this document" }).click();
  const verdict = page.locator("[data-verdict]");
  await expect(verdict).toHaveAttribute("data-verdict", "block");
  await expect(verdict).toContainText("Do not use this document");
  await expect(page.getByText("Contains text that tries to make the AI ignore its rules.")).toBeVisible();
  await expect(page.getByRole("meter", { name: "Risk score" })).toHaveAttribute("aria-valuenow", /^(7\d|8\d|9\d|100)$/);
  await page.getByRole("switch", { name: "Show me the cleaned version" }).click();
  await expect(page.getByTestId("cleaned")).toBeVisible();

  await page.getByTestId("check-file-input").setInputFiles(fixture("clean_policy.txt"));
  await expect(page.getByLabel("Document to check")).toHaveValue(/Hand Hygiene/);
  await page.getByRole("button", { name: "Check this document" }).click();
  await expect(verdict).toHaveAttribute("data-verdict", "allow");
  await expect(verdict).toContainText("Looks safe");
});

test("restore names within the session and explain unavailable codes", async ({ page }) => {
  await findDetails(page, NOTE);
  const coded = (await page.getByTestId("preview").textContent())!;
  await go(page, "Restore names");
  await expect(page.getByText("This shows real patient details.")).toBeVisible();
  await page.getByLabel("AI answer with codes").fill(`${coded}\nAlso see [SIN_0badc0de].`);
  await mainButton(page, "Restore names").click();
  await expect(page.getByTestId("restored")).toContainText("Patient: Eleanor Whitfield");
  await expect(page.getByText(/1 code is not available/)).toBeVisible();
  await expect(page.getByText(/codes are only stored while Studio is open/)).toBeVisible();

  await page.getByLabel("AI answer with codes").fill(`${coded}\nCall her at 905-555-0177.`);
  await page.getByRole("button", { name: "Check this answer for leaked details" }).click();
  await expect(page.getByText("This answer may contain patient details")).toBeVisible();
});

test("batch: several files in, ZIP out", async ({ page }) => {
  await page.getByRole("tab", { name: "Many files (batch)" }).click();
  await page.getByTestId("batch-files").setInputFiles([fixture("referral.docx"), fixture("lab-report.pdf"), fixture("scanned.pdf")]);
  await page.getByRole("button", { name: /Remove patient details from 3 files/ }).click();
  await expect(page.getByRole("heading", { name: "Finished" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "scanned.pdf" })).toBeVisible();
  await expect(page.getByRole("cell", { name: /Couldn't read/ })).toBeVisible();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download ZIP" }).click()]);
  expect(download.suggestedFilename()).toBe("phi-guard-redacted.zip");
});

test("activity log is intact and has no patient details", async ({ page }) => {
  await findDetails(page, NOTE);
  await copySafeText(page);
  await go(page, "Activity log");
  await expect(page.getByRole("cell", { name: "Removed patient details" }).first()).toBeVisible();
  await expect(page.locator("table")).not.toContainText("Whitfield");
  await page.getByRole("button", { name: "Check the log hasn't been changed" }).click();
  await expect(page.getByText("Log is intact")).toBeVisible();
});

test("settings: an always-remove word list changes what is found", async ({ page }) => {
  await go(page, "Settings");
  await page.getByRole("textbox", { name: "Always remove these words" }).fill("Lakeview");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText("Settings saved.")).toBeVisible();
  await go(page, "Remove patient details");
  await findDetails(page, NOTE);
  await expect(page.getByRole("group", { name: /Your word list “Lakeview”/ })).toBeVisible();
  await expect(page.getByTestId("preview")).not.toContainText("Lakeview");
  // Clean up for later tests.
  await go(page, "Settings");
  await page.getByRole("textbox", { name: "Always remove these words" }).fill("");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText("Settings saved.")).toBeVisible();
});

test("settings: theme and text size apply immediately", async ({ page }) => {
  await go(page, "Settings");
  await page.getByLabel("Dark").check();
  await page.getByLabel("Larger").check();
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await expect(page.locator("html")).toHaveAttribute("data-text-size", "larger");
  await page.getByLabel("Same as my computer").check();
  await page.getByLabel("Normal").check();
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-text-size", "normal");
});

test("security in the browser: token removed from URL, nothing in storage, no CSP violations", async ({ page }) => {
  await page.goto("about:blank");
  const errors = await open(page);
  expect(page.url()).not.toContain("token");
  await findDetails(page, NOTE);
  await go(page, "Check a document");
  const storage = await page.evaluate(() => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }));
  expect(storage).not.toContain("Whitfield");
  expect(storage).not.toContain("555-0142");
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
  expect(errors.filter((e) => /Content Security Policy|Refused/.test(e))).toEqual([]);
});

test("opening Studio without its token shows a friendly message", async ({ browser }) => {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Please open Studio from its shortcut" })).toBeVisible();
  await ctx.close();
});

test("the privacy badge explains what stays on the computer", async ({ page }) => {
  await page.getByRole("button", { name: /Runs only on this computer/ }).click();
  const dialog = page.getByRole("dialog", { name: "Your information stays on this computer" });
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});
