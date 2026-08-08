import { useState, useEffect } from 'react';
import { api } from '../api';
import type { ConfigResponse } from '../types';

export default function SettingsPage() {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchConfig = async () => {
      setLoading(true);
      try {
        const data = await api.getConfig();
        setConfig(data);
        setError('');
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };
    fetchConfig();
  }, []);

  return (
    <div>
      <div className="page-header">
        <h1>Settings</h1>
      </div>

      {error && <div className="error-msg">Error: {error}</div>}
      {loading && <div className="loading">Loading...</div>}

      {!loading && !error && config && (
        <div className="card">
          <h2>Configuration</h2>
          <table>
            <tbody>
              {Object.entries(config).map(([key, value]) => (
                <tr key={key}>
                  <td style={{ color: 'var(--text-muted)' }}>{key}</td>
                  <td>
                    {Array.isArray(value) ? value.join(', ') : String(value)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
