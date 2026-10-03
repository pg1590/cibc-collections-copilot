// Response shapes from docs/api-contract.md (API v1). Arrays whose item
// fields the contract does not fix are typed as generic records and rendered
// column-by-column from whatever the backend actually returns.

export type Role = "analyst" | "agent" | "supervisor";
export type ApiRecord = Record<string, unknown>;

export interface User {
  username: string;
  role: Role;
}

export interface Health {
  status: string;
  dataset_ready: boolean;
  snapshot_date: string | null;
  runtime_mode: string;
}

export interface LoginResponse {
  token: string;
  user: User;
}

export interface Overview {
  customers: number;
  open_cases: number;
  overdue_cad: number;
  identity: { matched: number; review: number; unmatched: number };
  quality_issues: number;
  pending_reviews: number;
}

export interface CustomerListItem {
  customer_id: string;
  name: string;
  province: string;
  open_cases: number;
  total_overdue: number;
  max_dpd: number;
  identity_confidence: number | string | null;
}

export interface CustomerList {
  items: CustomerListItem[];
  total: number;
}

export interface CustomerDetail {
  customer: {
    customer_id: string;
    name: string;
    province: string;
    preferred_language: string;
    identity_confidence: number | string | null;
  };
  accounts: ApiRecord[];
  cases: ApiRecord[];
  identity: ApiRecord[];
  notes: ApiRecord[];
  features: ApiRecord;
  snapshot_date: string;
}

export interface AskResponse {
  answer: string;
  sql_or_sources: string;
  refused: boolean;
  reason: string | null;
  rows: ApiRecord[];
  sources: unknown[];
  execution_ms: number;
  snapshot_date: string;
}

export interface Signal {
  name: string;
  value: unknown;
  evidence: unknown;
}

export interface Brief {
  brief_id: string;
  customer_id: string;
  summary: string;
  signals: Signal[];
  recommendation: string;
  policy_sources: unknown[];
  draft: string;
  status: string;
  model: { name: string; version: string };
  features: ApiRecord;
}

export type Decision = "approve" | "reject" | "edit";

export interface ReviewItem {
  brief_id: string;
  customer_id: string;
  summary: string;
  recommendation: string;
  draft: string;
  status: string;
  created_at: string;
  decision: Decision | null;
  reason: string | null;
  reviewer: string | null;
}

export interface AuditEvent {
  event_id: string;
  at: string;
  actor: string;
  action: string;
  resource: string;
  details: unknown;
}

export interface QualityCheck {
  check: string;
  table: string;
  failed_rows: number;
  total_rows: number;
  severity: string;
}

export interface QualityReport {
  snapshot_date: string;
  raw_counts: Record<string, number>;
  curated_counts: Record<string, number>;
  checks: QualityCheck[];
  identity: ApiRecord;
  built_at: string;
}

export interface FeatureRegistry {
  version: string;
  definitions: ApiRecord[];
  parity: { checked: number; mismatches: number };
  model: ApiRecord;
}
