import { useState, useEffect } from 'react';
import { api } from '../api';
import type { BenchmarkInfo } from '../types';

export default function BenchmarksPage() {
  const [benchmarks, setBenchmarks] = useState<BenchmarkInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchBenchmarks = async () => {
      setLoading(true);
      try {
        const data = await api.listBenchmarks();
        setBenchmarks(Array.isArray(data) ? data : []);
        setError('');
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };
    fetchBenchmarks();
  }, []);

  return (
    <div>
      <div className="page-header">
        <h1>Benchmarks</h1>
      </div>

      {error && <div className="error-msg">Error: {error}</div>}
      {loading && <div className="loading">Loading...</div>}

      {!loading && !error && benchmarks.length === 0 && (
        <div className="empty-state">No benchmarks available.</div>
      )}

      {!loading && !error && benchmarks.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Tasks</th>
              </tr>
            </thead>
            <tbody>
              {benchmarks.map(bm => (
                <tr key={bm.id}>
                  <td>{bm.id}</td>
                  <td>{bm.name}</td>
                  <td>{bm.task_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
