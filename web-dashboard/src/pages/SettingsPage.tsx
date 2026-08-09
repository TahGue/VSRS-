import { useState, useEffect } from 'react';
import { Cpu, Settings as SettingsIcon, CheckCircle, XCircle } from 'lucide-react';
import { api } from '../api';
import type { ConfigResponse, LLMStatus, LLMModelsResponse } from '../types';

export default function SettingsPage() {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [llmStatus, setLLMStatus] = useState<LLMStatus | null>(null);
  const [llmModels, setLLMModels] = useState<LLMModelsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchAll = async () => {
      setLoading(true);
      try {
        const [cfg, status, models] = await Promise.all([
          api.getConfig(),
          api.getLLMStatus(),
          api.getLLMModels(),
        ]);
        setConfig(cfg);
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
  }, []);

  return (
    <div>
      <div className="page-header">
        <h1>Settings</h1>
      </div>

      {error && <div className="error-msg">Error: {error}</div>}
      {loading && <div className="loading">Loading...</div>}

      {!loading && !error && (
        <>
          {/* LLM Provider Status */}
          <div className="card">
            <h2 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Cpu size={18} /> LLM Provider Status
            </h2>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
              <div>
                <table>
                  <tbody>
                    <tr>
                      <td style={{ color: 'var(--text-muted)' }}>Provider</td>
                      <td><span className="badge badge-neutral">{llmStatus?.provider ?? '—'}</span></td>
                    </tr>
                    <tr>
                      <td style={{ color: 'var(--text-muted)' }}>Model</td>
                      <td style={{ fontFamily: 'monospace', fontSize: 13 }}>{llmStatus?.model || 'auto-detect'}</td>
                    </tr>
                    <tr>
                      <td style={{ color: 'var(--text-muted)' }}>Base URL</td>
                      <td style={{ fontFamily: 'monospace', fontSize: 13 }}>{llmStatus?.base_url ?? '—'}</td>
                    </tr>
                    <tr>
                      <td style={{ color: 'var(--text-muted)' }}>Max Tokens</td>
                      <td>{llmStatus?.max_tokens ?? '—'}</td>
                    </tr>
                    <tr>
                      <td style={{ color: 'var(--text-muted)' }}>Temperature</td>
                      <td>{llmStatus?.temperature ?? '—'}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div>
                <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                  {llmModels?.connected ? (
                    <><CheckCircle size={20} style={{ color: 'var(--success)' }} /><span className="badge badge-success">Connected</span></>
                  ) : (
                    <><XCircle size={20} style={{ color: 'var(--danger)' }} /><span className="badge badge-danger">Disconnected</span></>
                  )}
                </div>
                {llmModels?.error && (
                  <div style={{ padding: 8, background: 'rgba(248,81,73,0.1)', borderRadius: 4, fontSize: 12, color: 'var(--danger)', marginBottom: 12 }}>
                    {llmModels.error}
                  </div>
                )}
                {llmModels && llmModels.models.length > 0 && (
                  <div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>
                      Available Models ({llmModels.models.length}):
                    </div>
                    <div style={{ maxHeight: 250, overflowY: 'auto' }}>
                      {llmModels.models.map((m, i) => (
                        <div key={i} style={{
                          padding: '6px 10px',
                          fontSize: 13,
                          background: 'var(--bg)',
                          borderRadius: 4,
                          marginBottom: 4,
                          fontFamily: 'monospace',
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                        }}>
                          <Cpu size={14} style={{ color: 'var(--primary)' }} />
                          {m}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {llmModels && llmModels.provider === 'stub' && (
                  <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
                    Using stub provider (no LLM). Set <code style={{ background: 'var(--bg)', padding: '2px 6px', borderRadius: 4 }}>VSRS_MODEL_PROVIDER=lmstudio</code> to enable LLM reasoning.
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Full Configuration */}
          <div className="card">
            <h2 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <SettingsIcon size={18} /> Full Configuration
            </h2>
            {config && (
              <table>
                <tbody>
                  {Object.entries(config).map(([key, value]) => (
                    <tr key={key}>
                      <td style={{ color: 'var(--text-muted)', width: 200 }}>{key}</td>
                      <td>
                        {Array.isArray(value) ? (
                          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                            {value.map((v, i) => <span key={i} className="badge badge-neutral" style={{ fontSize: 11 }}>{String(v)}</span>)}
                          </div>
                        ) : typeof value === 'object' && value !== null ? (
                          <pre style={{ fontSize: 12, fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                            {JSON.stringify(value, null, 2)}
                          </pre>
                        ) : (
                          String(value)
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}
