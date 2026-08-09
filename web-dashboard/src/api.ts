const API_BASE = '/api/v1';

async function request<T>(method: string, path: string, body?: any): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json();
}

async function requestText(path: string): Promise<string> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.text();
}

export const api = {
  health: () => request<{ status: string }>('GET', '/health'.replace('/api/v1', '')),
  // Runs
  listRuns: async (offset = 0, limit = 100) => {
    const res = await request<{ runs: any[]; total: number; offset: number; limit: number }>('GET', `/runs?offset=${offset}&limit=${limit}`);
    return res;
  },
  createRun: (data: { repo_path: string; task_instruction: string; task_type: string; risk?: string; acceptance_criteria?: string[] }) =>
    request<any>('POST', '/runs', data),
  getRun: (id: string) => request<any>('GET', `/runs/${id}`),
  deleteRun: (id: string) => request<{ deleted: boolean }>('DELETE', `/runs/${id}`),
  getRunEvents: (id: string) => request<{ events: any[]; total: number }>('GET', `/runs/${id}/events`),
  getRunTask: (id: string) => request<any>('GET', `/runs/${id}/task`),
  getRunEvidence: (id: string) => request<any>('GET', `/runs/${id}/evidence`),
  getRunDiff: (id: string) => request<any>('GET', `/runs/${id}/diff`),
  getRunVerification: (id: string) => request<any>('GET', `/runs/${id}/verify`),
  getRunReview: (id: string) => request<any>('GET', `/runs/${id}/review`),
  getRunProvenance: (id: string) => request<any>('GET', `/runs/${id}/provenance`),
  getRunReport: (id: string) => requestText(`/runs/${id}/report`),
  // Config
  getConfig: () => request<any>('GET', '/config'),
  // Benchmarks
  listBenchmarks: () => request<any>('GET', '/benchmarks'),
  // LLM
  getLLMModels: () => request<{ provider: string; models: string[]; connected: boolean; error?: string }>('GET', '/llm/models'),
  getLLMStatus: () => request<{ provider: string; model: string; base_url: string; max_tokens: number; temperature: number }>('GET', '/llm/status'),
  // Stats
  getStats: () => request<{ total_runs: number; states: Record<string, number>; verified: number; rejected: number; needs_review: number; failed: number; success_rate: number }>('GET', '/stats'),
};
