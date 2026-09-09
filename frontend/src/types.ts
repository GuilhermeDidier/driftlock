export type RunStatus = "running" | "published" | "healed" | "blocked" | "error";
export type Verdict = "pass" | "partial" | "drift" | "";

export interface RunEvent {
  seq: number; at: string; level: "info" | "warn" | "block" | "ok";
  code: string; message: string; data: Record<string, unknown>;
}

export interface HealAttempt {
  attempt: number; outcome: string; reason: string;
  from_version: number | null; candidate_version: number | null;
  candidate_rules: Record<string, unknown> | null;
  baseline_size: number; recovered: number;
  model: string; input_tokens: number; output_tokens: number;
  cost_usd: string; latency_ms: number;
}

export interface RecordRow {
  index: number; status: "published" | "quarantined" | "withheld";
  value: Record<string, string | number | boolean | null>;
  violations: { code: string; field: string | null; message: string }[];
}

export interface Run {
  id: number; source: string; status: RunStatus; verdict: Verdict;
  mapping_version: number | null; started_at: string; duration_ms: number | null;
  records_read: number; records_published: number; records_quarantined: number;
  drift_detected: boolean; cost_usd: string; error: string;
  report?: {
    verdict: string; fill_rates: Record<string, number>;
    distinct_ratios: Record<string, number>; batch_violations: string[];
  };
  events?: RunEvent[];
  heal_attempts?: HealAttempt[];
  records?: RecordRow[];
  budget?: Budget;
}

export interface Mapping {
  id: number; version: number; status: string; origin: string;
  rules: Record<string, { selector?: string; attr?: string; column?: string }>;
  note: string; promoted_at: string | null;
  diff: Record<string, { before: unknown; after: unknown }>;
}

export interface ContractField {
  name: string; type: string; description: string;
  required: boolean; stable: boolean;
  min_fill_rate: number | null; min_distinct_ratio: number | null;
}

export interface Source {
  key: string; name: string; kind: string;
  contract: {
    key: string; name: string; unique_by: string[];
    continuity_threshold: number; fields: ContractField[];
  };
  active_mapping: Mapping | null;
  mapping_count: number;
  baseline: { records: Record<string, unknown>[]; pinned: boolean; name: string | null };
  latest_run: Run | null;
  mappings?: Mapping[];
  runs?: Run[];
}

export interface Budget {
  spent_usd: string; cap_usd: string; remaining_usd: string; exhausted: boolean;
}

export interface AppState {
  demo_layout: "v1" | "v2" | "v3";
  budget: Budget;
  sources: Source[];
  recent_runs: Run[];
}
