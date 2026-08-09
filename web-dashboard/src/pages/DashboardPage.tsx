import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Activity, CheckCircle, XCircle, AlertCircle, TrendingUp, Cpu } from 'lucide-react';
import { api } from '../api';
import type { StatsResponse, LLMStatus, LLMModelsResponse } from '../types';

export default function DashboardPage() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [llmStatus, setLLMStatus] = useState<LLMStatus | null>(null);
  const [llmModels, setLLMModels] = useState<LLMModelsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchAll = async () => {
      setLoading(true);
      try {
        const [s, status, models] = await Promise.all([
          api.getStats(),
          api.getLLMStatus(),
          api.getLLMModels(),
        ]);
        setStats(s);
        setLLMStatus(status);
        setLLMModels(models);
        setError('');
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };
    fetchAll();
    const interval = setInterval(fetchAll, 10000);
    return () => clearInterval(interval);
  }, []);

  if (loading && !stats) return <div className="loading">Loading dashboard...</div>;
  if (error) return <div className="error-msg">Error: {error}</div>;

  const metrics = [
    { label: 'Total Runs', value: stats?.total_runs ?? 0, icon: <Activity size={20} />, color: 'var(--primary)' },
    { label: 'Verified', value: stats?.verified ?? 0, icon: <CheckCircle size={20} />, color: 'var(--success)' },
    { label: 'Needs Review', value: stats?.needs_review ?? 0, icon: <AlertCircle size={20} />, color: 'var(--warning)' },
    { label: 'Failed', value: stats?.failed ?? 0, icon: <XCircle size={20} />, color: 'var(--danger)' },
  ];

  return (
    <div>
      <div className="page-header">
        <h1>Dashboard</h1>
        <span className="badge badge-success" style={{ fontSize: 11 }}>Auto-refresh 10s</span>
      </div>

      {/* Metrics grid */}
      <div className="metrics-grid" style={{ marginBottom: 24 }}>
        {metrics.map((m, i) => (
          <div key={i} className="card metric-card" style={{ padding: 20, textAlign: 'center' }}>
            <div style={{ color: m.color, marginBottom: 8, display: 'flex', justifyContent: 'center' }}>{m.icon}</div>
            <div className="metric-value" style={{ color: m.color }}>{m.value}</div>
            <div className="metric-label">{m.label}</div>
          </div>
        ))}
      </div>

      {/* Success rate + state breakdown */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
        <div className="card">
          <h2 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <TrendingUp size={18} /> Success Rate
          </h2>
          <div style={{ fontSize: 36, fontWeight: 700, color: stats && stats.success_rate > 50 ? 'var(--success)' : 'var(--warning)' }}>
            {stats?.success_rate ?? 0}%
          </div>
          <div style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 4 }}>
            {stats?.verified ?? 0} verified out of {stats?.total_runs ?? 0} total runs
          </div>
        </div>

        <div className="card">
          <h2>Run States</h2>
          {stats && Object.entries(stats.states).map(([state, count]) => {
            const pct = stats.total_runs > 0 ? (count / stats.total_runs) * 100 : 0;
            const cls = state === 'verified' ? 'badge-success' :
                        state === 'failed' ? 'badge-danger' :
                        state === 'rejected' ? 'badge-danger' :
                        state === 'needs_review' ? 'badge-warning' : 'badge-neutral';
            return (
              <div key={state} style={{ marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span className={`badge ${cls}`}>{state}</span>
                  <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>{count} ({pct.toFixed(0)}%)</span>
                </div>
                <div style={{ height: 6, background: 'var(--bg)', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${pct}%`, background: 'var(--primary)', borderRadius: 3 }} />
                </div>
              </div>
            );
          })}
          {stats && Object.keys(stats.states).length === 0 && (
            <div style={{ color: 'var(--text-muted)' }}>No runs yet.</div>
          )}
        </div>
      </div>

      {/* LLM Status */}
      <div className="card">
        <h2 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Cpu size={18} /> LLM Provider
        </h2>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div>
            <table>
              <tbody>
                <tr><td style={{ color: 'var(--text-muted)' }}>Provider</td><td>{llmStatus?.provider ?? '—'}</td></tr>
                <tr><td style={{ color: 'var(--text-muted)' }}>Model</td><td>{llmStatus?.model || 'auto-detect'}</td></tr>
                <tr><td style={{ color: 'var(--text-muted)' }}>Base URL</td><td>{llmStatus?.base_url ?? '—'}</td></tr>
                <tr><td style={{ color: 'var(--text-muted)' }}>Max Tokens</td><td>{llmStatus?.max_tokens ?? '—'}</td></tr>
                <tr><td style={{ color: 'var(--text-muted)' }}>Temperature</td><td>{llmStatus?.temperature ?? '—'}</td></tr>
              </tbody>
            </table>
          </div>
          <div>
            <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className={`badge ${llmModels?.connected ? 'badge-success' : 'badge-danger'}`}>
                {llmModels?.connected ? 'Connected' : 'Disconnected'}
              </span>
              {llmModels?.error && <span style={{ color: 'var(--danger)', fontSize: 12 }}>{llmModels.error}</span>}
            </div>
            {llmModels && llmModels.models.length > 0 && (
              <div style={{ maxHeight: 200, overflowY: 'auto' }}>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>Available Models ({llmModels.models.length}):</div>
                {llmModels.models.map((m, i) => (
                  <div key={i} style={{ padding: '4px 8px', fontSize: 13, background: 'var(--bg)', borderRadius: 4, marginBottom: 4, fontFamily: 'monospace' }}>
                    {m}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Quick actions */}
      <div className="card" style={{ textAlign: 'center' }}>
        <Link to="/" className="btn btn-primary" style={{ marginRight: 12 }}>
          <Activity size={16} /> View Runs
        </Link>
        <Link to="/settings" className="btn">
          Configure Settings
        </Link>
      </div>
    </div>
  );
}
