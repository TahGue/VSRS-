import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Download, RefreshCw, FileCode, CheckSquare, Eye, GitBranch, Network, ListChecks } from 'lucide-react';
import { api } from '../api';
import { useRunWebSocket } from '../useWebSocket';
import LiveProgress from '../components/LiveProgress';
import ProvenanceGraph from '../components/ProvenanceGraph';
import type { Run, Task, VerificationReport, Patch, EvidenceItem, Finding } from '../types';

type Tab = 'overview' | 'evidence' | 'patch' | 'verification' | 'review' | 'provenance';

export default function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const [run, setRun] = useState<Run | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [verification, setVerification] = useState<VerificationReport | null>(null);
  const [patch, setPatch] = useState<Patch | null>(null);
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [review, setReview] = useState<{ findings: Finding[]; final_decision: any } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const { events, connected } = useRunWebSocket(runId);

  const fetchAll = useCallback(async () => {
    if (!runId) return;
    try {
      const runData = await api.getRun(runId);
      setRun(runData);
      try { setTask(await api.getRunTask(runId)); } catch {}
      try { setVerification(await api.getRunVerification(runId)); } catch {}
      try { setPatch(await api.getRunDiff(runId)); } catch {}
      try { const ev = await api.getRunEvidence(runId); setEvidence(ev.items || []); } catch {}
      try { setReview(await api.getRunReview(runId)); } catch {}
      setError('');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  useEffect(() => {
    if (!autoRefresh || !runId) return;
    const isComplete = run && ['verified', 'rejected', 'failed'].includes(run.state);
    if (isComplete) return;
    const interval = setInterval(fetchAll, 3000);
    return () => clearInterval(interval);
  }, [autoRefresh, runId, run?.state, fetchAll]);

  const handleDownloadReport = async () => {
    if (!runId) return;
    try {
      const report = await api.getRunReport(runId);
      const blob = new Blob([report], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `vsrs-report-${runId}.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e.message);
    }
  };

  if (loading) return <div className="loading">Loading...</div>;
  if (error) return <div className="error-msg">Error: {error}</div>;
  if (!run) return <div className="empty-state">Run not found</div>;

  const isComplete = ['verified', 'rejected', 'failed'].includes(run.state);
  const statusClass = run.state === 'verified' ? 'badge-success' :
                      run.state === 'failed' || run.state === 'rejected' ? 'badge-danger' :
                      run.state === 'needs_review' ? 'badge-warning' : 'badge-neutral';

  const tabs: { id: Tab; label: string; icon: any; count?: number }[] = [
    { id: 'overview', label: 'Overview', icon: <ListChecks size={16} /> },
    { id: 'evidence', label: 'Evidence', icon: <FileCode size={16} />, count: evidence.length },
    { id: 'patch', label: 'Patch', icon: <GitBranch size={16} /> },
    { id: 'verification', label: 'Verification', icon: <CheckSquare size={16} />, count: verification?.checks.length },
    { id: 'review', label: 'Review', icon: <Eye size={16} />, count: review?.findings.length },
    { id: 'provenance', label: 'Provenance', icon: <Network size={16} /> },
  ];

  return (
    <div>
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Link to="/"><ArrowLeft size={20} /></Link>
          <h1 style={{ fontFamily: 'monospace', fontSize: 18 }}>{run.run_id}</h1>
          <span className={`badge ${statusClass}`}>{run.state}</span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className={`btn ${autoRefresh && !isComplete ? 'btn-primary' : ''}`} onClick={() => setAutoRefresh(!autoRefresh)} disabled={isComplete}>
            <RefreshCw size={16} /> {autoRefresh && !isComplete ? 'Auto' : 'Manual'}
          </button>
          <button className="btn" onClick={fetchAll}>
            <RefreshCw size={16} /> Refresh
          </button>
          <button className="btn" onClick={handleDownloadReport}>
            <Download size={16} /> Report
          </button>
        </div>
      </div>

      {/* Tab bar */}
      <div style={{ display: 'flex', gap: 2, marginBottom: 16, borderBottom: '1px solid var(--border)', paddingBottom: 0 }}>
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '8px 16px',
              background: activeTab === tab.id ? 'var(--surface)' : 'transparent',
              border: 'none',
              borderBottom: activeTab === tab.id ? '2px solid var(--primary)' : '2px solid transparent',
              color: activeTab === tab.id ? 'var(--primary)' : 'var(--text-muted)',
              cursor: 'pointer',
              fontSize: 14,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              borderRadius: 0,
            }}
          >
            {tab.icon}
            {tab.label}
            {tab.count !== undefined && tab.count > 0 && (
              <span style={{ background: 'var(--border)', borderRadius: 10, padding: '0 6px', fontSize: 11 }}>{tab.count}</span>
            )}
          </button>
        ))}
      </div>

      {/* Overview tab */}
      {activeTab === 'overview' && (
        <>
          <LiveProgress events={events} connected={connected} />

          <div className="card">
            <h2>Run Info</h2>
            <table>
              <tbody>
                <tr><td style={{ color: 'var(--text-muted)' }}>Task ID</td><td style={{ fontFamily: 'monospace', fontSize: 13 }}>{run.task_id}</td></tr>
                <tr><td style={{ color: 'var(--text-muted)' }}>State</td><td><span className={`badge ${statusClass}`}>{run.state}</span></td></tr>
                <tr><td style={{ color: 'var(--text-muted)' }}>Attempt</td><td>{run.attempt_no} / {run.max_attempts}</td></tr>
                <tr><td style={{ color: 'var(--text-muted)' }}>Started</td><td>{run.started_at}</td></tr>
                <tr><td style={{ color: 'var(--text-muted)' }}>Finished</td><td>{run.finished_at || '—'}</td></tr>
              </tbody>
            </table>
          </div>

          {task && (
            <div className="card">
              <h2>Task</h2>
              <table>
                <tbody>
                  <tr><td style={{ color: 'var(--text-muted)' }}>Type</td><td><span className="badge badge-neutral">{task.type}</span></td></tr>
                  <tr><td style={{ color: 'var(--text-muted)' }}>Risk</td><td><span className={`badge ${task.risk_level === 'high' ? 'badge-danger' : task.risk_level === 'medium' ? 'badge-warning' : 'badge-success'}`}>{task.risk_level}</span></td></tr>
                  <tr><td style={{ color: 'var(--text-muted)' }}>Instruction</td><td style={{ whiteSpace: 'pre-wrap' }}>{task.instruction}</td></tr>
                  {task.acceptance_criteria.length > 0 && (
                    <tr>
                      <td style={{ color: 'var(--text-muted)' }}>Criteria</td>
                      <td>
                        <ul style={{ margin: 0, paddingLeft: 20 }}>
                          {task.acceptance_criteria.map((c, i) => <li key={i}>{c}</li>)}
                        </ul>
                      </td>
                    </tr>
                  )}
                  <tr><td style={{ color: 'var(--text-muted)' }}>Gates</td><td>{task.required_gates.join(', ')}</td></tr>
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Evidence tab */}
      {activeTab === 'evidence' && (
        <div className="card">
          <h2>Evidence Items ({evidence.length})</h2>
          {evidence.length === 0 && <div className="empty-state" style={{ padding: 24 }}>No evidence collected.</div>}
          {evidence.map((item, i) => (
            <div key={i} className="check-item" style={{ display: 'block', padding: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span className="badge badge-neutral">{item.type}</span>
                <span style={{ fontFamily: 'monospace', fontSize: 12, color: 'var(--text-muted)' }}>{item.locator}</span>
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>Source: {item.source}</div>
              {item.content && (
                <pre style={{ marginTop: 8, fontSize: 12, color: 'var(--text)', whiteSpace: 'pre-wrap', background: 'var(--bg)', padding: 8, borderRadius: 4 }}>{item.content}</pre>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Patch tab */}
      {activeTab === 'patch' && (
        <div className="card">
          <h2>Patch {patch && `(Attempt ${patch.attempt_no})`}</h2>
          {!patch && <div className="empty-state" style={{ padding: 24 }}>No patch generated.</div>}
          {patch && (
            <>
              <div style={{ marginBottom: 12 }}>
                <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Changed files: </span>
                {patch.changed_files.map((f, i) => (
                  <span key={i} className="badge badge-neutral" style={{ marginRight: 6, fontFamily: 'monospace', fontSize: 12 }}>{f}</span>
                ))}
              </div>
              {patch.assumptions.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Assumptions:</span>
                  <ul style={{ margin: '4px 0', paddingLeft: 20, fontSize: 13 }}>
                    {patch.assumptions.map((a, i) => <li key={i}>{a}</li>)}
                  </ul>
                </div>
              )}
              {patch.diff ? (
                <div className="diff-viewer">
                  {patch.diff.split('\n').map((line, i) => (
                    <div key={i} className={
                      line.startsWith('+') && !line.startsWith('+++') ? 'diff-add' :
                      line.startsWith('-') && !line.startsWith('---') ? 'diff-del' :
                      line.startsWith('@@') ? 'diff-hunk' : ''
                    }>{line}</div>
                  ))}
                </div>
              ) : (
                <div style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>No diff content available.</div>
              )}
            </>
          )}
        </div>
      )}

      {/* Verification tab */}
      {activeTab === 'verification' && (
        <div className="card">
          <h2>Verification</h2>
          {!verification && <div className="empty-state" style={{ padding: 24 }}>No verification report.</div>}
          {verification && (
            <>
              <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
                <span className={`badge ${verification.required_passed ? 'badge-success' : 'badge-danger'}`}>
                  {verification.required_passed ? 'PASSED' : 'FAILED'}
                </span>
                <span style={{ color: 'var(--text-muted)' }}>{verification.final_status}</span>
              </div>
              {verification.blockers.length > 0 && (
                <div style={{ marginBottom: 16, padding: 12, background: 'rgba(248,81,73,0.1)', borderRadius: 'var(--radius)', border: '1px solid var(--danger)' }}>
                  <strong style={{ color: 'var(--danger)' }}>Blockers:</strong>
                  <ul style={{ margin: '4px 0', paddingLeft: 20 }}>
                    {verification.blockers.map((b, i) => <li key={i} style={{ fontSize: 13 }}>{b}</li>)}
                  </ul>
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
            </>
          )}
        </div>
      )}

      {/* Review tab */}
      {activeTab === 'review' && (
        <div className="card">
          <h2>Critic Review</h2>
          {!review && <div className="empty-state" style={{ padding: 24 }}>No review available.</div>}
          {review && (
            <>
              {review.final_decision && (
                <div style={{ marginBottom: 16, padding: 12, background: 'var(--bg)', borderRadius: 'var(--radius)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                    <span style={{ fontWeight: 600 }}>Final Decision:</span>
                    <span className={`badge ${review.final_decision.status === 'verified' ? 'badge-success' : review.final_decision.status === 'rejected' ? 'badge-danger' : 'badge-warning'}`}>
                      {review.final_decision.status}
                    </span>
                  </div>
                  {review.final_decision.summary && (
                    <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>{review.final_decision.summary}</div>
                  )}
                </div>
              )}
              <h3 style={{ marginBottom: 8 }}>Findings ({review.findings.length})</h3>
              {review.findings.length === 0 && <div style={{ color: 'var(--text-muted)' }}>No findings.</div>}
              {review.findings.map((f, i) => {
                const sev = f.severity?.toLowerCase() || 'minor';
                const cls = sev === 'blocker' ? 'badge-danger' : sev === 'major' ? 'badge-warning' : 'badge-neutral';
                return (
                  <div key={i} className="check-item" style={{ display: 'block', padding: 12, marginBottom: 8, borderLeft: `3px solid ${sev === 'blocker' ? 'var(--danger)' : sev === 'major' ? 'var(--warning)' : 'var(--border)'}` }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <span className={`badge ${cls}`}>{f.severity}</span>
                      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{f.category}</span>
                    </div>
                    <div style={{ fontSize: 13 }}>{f.message}</div>
                    {f.detail && <pre style={{ marginTop: 6, fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'pre-wrap' }}>{f.detail}</pre>}
                  </div>
                );
              })}
            </>
          )}
        </div>
      )}

      {/* Provenance tab */}
      {activeTab === 'provenance' && run && <ProvenanceGraph runId={run.run_id} />}
    </div>
  );
}
