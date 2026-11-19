import { useState } from "react";
import { ClipboardCopy, KeyRound, ShieldAlert, ScanSearch } from "lucide-react";
import { api, errorMessage } from "../lib/api";
import { describeCounts } from "../lib/kinds";
import type { Finding, RestoreResult } from "../lib/types";
import { Banner, Button, Card, PageHeader, TextArea } from "../components/ui";

export function RestorePage() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<RestoreResult | null>(null);
  const [leaks, setLeaks] = useState<Finding[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function restore() {
    setError(null);
    setNotice(null);
    setLeaks(null);
    if (!text.trim()) {
      setError("Paste the AI's answer first.");
      return;
    }
    try {
      setResult(await api.restore(text));
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function checkAnswer() {
    setError(null);
    setResult(null);
    if (!text.trim()) {
      setError("Paste the AI's answer first.");
      return;
    }
    try {
      setLeaks((await api.outputScan(text)).findings);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function copy() {
    if (!result) return;
    await navigator.clipboard.writeText(result.text).catch(() => undefined);
    setNotice("Copied. Remember: this text contains real patient details.");
  }

  const leakCounts: Record<string, number> = {};
  for (const f of leaks ?? []) leakCounts[f.kind] = (leakCounts[f.kind] ?? 0) + 1;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Restore names"
        intro="Got an answer back from an AI tool with codes like [PATIENT_NAME_a2b6c3d4]? Paste it here to put the real details back for your own records."
      />
      <Banner tone="warning" title="This shows real patient details." role="alert">
        Only use it on your own computer for authorized work. Don&apos;t paste the restored text back into an AI tool.
      </Banner>
      {error && <Banner tone="error" onClose={() => setError(null)}>{error}</Banner>}
      {notice && <Banner tone="success" onClose={() => setNotice(null)}>{notice}</Banner>}
      <Card>
        <div className="space-y-4">
          <TextArea id="restore-text" label="AI answer with codes" value={text} onChange={setText} rows={10} placeholder="Paste the AI's answer here…" />
          <div className="flex flex-wrap gap-3">
            <Button variant="primary" size="lg" onClick={restore}>
              <KeyRound aria-hidden className="h-5 w-5" /> Restore names
            </Button>
            <Button onClick={checkAnswer}>
              <ScanSearch aria-hidden className="h-5 w-5" /> Check this answer for leaked details
            </Button>
          </div>
        </div>
      </Card>

      {result && (
        <Card>
          <h2 className="text-xl font-semibold" aria-live="polite">
            Restored {result.restored} of {result.codes_found} code{result.codes_found === 1 ? "" : "s"}.
          </h2>
          {result.not_available.length > 0 && (
            <Banner tone="info" title={`${result.not_available.length} code${result.not_available.length > 1 ? "s are" : " is"} not available`}>
              <p>
                For your protection, codes are only stored while Studio is open. They are cleared when you click
                &ldquo;Start over&rdquo;, close Studio, leave it idle, or create a new protection key.
              </p>
              <ul className="mt-2 flex flex-wrap gap-2">
                {result.not_available.map((t) => (
                  <li key={t} className="rounded bg-white/60 px-2 py-0.5 font-mono dark:bg-black/30">
                    {t}
                  </li>
                ))}
              </ul>
            </Banner>
          )}
          <pre data-testid="restored" className="doc-text mt-4 max-h-[32rem] overflow-auto rounded-lg border border-amber-400 bg-amber-50/50 p-4 font-mono dark:border-amber-700 dark:bg-amber-950/30">
            {result.text}
          </pre>
          <Button className="mt-3" onClick={copy}>
            <ClipboardCopy aria-hidden className="h-5 w-5" /> Copy restored text
          </Button>
        </Card>
      )}

      {leaks && (
        <Card>
          {leaks.length === 0 ? (
            <Banner tone="success" title="No patient details found in this answer.">
              Only codes Studio created, or no identifiers at all.
            </Banner>
          ) : (
            <Banner tone="warning" title="This answer may contain patient details">
              <p>{describeCounts(leakCounts)} The AI should only see codes, so these may have leaked from somewhere else or been made up. Check before using the answer.</p>
              <ul className="mt-2 list-disc pl-6">
                {leaks.map((f) => (
                  <li key={f.id}>
                    <ShieldAlert aria-hidden className="mr-1 inline h-4 w-4" />
                    {f.label}: <span className="font-mono">{f.text}</span>
                  </li>
                ))}
              </ul>
            </Banner>
          )}
        </Card>
      )}
    </div>
  );
}
