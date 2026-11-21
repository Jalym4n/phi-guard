import { useCallback, useEffect, useState } from "react";
import { Download, FolderOpen, Printer, ShieldCheck } from "lucide-react";
import { api, errorMessage, saveBlob } from "../lib/api";
import { describeCounts } from "../lib/kinds";
import type { AuditEntry, AuditPage } from "../lib/types";
import { Banner, Button, Card, PageHeader } from "../components/ui";

export const ACTION_LABELS: Record<string, string> = {
  redact: "Removed patient details",
  check_document: "Checked a document",
  restore: "Restored names",
  check_ai_answer: "Checked an AI answer",
  open_file: "Opened a file",
  batch: "Batch of files",
  start_over: "Started over",
  settings_changed: "Changed settings",
  key_created: "Created a new protection key",
  key_exported: "Exported the protection key",
  key_imported: "Imported a protection key",
  inspect: "Checked text (command line)",
  batch_file: "Batch file (command line)",
};

const VERDICT_LABELS: Record<string, string> = { allow: "Looks safe", review: "Needs review", block: "Do not use" };

function when(ts: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(ts));
}

function details(e: AuditEntry): string {
  if (e.event === "restore") return `${String(e.restored ?? 0)} restored, ${String(e.not_available ?? 0)} not available`;
  if (e.event === "batch") return `${String(e.files ?? 0)} files. ${describeCounts(e.counts ?? {}).replace("Found ", "")}`;
  if (e.event === "open_file") return `${String(e.kind ?? "").toUpperCase()} file, ${String(e.size_kb ?? 0)} KB`;
  if (e.counts) return describeCounts(e.counts).replace("Found ", "");
  if (e.event === "check_document") return `Risk score ${Math.round(Number(e.score ?? 0) * 100)}`;
  return "–";
}

function verdictOf(e: AuditEntry): string {
  if (e.verdict) return VERDICT_LABELS[e.verdict] ?? e.verdict;
  if (e.verdicts?.length) return e.verdicts.map((v) => VERDICT_LABELS[v] ?? v).join(", ");
  return "–";
}

