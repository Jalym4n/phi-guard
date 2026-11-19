/**
 * Each kind of patient detail has a colour AND a text label, so colour is never
 * the only signal (WCAG 1.4.1).  Highlight colours are light tints with dark
 * text in light mode and deep tints with light text in dark mode; every pair
 * keeps text contrast above 4.5:1.
 */
export interface KindStyle {
  label: string;
  plural: string;
  className: string; // background + text for highlights and chip dots
}

const STYLES: Record<string, KindStyle> = {
  PATIENT_NAME: { label: "Name", plural: "names", className: "bg-sky-100 text-sky-950 dark:bg-sky-900 dark:text-sky-50" },
  PERSON_NAME_NER: { label: "Possible name", plural: "possible names", className: "bg-sky-100 text-sky-950 dark:bg-sky-900 dark:text-sky-50" },
  DATE_OF_BIRTH: { label: "Date of birth", plural: "dates of birth", className: "bg-amber-100 text-amber-950 dark:bg-amber-900 dark:text-amber-50" },
  OHIP_NUMBER: { label: "Health card number", plural: "health card numbers", className: "bg-rose-100 text-rose-950 dark:bg-rose-900 dark:text-rose-50" },
  SIN: { label: "Social insurance number", plural: "social insurance numbers", className: "bg-red-100 text-red-950 dark:bg-red-900 dark:text-red-50" },
  CREDIT_CARD: { label: "Payment card", plural: "payment cards", className: "bg-orange-100 text-orange-950 dark:bg-orange-900 dark:text-orange-50" },
  EMAIL: { label: "Email address", plural: "email addresses", className: "bg-violet-100 text-violet-950 dark:bg-violet-900 dark:text-violet-50" },
  PHONE: { label: "Phone number", plural: "phone numbers", className: "bg-emerald-100 text-emerald-950 dark:bg-emerald-900 dark:text-emerald-50" },
  POSTAL_CODE: { label: "Postal code", plural: "postal codes", className: "bg-lime-100 text-lime-950 dark:bg-lime-900 dark:text-lime-50" },
  ADDRESS: { label: "Street address", plural: "street addresses", className: "bg-teal-100 text-teal-950 dark:bg-teal-900 dark:text-teal-50" },
  MRN: { label: "Medical record number", plural: "medical record numbers", className: "bg-fuchsia-100 text-fuchsia-950 dark:bg-fuchsia-900 dark:text-fuchsia-50" },
  IP_ADDRESS: { label: "Computer address (IP)", plural: "computer addresses (IP)", className: "bg-slate-200 text-slate-950 dark:bg-slate-700 dark:text-slate-50" },
  CUSTOM: { label: "Your word list", plural: "words from your list", className: "bg-indigo-100 text-indigo-950 dark:bg-indigo-900 dark:text-indigo-50" },
  ID_NUMBER: { label: "ID number", plural: "ID numbers", className: "bg-pink-100 text-pink-950 dark:bg-pink-900 dark:text-pink-50" },
  OTHER: { label: "Other", plural: "other details", className: "bg-stone-200 text-stone-950 dark:bg-stone-700 dark:text-stone-50" },
  UNKNOWN_TOKEN: { label: "Unknown code", plural: "unknown codes", className: "bg-yellow-100 text-yellow-950 dark:bg-yellow-900 dark:text-yellow-50" },
};

const FALLBACK: KindStyle = { label: "Detail", plural: "details", className: "bg-stone-200 text-stone-950 dark:bg-stone-700 dark:text-stone-50" };

export function kindStyle(kind: string): KindStyle {
  return STYLES[kind] ?? FALLBACK;
}

export const MANUAL_KINDS = [
  { kind: "PATIENT_NAME", label: "Name" },
  { kind: "ADDRESS", label: "Address" },
  { kind: "ID_NUMBER", label: "ID number" },
  { kind: "OTHER", label: "Other" },
] as const;

/** "Found 8 patient details: 2 names, 1 health card number, ..." */
export function describeCounts(counts: Record<string, number>): string {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  if (total === 0) return "No patient details found.";
  const parts = Object.entries(counts)
    .filter(([, n]) => n > 0)
    .map(([kind, n]) => {
      const s = kindStyle(kind);
      // Lower-case only the first letter so acronyms stay intact: "computer address (IP)".
      const singular = s.label.charAt(0).toLowerCase() + s.label.slice(1);
      return `${n} ${n === 1 ? singular : s.plural}`;
    });
  return `Found ${total} patient detail${total === 1 ? "" : "s"}: ${parts.join(", ")}.`;
}
