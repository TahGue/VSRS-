/**
 * VSRS VSCode Extension - Type definitions
 * Shared types used across the extension
 */

export interface TaskInfo {
    id: string;
    type: string;
    instruction: string;
    status: TaskStatus;
    created_at: string;
    updated_at: string;
    result?: TaskResult;
}

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface TaskResult {
    task_id: string;
    verified: boolean;
    final_status: string;
    checks: CheckResult[];
    blockers: string[];
    duration_seconds: number;
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
    patch_id: string;
    checks: CheckResult[];
    required_passed: boolean;
    blockers: string[];
    final_status: string;
}

export interface PatchCandidate {
    id: string;
    task_id: string;
    attempt_no: number;
    diff: string;
    changed_files: string[];
    changed_symbols: string[];
    assumptions: string[];
    predicted_effects: string[];
}

export interface BenchmarkResult {
    total_tasks: number;
    verified_success_count: number;
    verified_success_rate: number;
    pass_at_1_rate: number;
    repair_success_rate: number;
    regression_rate: number;
}

export interface ServerConfig {
    serverUrl: string;
    apiKey: string;
    maxAttempts: number;
    timeout: number;
    requiredGates: string[];
    autoRunVerification: boolean;
}

export interface VSRSClient {
    connect(): Promise<boolean>;
    disconnect(): void;
    isConnected(): boolean;
    createTask(instruction: string, type: string): Promise<TaskInfo>;
    getTask(taskId: string): Promise<TaskInfo>;
    listTasks(): Promise<TaskInfo[]>;
    runVerification(taskId: string): Promise<VerificationReport>;
    runRepair(taskId: string, maxAttempts?: number): Promise<TaskResult>;
    runBenchmark(): Promise<BenchmarkResult>;
    cancelTask(taskId: string): Promise<boolean>;
}
