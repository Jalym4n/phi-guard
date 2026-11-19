export type Mode = "pseudonymize" | "mask";
export type ManualKind = "PATIENT_NAME" | "ADDRESS" | "ID_NUMBER" | "OTHER";
export type Verdict = "allow" | "review" | "block";

/** All offsets are UTF-16 code units, the same units JavaScript strings use. */
export interface Finding {
  id: string;
  kind: string;
  label: string;
  start: number;
  end: number;
  text: string;
  confidence: number;
  needs_check: boolean;
  source: string;
}

export interface ManualSpan {
  id: string;
  kind: ManualKind;
  start: number;
  end: number;
  text: string;
}

export interface SummaryItem {
  kind: string;
  label: string;
  count: number;
}

export interface ScanResult {
  findings: Finding[];
  summary: SummaryItem[];
}

export interface RedactResult {
  text: string;
  summary: SummaryItem[];
  removed: number;
  kept: number;
}

export interface ExtractResult {
  text: string;
  kind: "txt" | "docx" | "pdf";
  pages: number | null;
  warnings: string[];
  filename: string;
  size: number;
}

export interface InjectFinding {
  rule: string;
  source: string;
  explanation: string;
  start: number;
  end: number;
  match: string;
}

export interface InjectResult {
  score: number;
  verdict: Verdict;
  title: string;
  detail: string;
  findings: InjectFinding[];
  hidden_characters: number;
  cleaned_text: string;
}

export interface RestoreResult {
  text: string;
  restored: number;
  codes_found: number;
  not_available: string[];
}

export interface SessionInfo {
  idle_timeout_seconds: number;
  seconds_remaining: number;
  codes_in_memory: number;
  cleared_for_inactivity: boolean;
}

export interface BatchItem {
  name: string;
  status: "done" | "skipped" | "error";
  reason: string;
  counts: Record<string, number>;
  verdict: string;
  score: number;
  output_name: string;
}

export interface BatchStatus {
  id: string;
  status: "running" | "done" | "error";
  total: number;
  processed: number;
  items: BatchItem[];
}

export interface AuditEntry {
  seq: number;
  ts: string;
  event: string;
  source?: string;
  counts?: Record<string, number>;
  verdict?: string | null;
  verdicts?: string[];
  [key: string]: unknown;
}

export interface AuditPage {
  entries: AuditEntry[];
  total: number;
  page: number;
  page_size: number;
  actions: string[];
}

export interface Settings {
  enabled_kinds: string[];
  always_remove: string[];
  never_remove: string[];
  default_mode: Mode;
  text_size: "normal" | "large" | "larger";
  theme: "system" | "light" | "dark";
  ner_enabled: boolean;
  idle_timeout_minutes: number;
  max_upload_mb: number;
  batch_max_files: number;
  batch_max_mb: number;
}

export interface KeyStatus {
  exists: boolean;
  backend: "keychain" | "file";
  location: string;
  fingerprint: string | null;
}

export interface SettingsResponse {
  settings: Settings;
  detectors: { kind: string; label: string; example: string }[];
  ner_available: boolean;
  audit_path: string;
  key: KeyStatus;
}
