import { ScanLine } from "lucide-react";
import type { ExtractResult } from "../lib/types";

/**
 * Tells the user the text came from a scan and how sure the OCR was, and shows the
 * scanned pages so they can compare.  OCR mistakes in names and numbers are the
 * main way a scan can leak details, so the check is made prominent.
 */
export function ScanNotice({ file }: { file: Pick<ExtractResult, "ocr" | "previews" | "pages"> }) {
  const { ocr, previews, pages } = file;
  if (!ocr.used) return null;
  const pct = ocr.confidence === null ? null : Math.round(ocr.confidence * 100);
  const unsure = (pct !== null && pct < 85) || ocr.low_confidence_words > 0;
  const which =
    ocr.pages.length === pages
      ? "This text was read from a scanned image"
      : `Page${ocr.pages.length > 1 ? "s" : ""} ${ocr.pages.join(", ")} ${ocr.pages.length > 1 ? "were" : "was"} read from a scanned image`;
  return (
    <div
      role="status"
      data-testid="scan-notice"
      className={`rounded-lg border p-4 ${
        unsure
          ? "border-amber-400 bg-amber-50 text-amber-950 dark:border-amber-600 dark:bg-amber-950 dark:text-amber-50"
          : "border-sky-300 bg-sky-50 text-sky-950 dark:border-sky-700 dark:bg-sky-950 dark:text-sky-50"
      }`}
    >
      <div className="flex gap-3">
        <ScanLine aria-hidden className="mt-0.5 h-5 w-5 shrink-0" />
        <div className="min-w-0 flex-1 space-y-1">
          <p className="font-semibold">{which}</p>
          <p>
            {pct !== null && <>Studio was {pct}% confident overall. </>}
            {ocr.low_confidence_words > 0 && (
              <>
                {ocr.low_confidence_words} word{ocr.low_confidence_words > 1 ? "s were" : " was"} hard to read.{" "}
              </>
            )}
            Check names, dates and numbers against the scan. You can correct the text in the box above before you
            click <strong>Find patient details</strong>.
          </p>
          {previews.length > 0 && (
            <details className="pt-1">
              <summary className="cursor-pointer font-medium underline">
                Show the scanned page{previews.length > 1 ? "s" : ""}
              </summary>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {previews.map((src, i) => (
                  <img
                    key={src.slice(-32)}
                    src={src}
                    alt={`Scanned page ${i + 1}`}
                    className="w-full rounded border border-slate-300 bg-white dark:border-slate-600"
                  />
                ))}
              </div>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}
