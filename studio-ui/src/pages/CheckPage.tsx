import { useState } from "react";
import { FileSearch, RotateCcw } from "lucide-react";
import { api, errorMessage } from "../lib/api";
import { CLEAN_POLICY, POISONED_DOC } from "../lib/examples";
import type { InjectResult } from "../lib/types";
import { FileDrop } from "../components/FileDrop";
import { HighlightedText, type Highlight } from "../components/HighlightedText";
import { Banner, Button, Card, PageHeader, TextArea, Toggle } from "../components/ui";
import { RiskMeter, VerdictCard } from "../components/Verdict";

const RULE_TAG: Record<string, string> = {
  instruction_override: "Ignore rules",
  role_hijack: "Pretend",
  system_prompt_probe: "Reveal instructions",
  fake_delimiter: "Fake marker",
  data_exfiltration: "Send data",
  markdown_image_exfil: "Hidden image link",
  tool_abuse: "Run commands",
  safety_bypass: "Switch off safety",
  task_replacement: "New task",
  hidden_characters: "Invisible text",
  lookalike_characters: "Look-alike letters",
};

export function CheckPage() {
  const [text, setText] = useState("");
  const [checked, setChecked] = useState<string | null>(null);
  const [result, setResult] = useState<InjectResult | null>(null);
  const [showCleaned, setShowCleaned] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  async function check() {
    setError(null);
    if (!text.trim()) {
      setError("Paste a document or add a file first.");
      return;
    }
    setBusy(true);
    try {
      setResult(await api.inject(text));
      setChecked(text);
      setShowCleaned(false);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function onFile(f: File) {
    setError(null);
    try {
      const r = await api.extract(f);
      setText(r.text);
      setFileName(r.filename);
      setResult(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  // Group findings by rule so each explanation is listed once.
  const groups = new Map<string, { explanation: string; matches: string[] }>();
  for (const f of result?.findings ?? []) {
    const key = f.source === "base64" ? "base64" : f.rule;
    const g = groups.get(key) ?? { explanation: f.explanation, matches: [] };
    if (f.rule !== "hidden_characters") g.matches.push(f.match);
    groups.set(key, g);
  }

  const highlights: Highlight[] = (result?.findings ?? [])
    .filter((f) => f.end > f.start)
    .map((f, i) => ({
      id: `inj-${i}`,
      start: f.start,
      end: f.end,
      kind: "OTHER",
      label: f.source === "base64" ? "Encoded" : (RULE_TAG[f.rule] ?? "Suspicious"),
      className: "bg-red-100 text-red-950 dark:bg-red-900 dark:text-red-50",
    }));

  return (
    <div className="space-y-5">
      <PageHeader
        title="Check a document"
        intro="Before a document goes into an AI tool or knowledge base, check it for hidden instructions that try to manipulate the AI (called “prompt injection”)."
      />
      {error && <Banner tone="error" onClose={() => setError(null)}>{error}</Banner>}
      <Card>
        <div className="space-y-4">
          <TextArea id="check-text" label="Document to check" value={text} onChange={(v) => { setText(v); setFileName(null); }} rows={10} placeholder="Paste the document here…" />
          {fileName && <p>Loaded <strong>{fileName}</strong>.</p>}
          <FileDrop onFile={onFile} testId="check-file-input" />
          <div className="flex flex-wrap gap-3">
            <Button variant="primary" size="lg" onClick={check} disabled={busy}>
              <FileSearch aria-hidden className="h-5 w-5" /> {busy ? "Checking…" : "Check this document"}
            </Button>
            <Button variant="ghost" onClick={() => { setText(POISONED_DOC); setResult(null); setFileName(null); }}>
              Try a tampered example
            </Button>
            <Button variant="ghost" onClick={() => { setText(CLEAN_POLICY); setResult(null); setFileName(null); }}>
              Try a normal policy
            </Button>
            {text && (
              <Button variant="ghost" onClick={() => { setText(""); setResult(null); setChecked(null); setFileName(null); }}>
                <RotateCcw aria-hidden className="h-5 w-5" /> Start over
              </Button>
            )}
          </div>
        </div>
      </Card>

      {result && checked !== null && (
        <>
          <VerdictCard verdict={result.verdict} title={result.title} detail={result.detail} />
          <Card>
            <RiskMeter score={result.score} verdict={result.verdict} />
          </Card>
          {groups.size > 0 && (
            <Card>
              <h2 className="mb-3 text-xl font-semibold">What we found</h2>
              <ul className="space-y-3">
                {[...groups.entries()].map(([key, g]) => (
                  <li key={key} className="rounded-lg border border-slate-300 p-3 dark:border-slate-600">
                    <p className="font-medium">{g.explanation}</p>
                    {g.matches.length > 0 && (
                      <p className="mt-1 break-words font-mono text-slate-700 dark:text-slate-300">“{g.matches[0]?.trim().slice(0, 160)}”{g.matches.length > 1 ? ` and ${g.matches.length - 1} more` : ""}</p>
                    )}
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-slate-600 dark:text-slate-400">
                This check looks for known warning signs. It can miss new tricks, so a document marked safe still needs
                ordinary care.
              </p>
            </Card>
          )}
          <Card>
            <h2 className="mb-2 text-xl font-semibold">The document, with warning signs highlighted</h2>
            <Toggle
              id="show-cleaned"
              checked={showCleaned}
              onChange={setShowCleaned}
              label="Show me the cleaned version"
              description="Removes invisible characters and converts look-alike or special letters to plain text, so you can see what the AI would read."
            />
            <div className="mt-3">
              {showCleaned ? (
                <pre data-testid="cleaned" className="doc-text max-h-[32rem] overflow-auto rounded-lg border border-slate-300 bg-white p-4 font-mono dark:border-slate-600 dark:bg-slate-950">
                  {result.cleaned_text}
                </pre>
              ) : (
                <HighlightedText text={checked} highlights={highlights} label="Document with suspicious passages highlighted" />
              )}
            </div>
            {result.hidden_characters > 0 && (
              <Banner tone="warning">
                This document contains {result.hidden_characters} invisible character{result.hidden_characters > 1 ? "s" : ""}.
              </Banner>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
