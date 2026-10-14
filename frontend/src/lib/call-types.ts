import type { ActionPlan } from "./plan-types";

/** Live Call Mode contract: POST /api/call/session, /api/call/extract, /api/call/submit. */

export type Reached = "customer" | "third_party" | "no_answer" | "voicemail";
export type HardshipReason = "job_loss" | "reduced_income" | "illness" | "separation" | "disaster" | "expense_increase" | "other";
export type DisputeType = "fee" | "transaction" | "payment_not_applied" | "fraud" | "other";
export type RepresentativeKind = "lawyer" | "credit_counsellor" | "trustee" | "other";

export interface Outcomes {
  reached: Reached | null;
  identity_verified: boolean;
  recording_notice: boolean;
  hardship: { stated: boolean; reason: HardshipReason | null };
  cannot_afford: boolean;
  dispute: { raised: boolean; type: DisputeType | null };
  complaint: boolean;
  cease_request: boolean;
  representative: { stated: boolean; kind: RepresentativeKind | null };
  vulnerable_disclosed: boolean;
  /** program_id chosen from the calculator options */
  programme: string | null;
  /** date is YYYY-MM-DD */
  promise: { amount: number; date: string } | null;
  /** customer-local date and HH:MM */
  callback: { date: string; time: string } | null;
  /** customer-stated, not verified */
  income: { monthly_income: number | null; monthly_expenses: number | null };
}

export const EMPTY_OUTCOMES: Outcomes = {
  reached: null,
  identity_verified: false,
  recording_notice: false,
  hardship: { stated: false, reason: null },
  cannot_afford: false,
  dispute: { raised: false, type: null },
  complaint: false,
  cease_request: false,
  representative: { stated: false, kind: null },
  vulnerable_disclosed: false,
  programme: null,
  promise: null,
  callback: null,
  income: { monthly_income: null, monthly_expenses: null },
};

export type CheckStatus = "ok" | "warn" | "block";

export interface Check {
  key: string;
  status: CheckStatus;
  message: string;
  policy: string[];
}

export type CalcStatus = "likely_eligible" | "check" | "not_eligible";

export interface CalcOption {
  program_id: string;
  version: string;
  name: string;
  status: CalcStatus;
  approver: string;
  months: number | null;
  payment_now: number | null;
  payment_during: number | null;
  payment_after: number | null;
  monthly_saving: number | null;
  deferred_amount: number | null;
  interest_saving: number | null;
  one_time_amount: number | null;
  note: string;
  reasons: string[];
}

export interface ScriptItem {
  key: string;
  text: string;
  required: boolean;
  done: boolean;
  policy: string[];
}

export type CallStage = "blocked" | "pre_call" | "verification" | "conversation" | "wrap_up";

export interface CallCustomer {
  customer_id: string;
  name: string;
  preferred_language: string;
  time_zone: string;
  /** display string such as "Mon 28 Sep 07:00"; null when no call is allowed */
  local_time_now: string | null;
  /** explains that the call time is simulated after the data snapshot */
  call_time_note?: string | null;
  product: string;
  dpd: number;
  overdue_cad: number;
  case_id: string;
}

export interface Affordability {
  monthly_income: number | null;
  monthly_obligations: number | null;
  housing: number | null;
  disposable: number | null;
  source: string;
  verified: boolean;
  promise_share_of_disposable: number | null;
}

export interface FollowUp {
  type: string;
  when: string;
  reason: string;
}

export interface WrapUp {
  note: string;
  outcome_codes: string[];
  follow_ups: FollowUp[];
  ready_to_submit: boolean;
  blocking: string[];
}

export interface CallSession {
  customer: CallCustomer;
  stage: CallStage;
  /** false until reached=customer and identity_verified */
  can_discuss_debt: boolean;
  script: ScriptItem[];
  plan: ActionPlan;
  checks: Check[];
  calculator: {
    account: {
      product: string;
      balance: number | null;
      regular_payment: number | null;
      apr: number | null;
      remaining_term_months: number | null;
      source: string;
    };
    options: CalcOption[];
  };
  affordability: Affordability;
  wrap_up: WrapUp;
  /** the server-normalised outcomes the session was computed from */
  outcomes?: Outcomes;
}

export interface ExtractProposal {
  /** dotted Outcomes path, e.g. "hardship.reason" or "promise" */
  field: string;
  value: unknown;
  /** verbatim words from the note */
  quote: string;
  source: "gemini" | "rules";
}

export interface ExtractResponse {
  proposals: ExtractProposal[];
  provider: "gemini" | "rules";
  message?: string | null;
}

export interface SubmitResponse {
  brief_id: string;
  status: "pending";
}
