import { useState, useEffect } from 'react';
import { api } from '../api';

interface ProvenanceNode {
  id: string;
  label: string;
  type: string;
}

interface ProvenanceEdge {
  source: string;
  target: string;
  relation: string;
}

const typeColors: Record<string, string> = {
  task: '#2f81f7',
  evidence: '#3fb950',
  hypothesis: '#d29922',
  patch: '#f85149',
  verification: '#a371f7',
  review: '#f0883e',
  run: '#2f81f7',
  default: '#8b949e',
};

export default function ProvenanceGraph({ runId }: { runId: string }) {
  const [nodes, setNodes] = useState<ProvenanceNode[]>([]);
  const [edges, setEdges] = useState<ProvenanceEdge[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<ProvenanceNode | null>(null);

  useEffect(() => {
    const fetchProvenance = async () => {
      setLoading(true);
      try {
        const data = await api.getRunProvenance(runId);
        const edgeList: ProvenanceEdge[] = data.edges || [];
        const nodeMap: Record<string, ProvenanceNode> = {};

        for (const edge of edgeList) {
          if (!nodeMap[edge.source]) {
            nodeMap[edge.source] = { id: edge.source, label: edge.source, type: 'default' };
          }
          if (!nodeMap[edge.target]) {
            nodeMap[edge.target] = { id: edge.target, label: edge.target, type: 'default' };
          }
        }

        if (data.summary) {
          if (data.summary.task_id) {
            nodeMap[data.summary.task_id] = { ...nodeMap[data.summary.task_id], type: 'task', label: `Task: ${data.summary.task_id}` };
          }
          if (data.summary.run_id) {
            nodeMap[data.summary.run_id] = { ...nodeMap[data.summary.run_id], type: 'run', label: `Run: ${data.summary.run_id}` };
          }
        }

        setNodes(Object.values(nodeMap));
        setEdges(edgeList);
        setError('');
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };
    fetchProvenance();
  }, [runId]);

  if (loading) return <div className="loading">Loading provenance...</div>;
  if (error) return <div className="error-msg">Error: {error}</div>;
  if (nodes.length === 0) {
    return <div className="empty-state" style={{ padding: 24 }}>No provenance data available.</div>;
  }

  const radius = Math.max(120, nodes.length * 25);
  const centerX = 200;
  const centerY = 200;
  const positions: Record<string, { x: number; y: number }> = {};
  nodes.forEach((node, i) => {
    const angle = (i / nodes.length) * 2 * Math.PI;
    positions[node.id] = {
      x: centerX + radius * Math.cos(angle),
      y: centerY + radius * Math.sin(angle),
    };
  });

  return (
    <div className="card">
      <h2>Provenance Graph</h2>
      <div style={{ display: 'flex', gap: 16 }}>
        <svg
          width="400"
          height="400"
          viewBox="0 0 400 400"
          style={{ background: 'var(--bg)', borderRadius: 'var(--radius)', flexShrink: 0 }}
        >
          {edges.map((edge, i) => {
            const src = positions[edge.source];
            const tgt = positions[edge.target];
            if (!src || !tgt) return null;
            return (
              <g key={i}>
                <line
                  x1={src.x}
                  y1={src.y}
                  x2={tgt.x}
                  y2={tgt.y}
                  stroke="var(--border)"
                  strokeWidth="1.5"
                  markerEnd="url(#arrowhead)"
                />
                <text
                  x={(src.x + tgt.x) / 2}
                  y={(src.y + tgt.y) / 2}
                  fill="var(--text-muted)"
                  fontSize="9"
                  textAnchor="middle"
                >
                  {edge.relation}
                </text>
              </g>
            );
          })}
          {nodes.map(node => {
            const pos = positions[node.id];
            if (!pos) return null;
            const color = typeColors[node.type] || typeColors.default;
            const isSelected = selected?.id === node.id;
            return (
              <g
                key={node.id}
                onClick={() => setSelected(node)}
                style={{ cursor: 'pointer' }}
              >
                <circle
                  cx={pos.x}
                  cy={pos.y}
                  r={isSelected ? 12 : 8}
                  fill={color}
                  stroke={isSelected ? 'white' : 'none'}
                  strokeWidth="2"
                />
                <text
                  x={pos.x}
                  y={pos.y + 22}
                  fill="var(--text)"
                  fontSize="8"
                  textAnchor="middle"
                >
                  {node.label.length > 20 ? node.label.slice(0, 17) + '...' : node.label}
                </text>
              </g>
            );
          })}
          <defs>
            <marker
              id="arrowhead"
              markerWidth="6"
              markerHeight="4"
              refX="5"
              refY="2"
              orient="auto"
            >
              <polygon points="0 0, 6 2, 0 4" fill="var(--border)" />
            </marker>
          </defs>
        </svg>

        <div style={{ flex: 1 }}>
          {selected ? (
            <div>
              <h3 style={{ marginBottom: 8 }}>Node Details</h3>
              <table>
                <tbody>
                  <tr><td style={{ color: 'var(--text-muted)' }}>ID</td><td>{selected.id}</td></tr>
                  <tr><td style={{ color: 'var(--text-muted)' }}>Type</td><td>
                    <span className="badge badge-neutral">{selected.type}</span>
                  </td></tr>
                  <tr><td style={{ color: 'var(--text-muted)' }}>Label</td><td>{selected.label}</td></tr>
                </tbody>
              </table>
              <h3 style={{ marginTop: 16, marginBottom: 8 }}>Connections</h3>
              <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                {edges.filter(e => e.source === selected.id || e.target === selected.id).map((e, i) => (
                  <div key={i}>
                    {e.source === selected.id ? '→' : '←'} {e.relation}: {e.source === selected.id ? e.target : e.source}
                  </div>
                ))}
                {edges.filter(e => e.source === selected.id || e.target === selected.id).length === 0 && (
                  <span>No connections</span>
                )}
              </div>
            </div>
          ) : (
            <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
              Click a node to see details.
              <div style={{ marginTop: 12 }}>
                <strong>Legend:</strong>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                  {Object.entries(typeColors).filter(([k]) => k !== 'default').map(([type, color]) => (
                    <span key={type} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11 }}>
                      <span style={{ width: 10, height: 10, borderRadius: '50%', background: color, display: 'inline-block' }} />
                      {type}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
