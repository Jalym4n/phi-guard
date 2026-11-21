/**
 * Talks to the local Studio server (same origin, http://127.0.0.1:PORT).
 *
 * The per-launch session token arrives in the URL fragment (#token=...), which
 * browsers never send to servers.  We read it once, remove it from the address
 * bar, and keep it in sessionStorage so a page refresh still works.  The token
 * is not patient data; patient text is never stored in browser storage.
 */
import type {
  AuditPage,
  BatchStatus,
  ExtractResult,
  InjectResult,
  KeyStatus,
  ManualSpan,
  Mode,
  RedactResult,
  RestoreResult,
  ScanResult,
  SessionInfo,
  Settings,
  SettingsResponse,
} from "./types";

const TOKEN_KEY = "phi-guard-session-token";
let token: string | null = null;

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function storage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function initToken(): string | null {
  const match = /[#&]token=([^&]+)/.exec(window.location.hash);
  if (match?.[1]) {
    token = decodeURIComponent(match[1]);
    try {
      storage()?.setItem(TOKEN_KEY, token);
    } catch {
      /* storage unavailable: the token still works until the tab is refreshed */
    }
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
  } else {
    try {
      token = storage()?.getItem(TOKEN_KEY) ?? null;
    } catch {
      token = null;
    }
  }
  return token;
}

export function setTokenForTests(value: string | null): void {
  token = value;
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (token) headers.set("X-PHI-Guard-Token", token);
  let res: Response;
  try {
    res = await fetch(path, { ...init, headers, credentials: "same-origin", cache: "no-store" });
  } catch {
    throw new ApiError("Studio isn't responding. Check that the Studio window is still open, then try again.", 0);
  }
  if (!res.ok) {
    let message = "Something went wrong. Please try again.";
    try {
      const body = (await res.json()) as { error?: string };
      if (body.error) message = body.error;
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(message, res.status);
  }
  return res;
}

async function json<T>(path: string, body?: unknown, method = body === undefined ? "GET" : "POST"): Promise<T> {
  const init: RequestInit = { method };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "Content-Type": "application/json" };
  }
  const res = await request(path, init);
  return (await res.json()) as T;
}

async function form<T>(path: string, data: FormData): Promise<T> {
  const res = await request(path, { method: "POST", body: data });
  return (await res.json()) as T;
}

async function blob(path: string, init: RequestInit = {}): Promise<Blob> {
  const res = await request(path, init);
  return res.blob();
}

export interface RedactOptions {
  mode: Mode;
  keep: { start: number; end: number }[];
  manual: Pick<ManualSpan, "start" | "end" | "kind">[];
}

export const api = {
  health: () => json<{ status: string; version: string; ner_available: boolean; key_backend: string }>("/api/health"),
  session: () => json<SessionInfo>("/api/session"),
  clearSession: () => json<{ ok: boolean }>("/api/session/clear", {}),
  scan: (text: string) => json<ScanResult>("/api/scan", { text }),
  redact: (text: string, options: RedactOptions, final = false) =>
    json<RedactResult>("/api/redact", { text, ...options, final }),
  redactDocx: (file: File, options: RedactOptions) => {
    const data = new FormData();
    data.append("file", file);
    data.append("options", JSON.stringify(options));
    return blob("/api/redact/docx", { method: "POST", body: data });
  },
  redactScan: (file: File, options: RedactOptions) => {
    const data = new FormData();
    data.append("file", file);
    data.append("options", JSON.stringify(options));
    return blob("/api/redact/scan", { method: "POST", body: data });
  },
  extract: (file: File) => {
    const data = new FormData();
    data.append("file", file);
    return form<ExtractResult>("/api/extract", data);
  },
  inject: (text: string) => json<InjectResult>("/api/inject", { text }),
  restore: (text: string) => json<RestoreResult>("/api/restore", { text }),
  outputScan: (text: string) => json<ScanResult>("/api/output-scan", { text }),
  startBatch: (files: { file: File; path: string }[], mode: Mode) => {
    const data = new FormData();
    for (const { file, path } of files) data.append("files", file, path);
    data.append("mode", mode);
    return form<{ id: string; total: number }>("/api/batch", data);
  },
  batchStatus: (id: string) => json<BatchStatus>(`/api/batch/${encodeURIComponent(id)}`),
  batchDownload: (id: string) => blob(`/api/batch/${encodeURIComponent(id)}/download`),
  audit: (params: Record<string, string>) => json<AuditPage>(`/api/audit?${new URLSearchParams(params).toString()}`),
  verifyAudit: () => json<{ ok: boolean; broken_line: number | null; entries: number | null }>("/api/audit/verify", {}),
  exportAudit: () => blob("/api/audit/export"),
  openLogFolder: () => json<{ opened: boolean; path: string }>("/api/audit/open-folder", {}),
  settings: () => json<SettingsResponse>("/api/settings"),
  saveSettings: (s: Settings) => json<SettingsResponse>("/api/settings", s, "PUT"),
  rotateKey: () => json<KeyStatus>("/api/key/rotate", {}),
  exportKey: (password: string) =>
    blob("/api/key/export", {
      method: "POST",
      body: JSON.stringify({ password }),
      headers: { "Content-Type": "application/json" },
    }),
  importKey: (file: File, password: string) => {
    const data = new FormData();
    data.append("file", file);
    data.append("password", password);
    return form<KeyStatus>("/api/key/import", data);
  },
};

/** Save a Blob as a file the user downloads (the only way Studio writes patient-derived data to disk). */
export function saveBlob(data: Blob, filename: string): void {
  const url = URL.createObjectURL(data);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong. Please try again.";
}
