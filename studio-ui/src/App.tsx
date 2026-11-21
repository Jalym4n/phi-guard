import { useCallback, useEffect, useRef, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { api, initToken } from "./lib/api";
import type { Mode, SessionInfo, Settings } from "./lib/types";
import { PrivacyBadge } from "./components/PrivacyBadge";
import { PAGES, Sidebar, type PageId } from "./components/Sidebar";
import { Banner, Button } from "./components/ui";
import { ActivityPage } from "./pages/ActivityPage";
import { CheckPage } from "./pages/CheckPage";
import { HelpPage } from "./pages/HelpPage";
import { RemovePage } from "./pages/RemovePage";
import { RestorePage } from "./pages/RestorePage";
import { SettingsPage } from "./pages/SettingsPage";

function applyAppearance(s: Pick<Settings, "theme" | "text_size">) {
  const root = document.documentElement;
  const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
  root.classList.toggle("dark", s.theme === "dark" || (s.theme === "system" && prefersDark));
  root.dataset.textSize = s.text_size;
}

function mmss(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function App() {
  const [token] = useState(() => initToken());
  const [page, setPage] = useState<PageId>("remove");
  const [settings, setSettings] = useState<Settings | null>(null);
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [clearedNotice, setClearedNotice] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const mainRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!token) return;
    api
      .settings()
      .then((r) => {
        setSettings(r.settings);
        applyAppearance(r.settings);
      })
      .catch((e: unknown) => setConnectionError(e instanceof Error ? e.message : String(e)));
  }, [token]);

  // Follow the operating system's light/dark setting when theme is "system".
  useEffect(() => {
    if (!settings || settings.theme !== "system" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyAppearance(settings);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [settings]);

  const pollSession = useCallback(() => {
    api
      .session()
      .then((s) => {
        setSession(s);
        setRemaining(s.seconds_remaining);
        if (s.cleared_for_inactivity) setClearedNotice(true);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!token) return;
    pollSession();
    const poll = setInterval(pollSession, 15000);
    const tick = setInterval(() => setRemaining((r) => (r === null ? r : Math.max(0, r - 1))), 1000);
    return () => {
      clearInterval(poll);
      clearInterval(tick);
    };
  }, [token, pollSession]);

  useEffect(() => {
    const label = PAGES.find((p) => p.id === page)?.label ?? "";
    document.title = `${label} · phi-guard Studio`;
  }, [page]);

  function navigate(p: PageId) {
    setPage(p);
    setTimeout(() => mainRef.current?.querySelector("h1")?.focus(), 0);
  }

  if (!token) {
    return (
      <main className="mx-auto mt-24 max-w-xl p-6">
        <h1 className="text-2xl font-bold">Please open Studio from its shortcut</h1>
        <p className="mt-3 text-lg">
          For your protection, this page only works when it is opened by phi-guard Studio itself. Close this tab and
          start Studio again from its desktop shortcut or with the <code>phi-guard-studio</code> command.
        </p>
      </main>
    );
  }

  const showCountdown = remaining !== null && remaining < 120 && (session?.codes_in_memory ?? 0) > 0;
  const mode: Mode = settings?.default_mode ?? "pseudonymize";

  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:p-3 focus:text-slate-900">
        Skip to main content
      </a>
      <header className="no-print flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-5 py-3 dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center gap-2">
          <ShieldCheck aria-hidden className="h-7 w-7 text-teal-700 dark:text-teal-400" />
          <span className="text-xl font-bold">phi-guard Studio</span>
        </div>
        <PrivacyBadge />
      </header>
      <div className="flex flex-1">
        <Sidebar current={page} onNavigate={navigate} />
        <main id="main" ref={mainRef} tabIndex={-1} className="min-w-0 flex-1 p-6 lg:p-8">
          <div className="mx-auto max-w-7xl space-y-4">
            {connectionError && <Banner tone="error" title="Studio couldn't load">{connectionError}</Banner>}
            {showCountdown && (
              <Banner tone="warning" title={`Codes will be cleared in ${mmss(remaining ?? 0)}`} role="status">
                For your protection, Studio forgets codes after a period of inactivity.{" "}
                <Button className="ml-2 mt-2" onClick={() => api.health().then(pollSession).catch(() => undefined)}>
                  Keep my codes
                </Button>
              </Banner>
            )}
            {clearedNotice && (
              <Banner tone="info" title="Codes were cleared because Studio was idle" onClose={() => setClearedNotice(false)}>
                Codes from earlier can no longer be restored. This protects patient details if the computer is left unattended.
              </Banner>
            )}
            <div hidden={page !== "remove"}>
              <RemovePage defaultMode={mode} />
            </div>
            <div hidden={page !== "check"}>
              <CheckPage />
            </div>
            <div hidden={page !== "restore"}>
              <RestorePage />
            </div>
            {page === "activity" && <ActivityPage />}
            {page === "settings" && (
              <SettingsPage
                onSaved={(s) => {
                  setSettings(s);
                  applyAppearance(s);
                }}
              />
            )}
            {page === "help" && <HelpPage />}
          </div>
        </main>
      </div>
    </div>
  );
}
