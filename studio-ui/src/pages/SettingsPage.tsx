import { useEffect, useRef, useState } from "react";
import { Download, FolderOpen, KeyRound, Save, Upload } from "lucide-react";
import { api, errorMessage, saveBlob } from "../lib/api";
import type { Settings, SettingsResponse } from "../lib/types";
import { Banner, Button, Card, Dialog, PageHeader, Toggle } from "../components/ui";

function terms(text: string): string[] {
  return text.split(/\r?\n/).map((t) => t.trim()).filter(Boolean);
}

function WordList({ id, label, help, value, onChange }: { id: string; label: string; help: string; value: string; onChange: (v: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <div>
      <label htmlFor={id} className="block text-lg font-semibold">{label}</label>
      <p id={`${id}-help`} className="mb-2 text-slate-600 dark:text-slate-400">{help}</p>
      <textarea
        id={id}
        aria-describedby={`${id}-help`}
        value={value}
        rows={6}
        onChange={(e) => onChange(e.target.value)}
        placeholder="One word or phrase per line"
        className="w-full rounded-lg border border-slate-300 bg-white p-3 font-mono dark:border-slate-600 dark:bg-slate-950"
      />
      <div className="mt-2 flex gap-2">
        <Button onClick={() => input.current?.click()}>
          <Upload aria-hidden className="h-4 w-4" /> Import .txt
        </Button>
        <Button onClick={() => saveBlob(new Blob([terms(value).join("\n") + "\n"], { type: "text/plain" }), `${id}.txt`)}>
          <Download aria-hidden className="h-4 w-4" /> Export .txt
        </Button>
        <input
          ref={input}
          type="file"
          accept=".txt,text/plain"
          className="sr-only"
          tabIndex={-1}
          aria-label={`Import ${label}`}
          onChange={async (e) => {
            const f = e.target.files?.[0];
            if (f) onChange([...terms(value), ...terms(await f.text())].join("\n"));
            e.target.value = "";
          }}
        />
      </div>
    </div>
  );
}

export function SettingsPage({ onSaved }: { onSaved: (s: Settings) => void }) {
  const [data, setData] = useState<SettingsResponse | null>(null);
  const [draft, setDraft] = useState<Settings | null>(null);
  const [always, setAlways] = useState("");
  const [never, setNever] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [dialog, setDialog] = useState<null | "rotate" | "export" | "import">(null);
  const [password, setPassword] = useState("");
  const [keyFile, setKeyFile] = useState<File | null>(null);

  useEffect(() => {
    api
      .settings()
      .then((r) => {
        setData(r);
        setDraft(r.settings);
        setAlways(r.settings.always_remove.join("\n"));
        setNever(r.settings.never_remove.join("\n"));
      })
      .catch((e: unknown) => setError(errorMessage(e)));
  }, []);

  if (!data || !draft) return <PageHeader title="Settings" intro="Loading…" />;
  const loaded = data;
  const current = draft;

  const update = (patch: Partial<Settings>) => setDraft({ ...current, ...patch });

  async function save(next: Settings = { ...current, always_remove: terms(always), never_remove: terms(never) }) {
    setError(null);
    try {
      const r = await api.saveSettings(next);
      setData(r);
      setDraft(r.settings);
      setAlways(r.settings.always_remove.join("\n"));
      setNever(r.settings.never_remove.join("\n"));
      onSaved(r.settings);
      setNotice("Settings saved.");
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function keyAction() {
    setError(null);
    try {
      if (dialog === "rotate") {
        const key = await api.rotateKey();
        setData({ ...loaded, key });
        setNotice("A new protection key was created. Codes made before now can no longer be restored.");
      } else if (dialog === "export") {
        saveBlob(await api.exportKey(password), "phi-guard-key-backup.json");
        setNotice("Key backup saved. Keep the file and its password in separate, safe places.");
      } else if (dialog === "import" && keyFile) {
        const key = await api.importKey(keyFile, password);
        setData({ ...loaded, key });
        setNotice("Protection key imported.");
      }
      setDialog(null);
      setPassword("");
      setKeyFile(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  const choice = (name: string, value: string, current: string, label: string, onPick: () => void) => (
    <label key={value} className="flex items-center gap-2">
      <input type="radio" name={name} value={value} checked={current === value} onChange={onPick} className="h-5 w-5" />
      {label}
    </label>
  );

  return (
    <div className="space-y-5">
      <PageHeader title="Settings" intro="Choose what Studio looks for and how it looks. Settings are saved on this computer." />
      {error && <Banner tone="error" onClose={() => setError(null)}>{error}</Banner>}
      {notice && <Banner tone="success" onClose={() => setNotice(null)}>{notice}</Banner>}

      <Card>
        <h2 className="mb-2 text-xl font-semibold">Which details to look for</h2>
        <div className="divide-y divide-slate-200 dark:divide-slate-700">
          {data.detectors.map((d) => (
            <Toggle
              key={d.kind}
              id={`kind-${d.kind}`}
              label={d.label}
              description={d.example}
              checked={draft.enabled_kinds.includes(d.kind)}
              onChange={(on) =>
                update({ enabled_kinds: on ? [...draft.enabled_kinds, d.kind] : draft.enabled_kinds.filter((k) => k !== d.kind) })
              }
            />
          ))}
          {data.ner_available && (
            <Toggle
              id="ner"
              label="Find names without a label (AI-based, slower)"
              description="Uses a language model on this computer to find names that don't follow “Patient:” or “Mrs.”. It may also flag some drug or place names, so check its results."
              checked={draft.ner_enabled}
              onChange={(v) => update({ ner_enabled: v })}
            />
          )}
        </div>
      </Card>

      <Card>
        <div className="grid gap-6 lg:grid-cols-2">
          <WordList
            id="always-remove"
            label="Always remove these words"
            help="For example staff names, your clinic's name, or rare surnames. Matches whole words, ignoring capitals."
            value={always}
            onChange={setAlways}
          />
          <WordList
            id="never-remove"
            label="Never remove these words"
            help="For example drug names that look like names, or the clinic's own public phone number."
            value={never}
            onChange={setNever}
          />
        </div>
      </Card>

      <Card>
        <h2 className="mb-3 text-xl font-semibold">Appearance</h2>
        <fieldset className="mb-4">
          <legend className="font-medium">Text size</legend>
          <div className="mt-2 flex flex-wrap gap-5">
            {choice("text-size", "normal", draft.text_size, "Normal", () => update({ text_size: "normal" }))}
            {choice("text-size", "large", draft.text_size, "Large", () => update({ text_size: "large" }))}
            {choice("text-size", "larger", draft.text_size, "Larger", () => update({ text_size: "larger" }))}
          </div>
        </fieldset>
        <fieldset>
          <legend className="font-medium">Theme</legend>
          <div className="mt-2 flex flex-wrap gap-5">
            {choice("theme", "system", draft.theme, "Same as my computer", () => update({ theme: "system" }))}
            {choice("theme", "light", draft.theme, "Light", () => update({ theme: "light" }))}
            {choice("theme", "dark", draft.theme, "Dark", () => update({ theme: "dark" }))}
          </div>
        </fieldset>
      </Card>

      <Card>
        <h2 className="mb-3 text-xl font-semibold">Privacy and limits</h2>
        <div className="flex flex-wrap gap-6">
          <div>
            <label htmlFor="idle" className="block font-medium">Clear codes after this many idle minutes</label>
            <input id="idle" type="number" min={1} max={480} value={draft.idle_timeout_minutes} onChange={(e) => update({ idle_timeout_minutes: Number(e.target.value) })} className="mt-1 w-28 rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-600 dark:bg-slate-950" />
          </div>
          <div>
            <label htmlFor="max-upload" className="block font-medium">Largest file (MB)</label>
            <input id="max-upload" type="number" min={1} max={100} value={draft.max_upload_mb} onChange={(e) => update({ max_upload_mb: Number(e.target.value) })} className="mt-1 w-28 rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-600 dark:bg-slate-950" />
          </div>
          <div>
            <label htmlFor="batch-files" className="block font-medium">Files per batch</label>
            <input id="batch-files" type="number" min={1} max={1000} value={draft.batch_max_files} onChange={(e) => update({ batch_max_files: Number(e.target.value) })} className="mt-1 w-28 rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-600 dark:bg-slate-950" />
          </div>
          <div>
            <label htmlFor="batch-mb" className="block font-medium">Batch size (MB)</label>
            <input id="batch-mb" type="number" min={1} max={500} value={draft.batch_max_mb} onChange={(e) => update({ batch_max_mb: Number(e.target.value) })} className="mt-1 w-28 rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-600 dark:bg-slate-950" />
          </div>
        </div>
      </Card>

      <div className="sticky bottom-0 z-10 -mx-1 border-t border-slate-200 bg-slate-50/95 px-1 py-3 dark:border-slate-800 dark:bg-slate-950/95">
        <Button variant="primary" size="lg" onClick={() => void save()}>
          <Save aria-hidden className="h-5 w-5" /> Save settings
        </Button>
      </div>

      <Card>
        <h2 className="mb-2 text-xl font-semibold">Protection key</h2>
        <p className="text-slate-700 dark:text-slate-300">
          The protection key turns details into codes. Without it, nobody can work out what a code stands for.
        </p>
        <dl className="mt-3 grid gap-x-6 gap-y-1 sm:grid-cols-[max-content_1fr]">
          <dt className="font-medium">Status</dt>
          <dd>{data.key.exists ? "A key is set up" : "No key yet"}</dd>
          <dt className="font-medium">Stored in</dt>
          <dd>
            {data.key.backend === "keychain" ? "Your computer's secure keychain" : "A protected file (less secure than the system keychain)"}
            <span className="block break-all text-slate-600 dark:text-slate-400">{data.key.location}</span>
          </dd>
          <dt className="font-medium">Key fingerprint</dt>
          <dd className="font-mono">{data.key.fingerprint ?? "–"}</dd>
        </dl>
        <div className="mt-4 flex flex-wrap gap-3">
          <Button onClick={() => setDialog("rotate")}>
            <KeyRound aria-hidden className="h-5 w-5" /> Create new key
          </Button>
          <Button onClick={() => setDialog("export")}>
            <Download aria-hidden className="h-5 w-5" /> Export key
          </Button>
          <Button onClick={() => setDialog("import")}>
            <Upload aria-hidden className="h-5 w-5" /> Import key
          </Button>
        </div>
      </Card>

      <Card>
        <h2 className="mb-2 text-xl font-semibold">Activity log location</h2>
        <p className="break-all font-mono">{data.audit_path}</p>
        <Button className="mt-3" onClick={() => void api.openLogFolder().then((r) => !r.opened && setError(`Open this folder yourself: ${r.path}`))}>
          <FolderOpen aria-hidden className="h-5 w-5" /> Open folder
        </Button>
      </Card>

      <Dialog
        open={dialog !== null}
        onClose={() => {
          setDialog(null);
          setPassword("");
        }}
        title={dialog === "rotate" ? "Create a new protection key?" : dialog === "export" ? "Export the protection key" : "Import a protection key"}
      >
        <div className="space-y-4">
          {dialog === "rotate" && (
            <Banner tone="warning" title="Codes made before now can't be restored.">
              Any AI answers that still contain old codes will stay coded. Export the current key first if you might need them.
            </Banner>
          )}
          {dialog === "export" && (
            <Banner tone="warning" title="Anyone with this file and its password can decode your codes.">
              Choose a strong password (at least 10 characters). Store the file and password separately.
            </Banner>
          )}
          {dialog === "import" && (
            <>
              <Banner tone="warning">Importing replaces the current key. Codes made with the current key can no longer be restored.</Banner>
              <div>
                <label htmlFor="key-file" className="block font-medium">Key backup file</label>
                <input id="key-file" type="file" accept=".json,application/json" onChange={(e) => setKeyFile(e.target.files?.[0] ?? null)} className="mt-1" />
              </div>
            </>
          )}
          {(dialog === "export" || dialog === "import") && (
            <div>
              <label htmlFor="key-password" className="block font-medium">Password</label>
              <input id="key-password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-600 dark:bg-slate-950" />
            </div>
          )}
          {error && <Banner tone="error">{error}</Banner>}
          <div className="flex justify-end gap-3">
            <Button onClick={() => setDialog(null)}>Cancel</Button>
            <Button
              variant={dialog === "rotate" ? "danger" : "primary"}
              disabled={(dialog === "export" && password.length < 10) || (dialog === "import" && (!keyFile || !password))}
              onClick={() => void keyAction()}
            >
              {dialog === "rotate" ? "Create new key" : dialog === "export" ? "Export" : "Import"}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
