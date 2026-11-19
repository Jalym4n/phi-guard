import { forwardRef, type ReactNode } from "react";
import { kindStyle } from "../lib/kinds";

export interface Highlight {
  id: string;
  start: number;
  end: number;
  kind: string;
  /** Overrides the default label for the kind (e.g. an injection rule name). */
  label?: string;
  needsCheck?: boolean;
  kept?: boolean;
  className?: string;
}

/**
 * Shows `text` with highlighted spans.  Each highlight includes a small visible
 * label (e.g. "Name") so the meaning never depends on colour alone.  Labels are
 * marked `data-skip` so text selection offsets ignore them.
 */
export const HighlightedText = forwardRef<HTMLDivElement, { text: string; highlights: Highlight[]; label: string; flashId?: string | null }>(
  function HighlightedText({ text, highlights, label, flashId }, ref) {
    const sorted = [...highlights].sort((a, b) => a.start - b.start || b.end - a.end);
    const parts: ReactNode[] = [];
    let cursor = 0;
    for (const h of sorted) {
      if (h.start < cursor) continue; // overlapping highlights are not expected; skip defensively
      if (h.start > cursor) parts.push(<span key={`t${cursor}`}>{text.slice(cursor, h.start)}</span>);
      const style = kindStyle(h.kind);
      const tag = h.label ?? style.label;
      parts.push(
        <mark
          key={h.id}
          id={`hl-${h.id}`}
          data-kind={h.kind}
          className={`rounded px-0.5 ${h.className ?? style.className} ${
            h.kept ? "opacity-70 outline-dashed outline-2 outline-offset-1 outline-slate-500" : ""
          } ${flashId === h.id ? "motion-safe:animate-flash outline outline-4 outline-blue-600" : ""}`}
        >
          <span data-skip aria-hidden className="mr-1 select-none rounded bg-black/10 px-1 align-middle text-[0.7rem] font-semibold uppercase tracking-wide dark:bg-white/15">
            {tag}
            {h.kept ? " · kept" : ""}
            {h.needsCheck ? " · check" : ""}
          </span>
          <span className="sr-only">{`${tag}${h.kept ? ", kept" : ""}: `}</span>
          <span>{text.slice(h.start, h.end)}</span>
        </mark>,
      );
      cursor = h.end;
    }
    if (cursor < text.length) parts.push(<span key={`t${cursor}`}>{text.slice(cursor)}</span>);
    return (
      <div
        ref={ref}
        // Scrollable regions must be keyboard-focusable so keyboard users can scroll them (WCAG 2.1.1).
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
        tabIndex={0}
        role="region"
        aria-label={label}
        className="doc-text max-h-[32rem] min-h-[12rem] overflow-auto rounded-lg border border-slate-300 bg-white p-4 font-mono text-base leading-8 dark:border-slate-600 dark:bg-slate-950"
      >
        {parts}
      </div>
    );
  },
);
