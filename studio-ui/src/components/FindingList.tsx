import { AlertCircle, Trash2 } from "lucide-react";
import { kindStyle } from "../lib/kinds";

export interface ChipItem {
  id: string;
  start: number;
  kind: string;
  label: string;
  text: string;
  needsCheck: boolean;
  remove: boolean;
  manual: boolean;
}

export function FindingList({
  items,
  onToggle,
  onFocus,
  onDeleteManual,
}: {
  items: ChipItem[];
  onToggle: (id: string, remove: boolean) => void;
  onFocus: (id: string) => void;
  onDeleteManual: (id: string) => void;
}) {
  if (items.length === 0) return <p className="text-slate-600 dark:text-slate-400">Nothing found yet.</p>;
  return (
    <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3" aria-label="Patient details found">
      {items.map((it) => {
        const style = kindStyle(it.kind);
        return (
          <li
            key={it.id}
            className={`flex flex-col gap-2 rounded-lg border p-3 ${
              it.remove ? "border-slate-300 dark:border-slate-600" : "border-dashed border-slate-400 bg-slate-100 dark:border-slate-500 dark:bg-slate-800"
            }`}
          >
            <button
              type="button"
              onClick={() => onFocus(it.id)}
              className="flex min-w-0 items-center gap-2 rounded text-left hover:underline"
              aria-label={`Show ${it.label} “${it.text}” in the text`}
            >
              <span className={`shrink-0 rounded px-1.5 py-0.5 text-sm font-semibold ${style.className}`}>{it.label}</span>
              <span className="truncate font-mono">{it.text}</span>
            </button>
            <div className="flex flex-wrap items-center gap-2">
              {it.needsCheck && (
                <span className="inline-flex items-center gap-1 rounded bg-amber-100 px-2 py-0.5 text-sm font-medium text-amber-950 dark:bg-amber-900 dark:text-amber-50">
                  <AlertCircle aria-hidden className="h-4 w-4" /> Please check
                </span>
              )}
              {it.manual && <span className="text-sm text-slate-600 dark:text-slate-400">Added by you</span>}
              <div role="group" aria-label={`${it.label} “${it.text}”`} className="ml-auto inline-flex rounded-md border border-slate-300 dark:border-slate-600">
                <button
                  type="button"
                  aria-pressed={it.remove}
                  onClick={() => onToggle(it.id, true)}
                  className={`rounded-l-md px-3 py-1 font-medium ${it.remove ? "bg-teal-700 text-white dark:bg-teal-400 dark:text-slate-950" : ""}`}
                >
                  Remove
                </button>
                {it.manual ? (
                  <button
                    type="button"
                    onClick={() => onDeleteManual(it.id)}
                    className="inline-flex items-center gap-1 rounded-r-md px-3 py-1 font-medium"
                    aria-label={`Undo: don't remove “${it.text}”`}
                  >
                    <Trash2 aria-hidden className="h-4 w-4" /> Undo
                  </button>
                ) : (
                  <button
                    type="button"
                    aria-pressed={!it.remove}
                    onClick={() => onToggle(it.id, false)}
                    className={`rounded-r-md px-3 py-1 font-medium ${!it.remove ? "bg-slate-700 text-white dark:bg-slate-300 dark:text-slate-950" : ""}`}
                  >
                    Keep
                  </button>
                )}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
