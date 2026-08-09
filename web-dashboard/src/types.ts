export interface Run {
  run_id: string;
  task_id: string;
  state: string;
  started_at: string;
  attempt_no: number;
  max_attempts: number;
  finished_at?: string | null;
  updated_at?: string | null;
  final_decision?: any;
}

export interface Task {
  id: string;
  type: string;
  risk_level: string;
  instruction: string;
  acceptance_criteria: string[];
  required_gates: string[];
}

export interface CheckResult {
  check_type: string;
  command: string;
  exit_code: number;
  status: string;
  duration_seconds: number;
  error_message: string;
}

export interface VerificationReport {
  checks: CheckResult[];
  required_passed: boolean;
  final_status: string;
  blockers: string[];
  unresolved_unknowns: string[];
}

export interface Patch {
  id: string;
  attempt_no: number;
  base_commit: string;
  diff: string;
  changed_files: string[];
  assumptions: string[];
}

export interface EvidenceItem {
  id: string;
  type: string;
  source: string;
  locator: string;
  content: string;
  state: string;
}

export interface EvidenceResponse {
  items: EvidenceItem[];
}

export interface Finding {
  id: string;
  severity: string;
  category: string;
  message: string;
  detail?: string;
}

export interface ReviewResponse {
  findings: Finding[];
  final_decision: any | null;
}

export interface ProvenanceResponse {
  edges: any[];
  summary: any | null;
}

export interface BenchmarkInfo {
  id: string;
  name: string;
  task_count: number;
}

export interface ConfigResponse {
  max_attempts: number;
  required_gates: string[];
  [key: string]: any;
}

export interface StatsResponse {
  total_runs: number;
  states: Record<string, number>;
  verified: number;
  rejected: number;
  needs_review: number;
  failed: number;
  success_rate: number;
}

export interface LLMStatus {
  provider: string;
  model: string;
  base_url: string;
  max_tokens: number;
  temperature: number;
}

export interface LLMModelsResponse {
  provider: string;
  models: string[];
  connected: boolean;
  error?: string;
}

export interface RunEvent {
  id: string;
  run_id: string;
  task_id: string;
  state: string;
  event_type: string;
  payload: any;
  timestamp: string;
}
