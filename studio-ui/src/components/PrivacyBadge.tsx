import { useState } from "react";
import { Lock } from "lucide-react";
import { Dialog } from "./ui";

export function PrivacyBadge() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 rounded-full border border-emerald-600 bg-emerald-50 px-3 py-1.5 font-medium text-emerald-900 hover:bg-emerald-100 dark:border-emerald-500 dark:bg-emerald-950 dark:text-emerald-100 dark:hover:bg-emerald-900"
      >
        <Lock aria-hidden className="h-4 w-4" />
        Runs only on this computer. Nothing is uploaded.
      </button>
      <Dialog open={open} onClose={() => setOpen(false)} title="Your information stays on this computer">
        <div className="space-y-3 text-base">
          <p>
            phi-guard Studio is a small program running on this computer. The page you are looking at talks only to
            that program, at an address that other computers cannot reach (<code>127.0.0.1</code>).
          </p>
          <ul className="list-disc space-y-1 pl-6">
            <li>Text and files you add are processed in this computer&apos;s memory and are not saved.</li>
            <li>Studio never connects to the internet. It has no analytics or tracking.</li>
            <li>
              Codes that let you restore names are kept in memory only, and are cleared when you click
              &ldquo;Start over&rdquo;, close Studio, or leave it idle.
            </li>
            <li>The activity log records what was done (for example &ldquo;3 names removed&rdquo;), never the details themselves.</li>
          </ul>
          <p>
            You can check this yourself: disconnect from the internet and Studio keeps working exactly the same. See
            Help for more.
          </p>
        </div>
      </Dialog>
    </>
  );
}
