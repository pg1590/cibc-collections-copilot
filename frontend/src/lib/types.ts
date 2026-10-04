// Response shapes from docs/api-contract.md (API v1). Arrays whose item
// fields the contract does not fix are typed as generic records and rendered
// column-by-column from whatever the backend actually returns.

export type Role = "analyst" | "agent" | "supervisor";
export type ApiRecord = Record<string, unknown>;

export interface Generation {
  provider: string;
  model?: string;
  status: string;
  detail?: string;
}

export type HardshipStatus = "recorded" | "possible" | "not_established";

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
  explanation?: string;
  sql_or_sources: string;
  refused: boolean;
  reason: string | null;
  rows: ApiRecord[];
  sources: unknown[];
  execution_ms: number;
  snapshot_date: string;
  generation?: Generation;
  plan?: ApiRecord;
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
  summary_evidence?: string;
  signals: Signal[];
  recommendation: string;
  policy_sources: unknown[];
  draft: string;
  contact_hold: boolean;
  status: string;
  model: { name: string; version: string };
  features: ApiRecord;
  recommendation_reason?: string;
  hardship_status?: HardshipStatus;
  recorded_hardship_cases?: string[];
  generation?: Generation;
}

export type Decision = "approve" | "reject" | "edit";

export interface ReviewItem {
  brief_id: string;
  customer_id: string;
  summary: string;
  summary_evidence?: string;
  recommendation: string;
  draft: string;
  contact_hold?: boolean;
  status: string;
  created_at: string;
  decision: Decision | null;
  reason: string | null;
  reviewer: string | null;
  recommendation_reason?: string;
  hardship_status?: HardshipStatus;
  recorded_hardship_cases?: string[];
  generation?: Generation;
  policy_sources?: unknown[];
  signals?: Signal[];
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

export interface VoiceSample {
  voice_sample_id: string;
  transcript_id: string;
  case_id: string;
  call_start_ts: string;
  language: string;
  duration_sec: number;
  audio_available: boolean;
}

export interface CustomerVoice {
  items: VoiceSample[];
  speech_to_text_available: boolean;
  speech_model: string;
  note: string;
}

export interface VoiceTranscription {
  status: "not_started" | "queued" | "running" | "completed" | "failed";
  job_id?: string;
  error?: string;
  transcript?: {
    text: string;
    segments: { start: number; end: number; text: string }[];
    language: string;
    language_probability: number;
    model: string;
    source_sha256: string;
    created_at: string;
    features: Record<string, number>;
    speaker_attribution: "unavailable";
    review_required: true;
    duration_sec: number;
    processing_seconds: number;
  };
}
