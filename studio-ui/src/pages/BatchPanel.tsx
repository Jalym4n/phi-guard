import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Download, FolderOpen, Files, MinusCircle, XCircle } from "lucide-react";
import { api, errorMessage, saveBlob } from "../lib/api";
import { describeCounts } from "../lib/kinds";
import type { BatchStatus, Mode, Settings } from "../lib/types";
import { Banner, Button, Card, formatBytes } from "../components/ui";

interface Picked {
  file: File;
  path: string;
}

const STATUS = {
  done: { icon: CheckCircle2, label: "Done", cls: "text-emerald-700 dark:text-emerald-400" },
  skipped: { icon: MinusCircle, label: "Skipped", cls: "text-slate-600 dark:text-slate-400" },
  error: { icon: XCircle, label: "Couldn't read", cls: "text-red-700 dark:text-red-400" },
} as const;

const VERDICT_LABEL: Record<string, string> = { allow: "Looks safe", review: "Needs review", block: "Do not use" };

export function BatchPanel({ defaultMode }: { defaultMode: Mode }) {
  const [picked, setPicked] = useState<Picked[]>([]);
  const [mode, setMode] = useState<Mode>(defaultMode === "pseudonymize" ? "pseudonymize" : "mask");
  const [job, setJob] = useState<BatchStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [limits, setLimits] = useState<Pick<Settings, "batch_max_files" | "batch_max_mb">>({ batch_max_files: 200, batch_max_mb: 100 });
  const folderInput = useRef<HTMLInputElement>(null);
  const filesInput = useRef<HTMLInputElement>(null);
  const folderSupported = typeof HTMLInputElement !== "undefined" && "webkitdirectory" in HTMLInputElement.prototype;

  useEffect(() => {
    folderInput.current?.setAttribute("webkitdirectory", "");
    api
      .settings()
      .then((s) => setLimits({ batch_max_files: s.settings.batch_max_files, batch_max_mb: s.settings.batch_max_mb }))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!job || job.status !== "running") return;
    const t = setInterval(() => {
      api
        .batchStatus(job.id)
        .then(setJob)
        .catch((e: unknown) => setError(errorMessage(e)));
    }, 400);
    return () => clearInterval(t);
  }, [job]);

  function choose(list: FileList | null) {
    if (!list) return;
    const files = Array.from(list).map((file) => ({ file, path: file.webkitRelativePath || file.name }));
    setPicked(files);
    setJob(null);
    setError(null);
  }

  const totalBytes = picked.reduce((a, p) => a + p.file.size, 0);
  const overLimit =
    picked.length > limits.batch_max_files
      ? `Please choose at most ${limits.batch_max_files} files at a time.`
      : totalBytes > limits.batch_max_mb * 1024 * 1024
        ? `These files add up to ${formatBytes(totalBytes)}, more than the ${limits.batch_max_mb} MB limit for one batch.`
        : null;

  async function start() {
    setError(null);
    try {
      const r = await api.startBatch(picked, mode);
      setJob({ id: r.id, status: "running", total: r.total, processed: 0, items: [] });
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function download() {
    if (!job) return;
    try {
      saveBlob(await api.batchDownload(job.id), "phi-guard-redacted.zip");
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  const pct = job ? Math.round((job.processed / Math.max(1, job.total)) * 100) : 0;

  return (
    <div className="space-y-5">
      {error && <Banner tone="error" onClose={() => setError(null)}>{error}</Banner>}
      <Card>
        <h2 className="text-xl font-semibold">Remove patient details from many files</h2>
        <p className="mt-1 text-slate-700 dark:text-slate-300">
          Choose a folder or several .txt, .docx or .pdf files. You get back a ZIP file with a safe copy of each file
          and a summary sheet. The summary only lists counts, never the details themselves. PDF files come back as
          plain text.
        </p>
        <p className="mt-1 text-slate-600 dark:text-slate-400">
          Limit: {limits.batch_max_files} files or {limits.batch_max_mb} MB per batch (change this in Settings).
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          {folderSupported && (
            <Button onClick={() => folderInput.current?.click()}>
              <FolderOpen aria-hidden className="h-5 w-5" /> Choose a folder…
            </Button>
          )}
          <Button onClick={() => filesInput.current?.click()}>
            <Files aria-hidden className="h-5 w-5" /> Choose files…
          </Button>
          <input ref={folderInput} type="file" multiple className="sr-only" tabIndex={-1} aria-label="Choose a folder" onChange={(e) => choose(e.target.files)} />
          <input
            ref={filesInput}
            type="file"
            multiple
            accept=".txt,.docx,.pdf"
            className="sr-only"
            tabIndex={-1}
            aria-label="Choose files"
            data-testid="batch-files"
            onChange={(e) => choose(e.target.files)}
          />
        </div>
        {picked.length > 0 && (
          <div className="mt-4 space-y-3">
            <p>
              <strong>{picked.length}</strong> file{picked.length > 1 ? "s" : ""} selected ({formatBytes(totalBytes)}).
            </p>
            {overLimit && <Banner tone="warning">{overLimit}</Banner>}
            <fieldset>
              <legend className="font-medium">How should details be removed?</legend>
              <div className="mt-2 flex flex-wrap gap-4">
                <label className="flex items-center gap-2">
                  <input type="radio" name="batch-mode" checked={mode === "mask"} onChange={() => setMode("mask")} className="h-5 w-5" />
                  Remove permanently
                </label>
                <label className="flex items-center gap-2">
                  <input type="radio" name="batch-mode" checked={mode === "pseudonymize"} onChange={() => setMode("pseudonymize")} className="h-5 w-5" />
                  Replace with codes (restorable while Studio is open)
                </label>
              </div>
            </fieldset>
            <Button variant="primary" size="lg" onClick={start} disabled={Boolean(overLimit) || job?.status === "running"}>
              Remove patient details from {picked.length} file{picked.length > 1 ? "s" : ""}
            </Button>
          </div>
        )}
      </Card>

      {job && (
        <Card>
          <h2 className="text-xl font-semibold">{job.status === "running" ? "Working…" : job.status === "done" ? "Finished" : "Something went wrong"}</h2>
          <div className="mt-3">
            <div className="mb-1 flex justify-between">
              <span id="batch-progress-label">Progress</span>
              <span>
                {job.processed} of {job.total}
              </span>
            </div>
            <div
              role="progressbar"
              aria-labelledby="batch-progress-label"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={pct}
              className="h-3 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"
            >
              <div className="h-full bg-teal-700 transition-all dark:bg-teal-400" style={{ width: `${pct}%` }} />
            </div>
          </div>
          {job.status === "done" && (
            <Button variant="primary" size="lg" className="mt-4" onClick={download}>
              <Download aria-hidden className="h-5 w-5" /> Download ZIP
            </Button>
          )}
          {job.items.length > 0 && (
            <table className="mt-4 w-full text-left">
              <caption className="sr-only">Result for each file</caption>
              <thead>
                <tr className="border-b border-slate-300 dark:border-slate-600">
                  <th scope="col" className="py-2 pr-3">File</th>
                  <th scope="col" className="py-2 pr-3">Status</th>
                  <th scope="col" className="py-2 pr-3">Details removed</th>
                  <th scope="col" className="py-2">Document check</th>
                </tr>
              </thead>
              <tbody>
                {job.items.map((it) => {
                  const s = STATUS[it.status];
                  const Icon = s.icon;
                  return (
                    <tr key={it.name} className="border-b border-slate-200 align-top dark:border-slate-700">
                      <td className="py-2 pr-3 font-mono break-all">{it.name}</td>
                      <td className={`py-2 pr-3 ${s.cls}`}>
                        <span className="inline-flex items-center gap-1 font-medium">
                          <Icon aria-hidden className="h-4 w-4" /> {s.label}
                        </span>
                        {it.reason && <span className="block text-slate-600 dark:text-slate-400">{it.reason}</span>}
                      </td>
                      <td className="py-2 pr-3">{it.status === "done" ? describeCounts(it.counts).replace("Found ", "") : "–"}</td>
                      <td className="py-2">{VERDICT_LABEL[it.verdict] ?? "–"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Card>
      )}
    </div>
  );
}
