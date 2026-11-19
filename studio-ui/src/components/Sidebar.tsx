import { Eraser, FileSearch, HelpCircle, History, KeyRound, Settings as SettingsIcon } from "lucide-react";

export type PageId = "remove" | "check" | "restore" | "activity" | "settings" | "help";

export const PAGES: { id: PageId; label: string; icon: typeof Eraser }[] = [
  { id: "remove", label: "Remove patient details", icon: Eraser },
  { id: "check", label: "Check a document", icon: FileSearch },
  { id: "restore", label: "Restore names", icon: KeyRound },
  { id: "activity", label: "Activity log", icon: History },
  { id: "settings", label: "Settings", icon: SettingsIcon },
  { id: "help", label: "Help", icon: HelpCircle },
];

export function Sidebar({ current, onNavigate }: { current: PageId; onNavigate: (p: PageId) => void }) {
  return (
    <nav aria-label="Main" className="no-print w-64 shrink-0 border-r border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      <ul className="space-y-1">
        {PAGES.map(({ id, label, icon: Icon }) => {
          const active = id === current;
          return (
            <li key={id} className={id === "help" ? "mt-4 border-t border-slate-200 pt-4 dark:border-slate-700" : ""}>
              <button
                type="button"
                onClick={() => onNavigate(id)}
                aria-current={active ? "page" : undefined}
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-base font-medium ${
                  active
                    ? "bg-teal-700 text-white dark:bg-teal-400 dark:text-slate-950"
                    : "text-slate-800 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
                }`}
              >
                <Icon aria-hidden className="h-5 w-5 shrink-0" />
                {label}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
