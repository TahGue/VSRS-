import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Plus, RefreshCw } from 'lucide-react';
import { api } from '../api';
import type { Run } from '../types';

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [repoPath, setRepoPath] = useState('');
  const [instruction, setInstruction] = useState('');
  const [taskType, setTaskType] = useState('bugfix');

  const fetchRuns = async () => {
    setLoading(true);
    try {
      const data = await api.listRuns();
      setRuns(Array.isArray(data) ? data : []);
      setError('');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchRuns(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createRun({ repo_path: repoPath, task_instruction: instruction, task_type: taskType });
      setShowForm(false);
      setRepoPath('');
      setInstruction('');
      fetchRuns();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const stateBadge = (state: string) => {
    const cls = state === 'verified' ? 'badge-success' :
                state === 'failed' ? 'badge-danger' :
                state === 'repairing' ? 'badge-warning' : 'badge-neutral';
    return <span className={`badge ${cls}`}>{state}</span>;
  };

  return (
    <div>
      <div className="page-header">
        <h1>Runs</h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn" onClick={fetchRuns}>
            <RefreshCw size={16} /> Refresh
          </button>
          <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
            <Plus size={16} /> New Run
          </button>
        </div>
      </div>

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
              <input className="input" value={instruction} onChange={e => setInstruction(e.target.value)} placeholder="Fix the bug in..." required />
            </div>
            <div className="form-group">
              <label>Task Type</label>
              <select className="input" value={taskType} onChange={e => setTaskType(e.target.value)}>
                <option value="bugfix">Bugfix</option>
                <option value="feature">Feature</option>
                <option value="refactor">Refactor</option>
                <option value="test">Test</option>
                <option value="security">Security</option>
              </select>
            </div>
            <button type="submit" className="btn btn-primary">Start Run</button>
          </form>
        </div>
      )}

      {error && <div className="error-msg">Error: {error}</div>}
      {loading && <div className="loading">Loading...</div>}

      {!loading && !error && runs.length === 0 && (
        <div className="empty-state">No runs yet. Click "New Run" to create one.</div>
      )}

      {!loading && !error && runs.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <table>
            <thead>
              <tr>
                <th>Run ID</th>
                <th>State</th>
                <th>Attempt</th>
                <th>Max Attempts</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {runs.map(run => (
                <tr key={run.run_id}>
                  <td>
                    <Link to={`/runs/${run.run_id}`}>{run.run_id}</Link>
                  </td>
                  <td>{stateBadge(run.state)}</td>
                  <td>{run.attempt_no}</td>
                  <td>{run.max_attempts}</td>
                  <td>{run.started_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
