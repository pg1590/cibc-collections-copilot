import type { DisputeType, HardshipReason, Outcomes, Reached, RepresentativeKind } from "./call-types";

export const REACHED_LABEL: Record<Reached, string> = {
  customer: "Customer",
  third_party: "Someone else",
  no_answer: "No answer",
  voicemail: "Voicemail",
};

export const HARDSHIP_REASON_LABEL: Record<HardshipReason, string> = {
  job_loss: "Job loss",
  reduced_income: "Reduced income",
  illness: "Illness or injury",
  separation: "Separation or divorce",
  disaster: "Disaster or emergency",
  expense_increase: "Expenses went up",
  other: "Other",
};

export const DISPUTE_TYPE_LABEL: Record<DisputeType, string> = {
  fee: "A fee",
  transaction: "A transaction",
  payment_not_applied: "Payment not applied",
  fraud: "Fraud",
  other: "Other",
};

export const REPRESENTATIVE_LABEL: Record<RepresentativeKind, string> = {
  lawyer: "Lawyer",
  credit_counsellor: "Credit counsellor",
  trustee: "Insolvency trustee",
  other: "Other",
};

const FIELD_LABEL: Record<string, string> = {
  reached: "Who answered",
  identity_verified: "Identity verified",
  recording_notice: "Recording notice given",
  "hardship.stated": "Hardship stated",
  "hardship.reason": "Hardship reason",
  hardship: "Hardship",
  cannot_afford: "Cannot afford a payment",
  "dispute.raised": "Dispute raised",
  "dispute.type": "Dispute about",
  dispute: "Dispute",
  complaint: "Complaint",
  cease_request: "Asked us to stop contact",
  "representative.stated": "Has a representative",
  "representative.kind": "Representative",
  representative: "Representative",
  vulnerable_disclosed: "Vulnerability disclosed",
  programme: "Hardship programme",
  promise: "Promise to pay",
  callback: "Callback",
  "income.monthly_income": "Monthly income (stated)",
  "income.monthly_expenses": "Monthly expenses (stated)",
  income: "Income and expenses",
};

export function fieldLabel(path: string): string {
  if (FIELD_LABEL[path]) return FIELD_LABEL[path];
  const text = path.replace(/[._]/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const money = new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" });

export function formatMoney(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? money.format(value) : "—";
}

/** Human-readable form of a proposed outcome value. */
export function valueLabel(path: string, value: unknown): string {
  if (path === "callback" && (value === null || value === undefined)) return "Pick a date and time";
  if (value === null || value === undefined) return "Not set";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string") {
    const maps: Record<string, Record<string, string>> = {
      "hardship.reason": HARDSHIP_REASON_LABEL,
      "dispute.type": DISPUTE_TYPE_LABEL,
      "representative.kind": REPRESENTATIVE_LABEL,
      reached: REACHED_LABEL,
    };
    return maps[path]?.[value] ?? value.replace(/_/g, " ");
  }
  if (typeof value === "number") return path.startsWith("income") ? formatMoney(value) : String(value);
  if (typeof value === "object") {
    const v = value as Record<string, unknown>;
    if (path === "promise" && typeof v.amount === "number") return v.date ? `${formatMoney(v.amount)} on ${String(v.date)}` : `${formatMoney(v.amount)}, date not given`;
    if (path === "dispute") return v.raised === false ? "No" : v.type ? `Yes: ${DISPUTE_TYPE_LABEL[v.type as DisputeType] ?? String(v.type)}` : "Yes";
    if (path === "representative") return v.stated === false ? "No" : v.kind ? REPRESENTATIVE_LABEL[v.kind as RepresentativeKind] ?? String(v.kind) : "Yes";
    if (path === "hardship") return v.stated === false ? "No" : v.reason ? HARDSHIP_REASON_LABEL[v.reason as HardshipReason] ?? String(v.reason) : "Yes";
    if (path === "callback") return `${String(v.date ?? "?")} at ${String(v.time ?? "?")}`;
    return Object.entries(v)
      .map(([k, x]) => `${k.replace(/_/g, " ")}: ${String(x)}`)
      .join(", ");
  }
  return String(value);
}

/**
 * Returns a copy of `outcomes` with the dotted `path` set to `value`. Setting a detail
 * (hardship reason, dispute type, representative kind) also marks its parent flag as true,
 * since a reason without the flag would be contradictory.
 */
export function setOutcome(outcomes: Outcomes, path: string, value: unknown): Outcomes {
  const parts = path.split(".");
  const next = structuredClone(outcomes) as unknown as Record<string, unknown>;
  let cursor = next;
  for (const part of parts.slice(0, -1)) {
    const child = cursor[part];
    if (!child || typeof child !== "object") cursor[part] = {};
    cursor = cursor[part] as Record<string, unknown>;
  }
  cursor[parts[parts.length - 1]] = value;
  const result = next as unknown as Outcomes;
  if (value !== null && value !== false) {
    if (path === "hardship.reason") result.hardship.stated = true;
    if (path === "dispute.type") result.dispute.raised = true;
    if (path === "representative.kind") result.representative.stated = true;
  }
  return result;
}

/** Applies an accepted extract proposal. Object values are merged into the existing group. */
export function applyProposal(outcomes: Outcomes, path: string, value: unknown): Outcomes {
  const current = getOutcome(outcomes, path);
  if (value && typeof value === "object" && current && typeof current === "object" && !Array.isArray(value)) {
    return setOutcome(outcomes, path, { ...(current as object), ...(value as object) });
  }
  return setOutcome(outcomes, path, value);
}

/** JSON with sorted keys, so outcomes from the server and the UI compare equal regardless of key order. */
export function canonical(value: unknown): string {
  return JSON.stringify(value, (_key, v: unknown) =>
    v && typeof v === "object" && !Array.isArray(v)
      ? Object.fromEntries(Object.entries(v as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)))
      : v,
  );
}

export function getOutcome(outcomes: Outcomes, path: string): unknown {
  return path.split(".").reduce<unknown>((acc, part) => (acc && typeof acc === "object" ? (acc as Record<string, unknown>)[part] : undefined), outcomes);
}
