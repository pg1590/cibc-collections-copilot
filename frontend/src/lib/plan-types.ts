import type { Brief, ReviewItem } from "./types";

export type StepStatus = "stop" | "action" | "caution" | "wait" | "clear";

export interface PlanStep {
  order: number;
  key: string;
  status: StepStatus;
  title: string;
  detail: string;
  policy: string[];
  evidence: string[];
}

export interface ContactWindow {
  available: boolean;
  date?: string;
  day?: string;
  from_local?: string;
  until_local?: string;
  time_zone: string;
  time_zone_known?: boolean;
  attempts_last_7d: number;
  cap_7d?: number;
  skipped?: { date: string; reason: string }[];
  at_utc?: string;
}

export interface Programme {
  program_id: string;
  version: string;
  name: string;
  description: string;
  approver: string;
  status: "likely_eligible" | "check" | "not_eligible";
  reasons: string[];
  missing_inputs: string[];
  source: string;
}

export interface ActionPlan {
  as_of: string;
  snapshot_date: string;
  case_id: string;
  next_action: string;
  steps: PlanStep[];
  contact_window: ContactWindow | null;
  programmes: Programme[];
  payday_estimate: string | null;
  note: string;
  other_open_cases?: string[];
}

export type BriefWithPlan = Brief & { action_plan?: ActionPlan | null; next_action?: string | null };
export type ReviewWithPlan = ReviewItem & { action_plan?: ActionPlan | null; next_action?: string | null };

export type QueueTier = "stop_now" | "promise_due" | "hardship_no_plan" | "near_write_off" | "promise_overdue" | "standard" | "on_hold";

export interface QueueItem {
  position: number;
  case_id: string;
  customer_id: string;
  name: string;
  product: string;
  dpd: number | null;
  overdue_cad: number | null;
  tier: QueueTier;
  tier_label: string;
  reason: string;
  next_contact: Pick<ContactWindow, "available" | "date" | "day" | "from_local" | "until_local" | "time_zone" | "attempts_last_7d" | "at_utc"> | null;
  flags: string[];
}

export interface QueueResponse {
  agent_id: string;
  as_of: string;
  total: number;
  items: QueueItem[];
  tiers: { key: QueueTier; label: string; rule: string; count: number }[];
  ordering?: string;
  agents?: { agent_id: string; open_cases: number }[];
}

export interface PortfolioCheck {
  id: string;
  title: string;
  value: number;
  unit: string;
  severity: "high" | "medium";
  definition: string;
  action: string;
  policy: string;
  sql: string;
}

export interface PortfolioChecks {
  snapshot_date: string;
  items: PortfolioCheck[];
}
