import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { api } from '../api';
import type { Run, Task, VerificationReport, Patch } from '../types';

export default function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const [run, setRun] = useState<Run | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [verification, setVerification] = useState<VerificationReport | null>(null);
  const [patch, setPatch] = useState<Patch | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!runId) return;
    const fetchData = async () => {
      setLoading(true);
      try {
        const runData = await api.getRun(runId);
        setRun(runData);
        try { setTask(await api.getRunTask(runId)); } catch {}
        try { setVerification(await api.getRunVerification(runId)); } catch {}
        try { setPatch(await api.getRunDiff(runId)); } catch {}
        setError('');
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [runId]);

  if (loading) return <div className="loading">Loading...</div>;
  if (error) return <div className="error-msg">Error: {error}</div>;
  if (!run) return <div className="empty-state">Run not found</div>;

  const statusClass = verification?.required_passed ? 'badge-success' : 'badge-danger';

  return (
    <div>
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Link to="/"><ArrowLeft size={20} /></Link>
          <h1>Run {run.run_id}</h1>
          <span className={`badge ${statusClass}`}>{run.state}</span>
        </div>
      </div>

      <div className="card">
        <h2>Run Info</h2>
        <table>
          <tbody>
            <tr><td style={{ color: 'var(--text-muted)' }}>Task ID</td><td>{run.task_id}</td></tr>
            <tr><td style={{ color: 'var(--text-muted)' }}>State</td><td>{run.state}</td></tr>
            <tr><td style={{ color: 'var(--text-muted)' }}>Attempt</td><td>{run.attempt_no} / {run.max_attempts}</td></tr>
            <tr><td style={{ color: 'var(--text-muted)' }}>Started</td><td>{run.started_at}</td></tr>
          </tbody>
        </table>
      </div>

      {task && (
        <div className="card">
          <h2>Task</h2>
          <table>
            <tbody>
              <tr><td style={{ color: 'var(--text-muted)' }}>Type</td><td>{task.type}</td></tr>
              <tr><td style={{ color: 'var(--text-muted)' }}>Risk</td><td>{task.risk_level}</td></tr>
              <tr><td style={{ color: 'var(--text-muted)' }}>Instruction</td><td>{task.instruction}</td></tr>
              <tr><td style={{ color: 'var(--text-muted)' }}>Gates</td><td>{task.required_gates.join(', ')}</td></tr>
            </tbody>
          </table>
        </div>
      )}

      {verification && (
        <div className="card">
          <h2>Verification</h2>
          <div style={{ marginBottom: 12 }}>
            <span className={`badge ${verification.required_passed ? 'badge-success' : 'badge-danger'}`}>
              {verification.required_passed ? 'PASSED' : 'FAILED'}
            </span>
            <span style={{ marginLeft: 8, color: 'var(--text-muted)' }}>{verification.final_status}</span>
          </div>
          {verification.blockers.length > 0 && (
            <div style={{ marginBottom: 12, color: 'var(--warning)' }}>
              <strong>Blockers:</strong> {verification.blockers.join(', ')}
            </div>
          )}
          <div className="check-list">
            {verification.checks.map((check, i) => (
              <div key={i} className={`check-item ${check.status}`}>
                <span className="check-type">{check.check_type}</span>
                <span className="check-status">{check.status}</span>
                <span className="check-duration">{check.duration_seconds.toFixed(2)}s</span>
                {check.error_message && <pre className="check-error">{check.error_message}</pre>}
              </div>
            ))}
          </div>
        </div>
      )}

      {patch && patch.diff && (
        <div className="card">
          <h2>Patch (Attempt {patch.attempt_no})</h2>
          <div style={{ marginBottom: 8, color: 'var(--text-muted)', fontSize: 13 }}>
            Changed files: {patch.changed_files.join(', ')}
          </div>
          <div className="diff-viewer">
            {patch.diff.split('\n').map((line, i) => (
              <div key={i} className={
                line.startsWith('+') && !line.startsWith('+++') ? 'diff-add' :
                line.startsWith('-') && !line.startsWith('---') ? 'diff-del' :
                line.startsWith('@@') ? 'diff-hunk' : ''
              }>{line}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
