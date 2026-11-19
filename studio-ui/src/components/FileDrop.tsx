import { useRef, useState, type DragEvent } from "react";
import { Upload } from "lucide-react";

export function FileDrop({
  onFile,
  accept = ".txt,.docx,.pdf",
  label = "Or add a file",
  busy = false,
  testId = "file-input",
}: {
  onFile: (file: File) => void;
  accept?: string;
  label?: string;
  busy?: boolean;
  testId?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  function drop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    const f = e.dataTransfer.files[0];
    if (f) onFile(f);
  }

  return (
    // The drop zone is an extra convenience; the Browse button is the accessible way to pick a file.
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={drop}
      className={`flex flex-wrap items-center gap-3 rounded-lg border-2 border-dashed p-4 ${
        over ? "border-teal-600 bg-teal-50 dark:bg-teal-950" : "border-slate-300 dark:border-slate-600"
      }`}
    >
      <Upload aria-hidden className="h-6 w-6 text-slate-500" />
      <span className="font-medium">{label}:</span>
      <span className="text-slate-600 dark:text-slate-400">drag a .txt, .docx or .pdf file here, or</span>
      <button
        type="button"
        disabled={busy}
        onClick={() => input.current?.click()}
        className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-medium hover:bg-slate-100 dark:border-slate-600 dark:bg-slate-800 dark:hover:bg-slate-700"
      >
        Browse…
      </button>
      <input
        ref={input}
        type="file"
        accept={accept}
        className="sr-only"
        tabIndex={-1}
        aria-label="Choose a file"
        data-testid={testId}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = "";
        }}
      />
    </div>
  );
}
