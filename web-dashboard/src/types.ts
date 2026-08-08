export interface Run {
  run_id: string;
  task_id: string;
  state: string;
  started_at: string;
  attempt_no: number;
  max_attempts: number;
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

export interface EvidenceResponse {
  items: any[];
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
