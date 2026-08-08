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

export const api = {
  health: () => request<{ status: string }>('GET', '/health'.replace('/api/v1', '')),
  listRuns: async () => {
    const res = await request<{ runs: any[]; total: number; offset: number; limit: number }>('GET', '/runs');
    return res.runs;
  },
  createRun: (data: { repo_path: string; task_instruction: string; task_type: string }) =>
    request<any>('POST', '/runs', data),
  getRun: (id: string) => request<any>('GET', `/runs/${id}`),
  getRunTask: (id: string) => request<any>('GET', `/runs/${id}/task`),
  getRunEvidence: (id: string) => request<any>('GET', `/runs/${id}/evidence`),
  getRunDiff: (id: string) => request<any>('GET', `/runs/${id}/diff`),
  getRunVerification: (id: string) => request<any>('GET', `/runs/${id}/verify`),
  getRunReview: (id: string) => request<any>('GET', `/runs/${id}/review`),
  getRunProvenance: (id: string) => request<any>('GET', `/runs/${id}/provenance`),
  getRunReport: (id: string) => request<string>('GET', `/runs/${id}/report`),
  getConfig: () => request<any>('GET', '/config'),
  listBenchmarks: () => request<any>('GET', '/benchmarks'),
};
