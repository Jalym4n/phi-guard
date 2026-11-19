import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ClipboardCopy, Download, FileText, RotateCcw, Search, Sparkles } from "lucide-react";
import { api, errorMessage, saveBlob, type RedactOptions } from "../lib/api";
import { EXAMPLE_NOTE } from "../lib/examples";
import { describeCounts, kindStyle, MANUAL_KINDS } from "../lib/kinds";
import { findAll, selectionOffsets, trimSpan } from "../lib/selection";
import type { ExtractResult, Finding, ManualKind, ManualSpan, Mode } from "../lib/types";
import { FileDrop } from "../components/FileDrop";
import { FindingList, type ChipItem } from "../components/FindingList";
import { HighlightedText, type Highlight } from "../components/HighlightedText";
import { Banner, Button, Card, PageHeader, TextArea, formatBytes } from "../components/ui";
import { BatchPanel } from "./BatchPanel";

interface Props {
  defaultMode: Mode;
}

function overlaps(a: { start: number; end: number }, b: { start: number; end: number }) {
  return a.start < b.end && b.start < a.end;
}

export function RemovePage({ defaultMode }: Props) {
  const [tab, setTab] = useState<"single" | "batch">("single");
  return (
    <div>
      <PageHeader
        title="Remove patient details"
        intro="Paste a note or add a file. Studio finds names, health card numbers, dates of birth and other details, and gives you a safe copy to use with AI tools."
      />
      <div role="tablist" aria-label="How many documents" className="no-print mb-5 inline-flex rounded-lg border border-slate-300 bg-white p-1 dark:border-slate-600 dark:bg-slate-900">
        {(
          [
            ["single", "One document"],
            ["batch", "Many files (batch)"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`tab-${id}`}
            aria-selected={tab === id}
            aria-controls={`panel-${id}`}
            onClick={() => setTab(id)}
            className={`rounded-md px-4 py-2 font-medium ${tab === id ? "bg-teal-700 text-white dark:bg-teal-400 dark:text-slate-950" : ""}`}
          >
            {label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "single" ? <SingleDocument defaultMode={defaultMode} /> : <BatchPanel defaultMode={defaultMode} />}
      </div>
    </div>
  );
}

function SingleDocument({ defaultMode }: Props) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileInfo, setFileInfo] = useState<ExtractResult | null>(null);
  const [reviewText, setReviewText] = useState<string | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [keep, setKeep] = useState<Set<string>>(new Set());
  const [manual, setManual] = useState<ManualSpan[]>([]);
  const [mode, setMode] = useState<Mode>(defaultMode);
  const [preview, setPreview] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selection, setSelection] = useState<{ start: number; end: number } | null>(null);
  const [phrase, setPhrase] = useState("");
  const [phraseKind, setPhraseKind] = useState<ManualKind>("OTHER");
  const [flashId, setFlashId] = useState<string | null>(null);
  const originalRef = useRef<HTMLDivElement>(null);
  const resultsRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => setMode(defaultMode), [defaultMode]);

  // Detected findings hidden under a manual selection are covered by it (manual always wins).
  const visibleFindings = useMemo(
    () => findings.filter((f) => !manual.some((m) => overlaps(f, m))),
    [findings, manual],
  );

  const options = useMemo<RedactOptions>(
    () => ({
      mode,
      keep: visibleFindings.filter((f) => keep.has(f.id)).map(({ start, end }) => ({ start, end })),
      manual: manual.map(({ start, end, kind }) => ({ start, end, kind })),
    }),
    [mode, visibleFindings, keep, manual],
  );

  // Live preview (not written to the activity log).
  useEffect(() => {
    if (reviewText === null) return;
    let cancelled = false;
    const t = setTimeout(() => {
      api
        .redact(reviewText, options)
        .then((r) => !cancelled && setPreview(r.text))
        .catch((e: unknown) => !cancelled && setError(errorMessage(e)));
    }, 120);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [reviewText, options]);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const f of visibleFindings) if (!keep.has(f.id)) c[f.kind] = (c[f.kind] ?? 0) + 1;
    for (const m of manual) c[m.kind] = (c[m.kind] ?? 0) + 1;
    return c;
  }, [visibleFindings, keep, manual]);

  const foundCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const k of [...visibleFindings.map((f) => f.kind), ...manual.map((m) => m.kind)]) c[k] = (c[k] ?? 0) + 1;
    return c;
  }, [visibleFindings, manual]);

  const totalFound = visibleFindings.length + manual.length;

  async function find() {
    setError(null);
    setNotice(null);
    if (!text.trim()) {
      setError("Paste some text or add a file first.");
      return;
    }
    setBusy(true);
    try {
      const r = await api.scan(text);
      setFindings(r.findings);
      setKeep(new Set());
      setManual([]);
      setReviewText(text);
      setPreview("");
      setTimeout(() => resultsRef.current?.focus(), 0);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function onFile(f: File) {
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const r = await api.extract(f);
      setFile(f);
      setFileInfo(r);
      setText(r.text);
      setReviewText(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function startOver() {
    setText("");
    setFile(null);
    setFileInfo(null);
    setReviewText(null);
    setFindings([]);
    setKeep(new Set());
    setManual([]);
    setPreview("");
    setSelection(null);
    setPhrase("");
    setError(null);
    setNotice("Everything was cleared, including the codes kept in memory.");
    try {
      await api.clearSession();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function copy() {
    if (reviewText === null) return;
    setError(null);
    try {
      const r = await api.redact(reviewText, options, true);
      try {
        await navigator.clipboard.writeText(r.text);
      } catch {
        const ta = document.createElement("textarea");
        ta.value = r.text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
      }
      setNotice("Safe text copied. You can paste it into your AI tool.");
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function download() {
    if (reviewText === null) return;
    setError(null);
    const stem = (fileInfo?.filename ?? "note.txt").replace(/\.[^.]+$/, "");
    try {
      if (file && fileInfo?.kind === "docx") {
        saveBlob(await api.redactDocx(file, options), `${stem}-redacted.docx`);
      } else {
        const r = await api.redact(reviewText, options, true);
        saveBlob(new Blob([r.text], { type: "text/plain;charset=utf-8" }), `${stem}-redacted.txt`);
      }
      setNotice("Download started. The saved file contains the safe version only.");
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  const captureSelection = useCallback(() => {
    if (!originalRef.current || reviewText === null) return;
    const s = selectionOffsets(originalRef.current);
    setSelection(s ? trimSpan(reviewText, s.start, s.end) : null);
  }, [reviewText]);

  function addManual(spans: { start: number; end: number }[], kind: ManualKind) {
    if (reviewText === null) return;
    const fresh = spans
      .filter((s) => s.end > s.start)
      .filter((s) => !manual.some((m) => overlaps(m, s)))
      .map((s) => ({ id: `m-${s.start}-${s.end}`, kind, ...s, text: reviewText.slice(s.start, s.end) }));
    if (fresh.length) setManual((prev) => [...prev, ...fresh]);
    window.getSelection()?.removeAllRanges();
    setSelection(null);
    setNotice(fresh.length ? `Added ${fresh.length} item${fresh.length > 1 ? "s" : ""} to remove.` : "That text is already being removed.");
  }

  function focusItem(id: string) {
    const el = document.getElementById(`hl-${id}`);
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
    setFlashId(null);
    requestAnimationFrame(() => setFlashId(id));
    setTimeout(() => setFlashId((cur) => (cur === id ? null : cur)), 2600);
  }

  const highlights: Highlight[] = [
    ...visibleFindings.map((f) => ({ id: f.id, start: f.start, end: f.end, kind: f.kind, needsCheck: f.needs_check, kept: keep.has(f.id) })),
    ...manual.map((m) => ({ id: m.id, start: m.start, end: m.end, kind: m.kind })),
  ];

  const chips: ChipItem[] = [
    ...visibleFindings.map((f) => ({
      start: f.start,
      id: f.id,
      kind: f.kind,
      label: kindStyle(f.kind).label,
      text: f.text,
      needsCheck: f.needs_check,
      remove: !keep.has(f.id),
      manual: false,
    })),
    ...manual.map((m) => ({
      start: m.start,
      id: m.id,
      kind: m.kind,
      label: kindStyle(m.kind).label,
      text: m.text,
      needsCheck: false,
      remove: true,
      manual: true,
    })),
  ].sort((a, b) => a.start - b.start);

  const legendKinds = [...new Set(highlights.map((h) => h.kind))];

  return (
    <div className="space-y-5">
      {error && <Banner tone="error" title="Something needs your attention" onClose={() => setError(null)}>{error}</Banner>}
      {notice && <Banner tone="success" onClose={() => setNotice(null)}>{notice}</Banner>}

      {reviewText === null ? (
        <Card>
          <div className="space-y-4">
            <TextArea
              id="input-text"
              label="Text to make safe"
              hint="Paste a patient note, letter or report. It stays on this computer."
              value={text}
              onChange={setText}
              rows={14}
              placeholder="Paste text here…"
            />
            {fileInfo && (
              <p className="flex items-center gap-2 text-slate-700 dark:text-slate-300">
                <FileText aria-hidden className="h-5 w-5" />
                <span>
                  <strong>{fileInfo.filename}</strong> ({formatBytes(fileInfo.size)}
                  {fileInfo.pages ? `, ${fileInfo.pages} page${fileInfo.pages > 1 ? "s" : ""}` : ""})
                </span>
              </p>
            )}
            {fileInfo?.warnings.map((w) => (
              <Banner key={w} tone="warning">
                {w}
              </Banner>
            ))}
            <FileDrop onFile={onFile} busy={busy} />
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="primary" size="lg" onClick={find} disabled={busy}>
                <Search aria-hidden className="h-5 w-5" />
                {busy ? "Working…" : "Find patient details"}
              </Button>
              {!text && (
                <Button variant="ghost" onClick={() => setText(EXAMPLE_NOTE)}>
                  <Sparkles aria-hidden className="h-5 w-5" />
                  Try an example
                </Button>
              )}
              {text && (
                <Button variant="ghost" onClick={startOver}>
                  <RotateCcw aria-hidden className="h-5 w-5" /> Start over
                </Button>
              )}
            </div>
            {!text && (
              <p className="text-slate-600 dark:text-slate-400">
                The example is made up. It shows the kinds of details Studio finds.
              </p>
            )}
          </div>
        </Card>
      ) : (
        <>
          <Card>
            <h2 ref={resultsRef} tabIndex={-1} className="text-xl font-semibold" aria-live="polite">
              {totalFound === 0 ? "No patient details found." : describeCounts(foundCounts)}
            </h2>
            {keep.size > 0 && (
              <p className="mt-1 text-slate-700 dark:text-slate-300">
                You chose to keep {keep.size}. {describeCounts(counts).replace("Found", "Removing")}
              </p>
            )}
            <fieldset className="mt-4">
              <legend className="font-medium">How should details be removed?</legend>
              <div className="mt-2 grid gap-3 md:grid-cols-2">
                {(
                  [
                    ["pseudonymize", "Replace with codes (you can restore later)", "Each detail becomes a code like [PATIENT_NAME_a2b6c3d4]. Use Restore names to put the real details back while Studio is open."],
                    ["mask", "Remove permanently", "Each detail becomes its type, like [PATIENT_NAME]. Nothing can be restored."],
                  ] as const
                ).map(([value, label, help]) => (
                  <label
                    key={value}
                    className={`flex cursor-pointer gap-3 rounded-lg border p-3 ${mode === value ? "border-teal-700 bg-teal-50 dark:border-teal-400 dark:bg-teal-950" : "border-slate-300 dark:border-slate-600"}`}
                  >
                    <input type="radio" name="mode" value={value} checked={mode === value} onChange={() => setMode(value)} className="mt-1 h-5 w-5" />
                    <span>
                      <span className="block font-medium">{label}</span>
                      <span className="block text-slate-600 dark:text-slate-400">{help}</span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="mt-5 flex flex-wrap gap-3">
              <Button variant="primary" size="lg" onClick={copy}>
                <ClipboardCopy aria-hidden className="h-5 w-5" /> Copy safe text
              </Button>
              <Button onClick={download}>
                <Download aria-hidden className="h-5 w-5" /> Download {fileInfo?.kind === "docx" ? "Word file" : "text file"}
              </Button>
              <Button variant="ghost" onClick={() => setReviewText(null)}>
                Edit the original
              </Button>
              <Button variant="ghost" onClick={startOver}>
                <RotateCcw aria-hidden className="h-5 w-5" /> Start over
              </Button>
            </div>
          </Card>

          {legendKinds.length > 0 && (
            <div aria-label="Colour key" role="group" className="flex flex-wrap items-center gap-2">
              <span className="font-medium">Key:</span>
              {legendKinds.map((k) => (
                <span key={k} className={`rounded px-2 py-0.5 text-sm font-semibold ${kindStyle(k).className}`}>
                  {kindStyle(k).label}
                </span>
              ))}
            </div>
          )}

          <div className="grid gap-5 lg:grid-cols-2">
            <div>
              <h3 className="mb-2 text-lg font-semibold">Original (only shown on this computer)</h3>
              <div onMouseUp={captureSelection} onKeyUp={captureSelection} role="presentation">
                <HighlightedText ref={originalRef} text={reviewText} highlights={highlights} label="Original text with patient details highlighted" flashId={flashId} />
              </div>
              {selection && (
                <div role="group" aria-label="Also remove the selected text" className="mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-teal-600 bg-teal-50 p-3 dark:bg-teal-950">
                  <span className="font-medium">
                    Also remove this: <span className="font-mono">“{reviewText.slice(selection.start, selection.end).slice(0, 40)}”</span> as
                  </span>
                  {MANUAL_KINDS.map(({ kind, label }) => (
                    <Button key={kind} onClick={() => addManual([selection], kind)}>
                      {label}
                    </Button>
                  ))}
                </div>
              )}
              <p className="mt-2 text-slate-600 dark:text-slate-400">
                Missed something? Select it in the original text, or type it below.
              </p>
              <form
                className="mt-2 flex flex-wrap items-end gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  const spans = findAll(reviewText, phrase.trim());
                  if (spans.length === 0) setError(`We couldn't find “${phrase.trim()}” in the text. Check the spelling and capital letters.`);
                  else addManual(spans, phraseKind);
                  setPhrase("");
                }}
              >
                <div>
                  <label htmlFor="add-phrase" className="block font-medium">
                    Add a word or phrase to remove
                  </label>
                  <input
                    id="add-phrase"
                    value={phrase}
                    onChange={(e) => setPhrase(e.target.value)}
                    className="mt-1 rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-600 dark:bg-slate-950"
                  />
                </div>
                <div>
                  <label htmlFor="add-kind" className="block font-medium">
                    Type
                  </label>
                  <select
                    id="add-kind"
                    value={phraseKind}
                    onChange={(e) => setPhraseKind(e.target.value as ManualKind)}
                    className="mt-1 rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-600 dark:bg-slate-950"
                  >
                    {MANUAL_KINDS.map(({ kind, label }) => (
                      <option key={kind} value={kind}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>
                <Button type="submit" disabled={!phrase.trim()}>
                  Also remove this
                </Button>
              </form>
            </div>
            <div>
              <h3 className="mb-2 text-lg font-semibold">Safe version (updates as you choose)</h3>
              <pre
                aria-live="polite"
                aria-label="Safe version of the text"
                data-testid="preview"
                // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
                tabIndex={0}
                className="doc-text max-h-[32rem] min-h-[12rem] overflow-auto rounded-lg border border-emerald-400 bg-emerald-50/40 p-4 font-mono text-base leading-8 dark:border-emerald-700 dark:bg-emerald-950/30"
              >
                {preview || "Preparing…"}
              </pre>
            </div>
          </div>

          <Card>
            <h3 className="mb-1 text-lg font-semibold">Review each detail</h3>
            <p className="mb-3 text-slate-600 dark:text-slate-400">
              Everything is removed unless you choose <strong>Keep</strong>. Click a detail to find it in the text. Items
              marked <strong>Please check</strong> are less certain.
            </p>
            <FindingList
              items={chips}
              onFocus={focusItem}
              onToggle={(id, remove) =>
                setKeep((prev) => {
                  const next = new Set(prev);
                  if (remove) next.delete(id);
                  else next.add(id);
                  return next;
                })
              }
              onDeleteManual={(id) => setManual((prev) => prev.filter((m) => m.id !== id))}
            />
          </Card>
        </>
      )}
    </div>
  );
}