export function ActivityPage() {
  const [data, setData] = useState<AuditPage | null>(null);
  const [filters, setFilters] = useState({ from: "", to: "", action: "", verdict: "" });
  const [page, setPage] = useState(1);
  const [verify, setVerify] = useState<{ ok: boolean; broken_line: number | null; entries: number | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [printing, setPrinting] = useState(false);

  const load = useCallback(async () => {
    const params: Record<string, string> = { page: String(page), page_size: printing ? "500" : "25" };
    if (filters.action) params.action = filters.action;
    if (filters.verdict) params.verdict = filters.verdict;
    if (filters.from) params.since = new Date(`${filters.from}T00:00:00`).toISOString();
    if (filters.to) params.until = new Date(`${filters.to}T23:59:59.999`).toISOString();
    try {
      setData(await api.audit(params));
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [page, filters, printing]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!printing || !data) return;
    const t = setTimeout(() => {
      window.print();
      setPrinting(false);
    }, 200);
    return () => clearTimeout(t);
  }, [printing, data]);

  async function runVerify() {
    setError(null);
    try {
      setVerify(await api.verifyAudit());
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function exportLog() {
    try {
      saveBlob(await api.exportAudit(), "phi-guard-activity-log.jsonl");
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function openFolder() {
    try {
      const r = await api.openLogFolder();
      if (!r.opened) setError(`We couldn't open the folder automatically. It is here: ${r.path}`);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const set = (k: keyof typeof filters) => (v: string) => {
    setPage(1);
    setFilters((f) => ({ ...f, [k]: v }));
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="Activity log"
        intro="A record of what Studio did on this computer. It lists what kind of details were handled and how many, never the details themselves."
      />
      {error && <Banner tone="error" onClose={() => setError(null)}>{error}</Banner>}

      <Card className="no-print">
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary" onClick={runVerify}>
            <ShieldCheck aria-hidden className="h-5 w-5" /> Check the log hasn&apos;t been changed
          </Button>
          <Button onClick={exportLog}>
            <Download aria-hidden className="h-5 w-5" /> Export log (JSONL)
          </Button>
          <Button onClick={() => setPrinting(true)}>
            <Printer aria-hidden className="h-5 w-5" /> Printable summary
          </Button>
          <Button variant="ghost" onClick={openFolder}>
            <FolderOpen aria-hidden className="h-5 w-5" /> Open log folder
          </Button>
        </div>
        {verify && (
          <div className="mt-4">
            {verify.ok ? (
              <Banner tone="success" title="Log is intact">
                {verify.entries === 1
                  ? "The 1 entry in the log has not been edited."
                  : `All ${verify.entries ?? 0} entries are linked together and none has been edited, removed or reordered.`}
              </Banner>
            ) : (
              <Banner tone="error" title={`The log was changed at entry #${verify.broken_line ?? "?"}`}>
                Each entry contains a fingerprint of the one before it. Entry #{verify.broken_line} doesn&apos;t match, which
                means it, or an earlier entry, was edited, deleted or moved after it was written. Entries from that point
                on can&apos;t be trusted. Keep a copy of the file and tell your privacy officer.
              </Banner>
            )}
          </div>
        )}
      </Card>

      <Card className="no-print">
        <h2 className="mb-3 text-lg font-semibold">Filter</h2>
        <div className="flex flex-wrap gap-4">
          <div>
            <label htmlFor="f-from" className="block font-medium">From</label>
            <input id="f-from" type="date" value={filters.from} onChange={(e) => set("from")(e.target.value)} className="mt-1 rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-600 dark:bg-slate-950" />
          </div>
          <div>
            <label htmlFor="f-to" className="block font-medium">To</label>
            <input id="f-to" type="date" value={filters.to} onChange={(e) => set("to")(e.target.value)} className="mt-1 rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-600 dark:bg-slate-950" />
          </div>
          <div>
            <label htmlFor="f-action" className="block font-medium">Action</label>
            <select id="f-action" value={filters.action} onChange={(e) => set("action")(e.target.value)} className="mt-1 rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-600 dark:bg-slate-950">
              <option value="">All actions</option>
              {(data?.actions ?? []).map((a) => (
                <option key={a} value={a}>{ACTION_LABELS[a] ?? a}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="f-verdict" className="block font-medium">Document check result</label>
            <select id="f-verdict" value={filters.verdict} onChange={(e) => set("verdict")(e.target.value)} className="mt-1 rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-600 dark:bg-slate-950">
              <option value="">Any</option>
              <option value="allow">Looks safe</option>
              <option value="review">Needs review</option>
              <option value="block">Do not use</option>
            </select>
          </div>
        </div>
      </Card>

      <Card>
        <h2 className="mb-3 hidden text-xl font-semibold print:block">phi-guard Studio activity summary</h2>
        {data && data.total === 0 ? (
          <p>No activity yet{filters.action || filters.verdict || filters.from || filters.to ? " for these filters" : ""}.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <caption className="sr-only">Activity log entries, newest first</caption>
              <thead>
                <tr className="border-b border-slate-300 dark:border-slate-600">
                  <th scope="col" className="py-2 pr-3">#</th>
                  <th scope="col" className="py-2 pr-3">Time</th>
                  <th scope="col" className="py-2 pr-3">Action</th>
                  <th scope="col" className="py-2 pr-3">Source</th>
                  <th scope="col" className="py-2 pr-3">Details found</th>
                  <th scope="col" className="py-2">Verdict</th>
                </tr>
              </thead>
              <tbody>
                {data?.entries.map((e) => (
                  <tr key={e.seq} className="border-b border-slate-200 align-top dark:border-slate-700">
                    <td className="py-2 pr-3 font-mono">{e.seq}</td>
                    <td className="py-2 pr-3 whitespace-nowrap">{when(e.ts)}</td>
                    <td className="py-2 pr-3">{ACTION_LABELS[e.event] ?? e.event}</td>
                    <td className="py-2 pr-3">{e.source === "studio" ? "Studio" : (e.source ?? "–")}</td>
                    <td className="py-2 pr-3">{details(e)}</td>
                    <td className="py-2">{verdictOf(e)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && pages > 1 && !printing && (
          <nav aria-label="Log pages" className="no-print mt-4 flex items-center gap-3">
            <Button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Newer</Button>
            <span>Page {page} of {pages}</span>
            <Button disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Older</Button>
          </nav>
        )}
      </Card>
    </div>
  );
}
