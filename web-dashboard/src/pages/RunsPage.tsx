import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Plus, RefreshCw, Trash2, Search, Play, Filter } from 'lucide-react';
import { api } from '../api';
import type { Run } from '../types';

const STATE_FILTERS = ['all', 'verified', 'needs_review', 'failed', 'rejected', 'intake'];

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [repoPath, setRepoPath] = useState('');
  const [instruction, setInstruction] = useState('');
  const [taskType, setTaskType] = useState('bugfix');
  const [riskLevel, setRiskLevel] = useState('low');
  const [acceptanceCriteria, setAcceptanceCriteria] = useState('');
  const [search, setSearch] = useState('');
  const [stateFilter, setStateFilter] = useState('all');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [creating, setCreating] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const fetchRuns = useCallback(async () => {
    try {
      const data = await api.listRuns(0, 200);
      setRuns(Array.isArray(data.runs) ? data.runs : []);
      setTotal(data.total ?? 0);
      setError('');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchRuns(); }, [fetchRuns]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchRuns, 5000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchRuns]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    try {
      const criteria = acceptanceCriteria
        ? acceptanceCriteria.split('\n').map(s => s.trim()).filter(Boolean)
        : [];
      await api.createRun({
        repo_path: repoPath,
        task_instruction: instruction,
        task_type: taskType,
        risk: riskLevel,
        acceptance_criteria: criteria,
      });
      setShowForm(false);
      setRepoPath('');
      setInstruction('');
      setAcceptanceCriteria('');
      setRiskLevel('low');
      fetchRuns();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (runId: string) => {
    try {
      await api.deleteRun(runId);
      setDeleteId(null);
      fetchRuns();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const filteredRuns = runs.filter(r => {
    if (stateFilter !== 'all' && r.state !== stateFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      return r.run_id?.toLowerCase().includes(q) ||
             r.task_id?.toLowerCase().includes(q) ||
             r.state?.toLowerCase().includes(q);
    }
    return true;
  });

  const stateBadge = (state: string) => {
    const cls = state === 'verified' ? 'badge-success' :
                state === 'failed' || state === 'rejected' ? 'badge-danger' :
                state === 'needs_review' || state === 'repairing' ? 'badge-warning' : 'badge-neutral';
    return <span className={`badge ${cls}`}>{state}</span>;
  };

  const formatDate = (s: string) => {
    try {
      const d = new Date(s);
      return d.toLocaleString();
    } catch {
      return s;
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>Runs <span style={{ fontSize: 14, color: 'var(--text-muted)' }}>({total} total)</span></h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className={`btn ${autoRefresh ? 'btn-primary' : ''}`} onClick={() => setAutoRefresh(!autoRefresh)}>
            <RefreshCw size={16} /> {autoRefresh ? 'Auto' : 'Manual'}
          </button>
          <button className="btn" onClick={fetchRuns}>
            <RefreshCw size={16} /> Refresh
          </button>
          <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
            <Plus size={16} /> New Run
          </button>
        </div>
      </div>

      {/* New Run form */}
      {showForm && (
        <div className="card">
          <h2>Create New Run</h2>
          <form onSubmit={handleCreate}>
            <div className="form-group">
              <label>Repository Path</label>
              <input className="input" value={repoPath} onChange={e => setRepoPath(e.target.value)} placeholder="/path/to/repo" required />
            </div>
            <div className="form-group">
              <label>Task Instruction</label>
              <textarea className="input" value={instruction} onChange={e => setInstruction(e.target.value)} placeholder="Describe the task in detail..." required rows={3} style={{ fontFamily: 'inherit', resize: 'vertical' }} />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div className="form-group">
                <label>Task Type</label>
                <select className="input" value={taskType} onChange={e => setTaskType(e.target.value)}>
                  <option value="bugfix">Bugfix</option>
                  <option value="feature">Feature</option>
                  <option value="refactor">Refactor</option>
                  <option value="test">Test</option>
                  <option value="security">Security</option>
                  <option value="migration">Migration</option>
                </select>
              </div>
              <div className="form-group">
                <label>Risk Level</label>
                <select className="input" value={riskLevel} onChange={e => setRiskLevel(e.target.value)}>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </div>
            </div>
            <div className="form-group">
              <label>Acceptance Criteria (one per line)</label>
              <textarea className="input" value={acceptanceCriteria} onChange={e => setAcceptanceCriteria(e.target.value)} placeholder={"test passes\nfunction exists"} rows={3} style={{ fontFamily: 'inherit', resize: 'vertical' }} />
            </div>
            <button type="submit" className="btn btn-primary" disabled={creating}>
              <Play size={16} /> {creating ? 'Starting...' : 'Start Run'}
            </button>
          </form>
        </div>
      )}

      {error && <div className="error-msg">Error: {error}</div>}

      {/* Search + Filter bar */}
      {!loading && runs.length > 0 && (
        <div className="card" style={{ padding: 12, marginBottom: 16, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
            <Search size={16} style={{ position: 'absolute', left: 10, top: 10, color: 'var(--text-muted)' }} />
            <input
              className="input"
              style={{ paddingLeft: 34 }}
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search by run ID, task ID, or state..."
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Filter size={16} style={{ color: 'var(--text-muted)' }} />
            {STATE_FILTERS.map(f => (
              <button
                key={f}
                className={`btn ${stateFilter === f ? 'btn-primary' : ''}`}
                style={{ padding: '4px 12px', fontSize: 12 }}
                onClick={() => setStateFilter(f)}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
      )}

      {loading && <div className="loading">Loading...</div>}

      {!loading && !error && runs.length === 0 && (
        <div className="empty-state">
          <p>No runs yet.</p>
          <button className="btn btn-primary" onClick={() => setShowForm(true)} style={{ marginTop: 12 }}>
            <Plus size={16} /> Create your first run
          </button>
        </div>
      )}

      {!loading && !error && filteredRuns.length === 0 && runs.length > 0 && (
        <div className="empty-state">No runs match your filters.</div>
      )}

      {/* Runs table */}
      {!loading && !error && filteredRuns.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <table>
            <thead>
              <tr>
                <th>Run ID</th>
                <th>State</th>
                <th>Attempt</th>
                <th>Started</th>
                <th>Finished</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredRuns.map(run => (
                <tr key={run.run_id}>
                  <td>
                    <Link to={`/runs/${run.run_id}`} style={{ fontFamily: 'monospace', fontSize: 13 }}>
                      {run.run_id.length > 30 ? run.run_id.slice(0, 27) + '...' : run.run_id}
                    </Link>
                  </td>
                  <td>{stateBadge(run.state)}</td>
                  <td>{run.attempt_no} / {run.max_attempts}</td>
                  <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{formatDate(run.started_at)}</td>
                  <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{run.finished_at ? formatDate(run.finished_at) : '—'}</td>
                  <td>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <Link to={`/runs/${run.run_id}`} className="btn" style={{ padding: '4px 10px', fontSize: 12 }}>
                        View
                      </Link>
                      <button
                        className="btn"
                        style={{ padding: '4px 10px', fontSize: 12, color: 'var(--danger)' }}
                        onClick={() => setDeleteId(run.run_id)}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Delete confirmation */}
      {deleteId && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }} onClick={() => setDeleteId(null)}>
          <div className="card" style={{ maxWidth: 400 }} onClick={e => e.stopPropagation()}>
            <h2>Delete Run?</h2>
            <p style={{ color: 'var(--text-muted)', marginBottom: 16, fontSize: 14 }}>
              This will permanently delete the run and all associated data (evidence, patches, verification, events).
            </p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn" onClick={() => setDeleteId(null)}>Cancel</button>
              <button className="btn btn-primary" style={{ background: 'var(--danger)', borderColor: 'var(--danger)' }} onClick={() => handleDelete(deleteId)}>
                <Trash2 size={16} /> Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
