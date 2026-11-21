import { useEffect, useRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, XCircle, X } from "lucide-react";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-teal-700 text-white hover:bg-teal-800 disabled:bg-slate-400 dark:bg-teal-400 dark:text-slate-950 dark:hover:bg-teal-300 dark:disabled:bg-slate-600",
  secondary:
    "bg-white text-slate-900 border border-slate-300 hover:bg-slate-100 disabled:text-slate-400 dark:bg-slate-800 dark:text-slate-100 dark:border-slate-600 dark:hover:bg-slate-700",
  danger: "bg-red-700 text-white hover:bg-red-800 dark:bg-red-500 dark:text-slate-950 dark:hover:bg-red-400",
  ghost: "text-slate-700 hover:bg-slate-200 dark:text-slate-200 dark:hover:bg-slate-800",
};

export function Button({
  variant = "secondary",
  size = "md",
  className = "",
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "md" | "lg" }) {
  const sizing = size === "lg" ? "px-5 py-3 text-lg" : "px-4 py-2 text-base";
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:cursor-not-allowed ${sizing} ${VARIANTS[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section
      className={`rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900 ${className}`}
    >
      {children}
    </section>
  );
}

const BANNER = {
  info: { icon: Info, cls: "border-sky-300 bg-sky-50 text-sky-950 dark:border-sky-700 dark:bg-sky-950 dark:text-sky-50" },
  success: {
    icon: CheckCircle2,
    cls: "border-emerald-300 bg-emerald-50 text-emerald-950 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-50",
  },
  warning: {
    icon: AlertTriangle,
    cls: "border-amber-400 bg-amber-50 text-amber-950 dark:border-amber-600 dark:bg-amber-950 dark:text-amber-50",
  },
  error: { icon: XCircle, cls: "border-red-300 bg-red-50 text-red-950 dark:border-red-700 dark:bg-red-950 dark:text-red-50" },
} as const;

export function Banner({
  tone = "info",
  title,
  children,
  onClose,
  role,
}: {
  tone?: keyof typeof BANNER;
  title?: string;
  children?: ReactNode;
  onClose?: () => void;
  role?: "alert" | "status";
}) {
  const { icon: Icon, cls } = BANNER[tone];
  return (
    <div role={role ?? (tone === "error" ? "alert" : "status")} className={`flex gap-3 rounded-lg border p-4 ${cls}`}>
      <Icon aria-hidden className="mt-0.5 h-5 w-5 shrink-0" />
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={title ? "mt-1" : ""}>{children}</div>}
      </div>
      {onClose && (
        <button type="button" onClick={onClose} className="self-start rounded p-1 hover:bg-black/10" aria-label="Dismiss">
          <X aria-hidden className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  description,
  id,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  description?: string;
  id: string;
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-2">
      <div>
        <label htmlFor={id} className="font-medium">
          {label}
        </label>
        {description && (
          <p id={`${id}-desc`} className="text-slate-600 dark:text-slate-400">
            {description}
          </p>
        )}
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-describedby={description ? `${id}-desc` : undefined}
        onClick={() => onChange(!checked)}
        className={`relative mt-1 inline-flex h-7 w-12 shrink-0 items-center rounded-full border-2 transition-colors ${
          checked ? "border-teal-700 bg-teal-700 dark:border-teal-400 dark:bg-teal-400" : "border-slate-400 bg-slate-200 dark:bg-slate-700"
        }`}
      >
        <span className="sr-only">{checked ? "On" : "Off"}</span>
        <span
          aria-hidden
          className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform dark:bg-slate-900 ${checked ? "translate-x-5" : "translate-x-0.5"}`}
        />
      </button>
    </div>
  );
}

export function Dialog({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      if (typeof d.showModal === "function") d.showModal();
      else d.setAttribute("open", "");
    } else if (!open && d.open) {
      if (typeof d.close === "function") d.close();
      else d.removeAttribute("open");
    }
  }, [open]);
  return (
    <dialog
      ref={ref}
      aria-labelledby="dialog-title"
      onClose={onClose}
      onCancel={onClose}
      className="w-[min(36rem,92vw)] rounded-xl border border-slate-300 bg-white p-0 text-slate-900 shadow-xl dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
    >
      {open && (
        <div className="p-6">
          <div className="mb-4 flex items-start justify-between gap-4">
            <h2 id="dialog-title" className="text-xl font-semibold">
              {title}
            </h2>
            <button type="button" onClick={onClose} className="rounded p-1 hover:bg-slate-200 dark:hover:bg-slate-700" aria-label="Close">
              <X aria-hidden className="h-5 w-5" />
            </button>
          </div>
          {children}
        </div>
      )}
    </dialog>
  );
}

export function PageHeader({ title, intro }: { title: string; intro?: ReactNode }) {
  return (
    <header className="mb-6">
      <h1 tabIndex={-1} className="text-3xl font-bold tracking-tight focus:outline-none">{title}</h1>
      {intro && <p className="mt-2 max-w-3xl text-lg text-slate-700 dark:text-slate-300">{intro}</p>}
    </header>
  );
}

export function TextArea({
  id,
  label,
  value,
  onChange,
  placeholder,
  rows = 12,
  hint,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
  hint?: string;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block font-medium">
        {label}
      </label>
      {hint && (
        <p id={`${id}-hint`} className="mb-2 text-slate-600 dark:text-slate-400">
          {hint}
        </p>
      )}
      <textarea
        id={id}
        value={value}
        rows={rows}
        placeholder={placeholder}
        aria-describedby={hint ? `${id}-hint` : undefined}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
        className="w-full rounded-lg border border-slate-300 bg-white p-3 font-mono text-base text-slate-900 placeholder:text-slate-500 dark:border-slate-600 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-400"
      />
    </div>
  );
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} bytes`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
