import { CheckCircle2, OctagonX, AlertTriangle } from "lucide-react";
import type { Verdict } from "../lib/types";

const STYLE: Record<Verdict, { icon: typeof CheckCircle2; cls: string; bar: string; light: string }> = {
  allow: {
    icon: CheckCircle2,
    cls: "border-emerald-500 bg-emerald-50 text-emerald-950 dark:bg-emerald-950 dark:text-emerald-50",
    bar: "bg-emerald-600",
    light: "Green",
  },
  review: {
    icon: AlertTriangle,
    cls: "border-amber-500 bg-amber-50 text-amber-950 dark:bg-amber-950 dark:text-amber-50",
    bar: "bg-amber-500",
    light: "Amber",
  },
  block: {
    icon: OctagonX,
    cls: "border-red-600 bg-red-50 text-red-950 dark:bg-red-950 dark:text-red-50",
    bar: "bg-red-600",
    light: "Red",
  },
};

export function VerdictCard({ verdict, title, detail }: { verdict: Verdict; title: string; detail: string }) {
  const s = STYLE[verdict];
  const Icon = s.icon;
  return (
    <div role="status" data-verdict={verdict} className={`flex gap-4 rounded-xl border-2 p-5 ${s.cls}`}>
      <Icon aria-hidden className="h-10 w-10 shrink-0" />
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide">{s.light} light</p>
        <p className="text-2xl font-bold">{title}</p>
        <p className="mt-1 text-base">{detail}</p>
      </div>
    </div>
  );
}

export function RiskMeter({ score, verdict }: { score: number; verdict: Verdict }) {
  return (
    <div>
      <div className="mb-1 flex justify-between">
        <span id="risk-label" className="font-medium">
          Risk score
        </span>
        <span className="font-mono font-semibold">{score} / 100</span>
      </div>
      <div
        role="meter"
        aria-labelledby="risk-label"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={score}
        aria-valuetext={`${score} out of 100`}
        className="h-4 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"
      >
        <div className={`h-full ${STYLE[verdict].bar}`} style={{ width: `${Math.max(2, score)}%` }} />
      </div>
      <div className="mt-1 flex justify-between text-sm text-slate-600 dark:text-slate-400">
        <span>0 safe</span>
        <span>30 review</span>
        <span>70 do not use</span>
        <span>100</span>
      </div>
    </div>
  );
}
