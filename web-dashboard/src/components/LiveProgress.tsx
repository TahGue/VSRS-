import { WSEvent } from '../useWebSocket';

const stateOrder = [
  'intake',
  'retrieving',
  'reasoning',
  'patching',
  'verifying',
  'revising',
  'reviewing',
  'verified',
  'rejected',
  'failed',
];

const stateLabels: Record<string, string> = {
  intake: 'Intake',
  retrieving: 'Retrieving Evidence',
  reasoning: 'Reasoning',
  patching: 'Generating Patch',
  verifying: 'Verifying',
  revising: 'Repairing',
  reviewing: 'Reviewing',
  verified: 'Verified',
  rejected: 'Rejected',
  failed: 'Failed',
};

const eventIcons: Record<string, string> = {
  state_change: '→',
  tool_call: '⚙',
  verification_result: '✓',
  patch_generated: '⚡',
  review_complete: '👁',
  run_complete: '●',
};

export default function LiveProgress({
  events,
  connected,
}: {
  events: WSEvent[];
  connected: boolean;
}) {
  const currentState = events
    .filter(e => e.type === 'state_change')
    .pop()?.to_state || 'intake';

  const isComplete = ['verified', 'rejected', 'failed'].includes(currentState);
  const currentIdx = stateOrder.indexOf(currentState);

  return (
    <div className="card">
      <h2 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        Live Progress
        <span
          className={`badge ${connected ? 'badge-success' : 'badge-neutral'}`}
          style={{ fontSize: 11 }}
        >
          {connected ? 'Connected' : 'Disconnected'}
        </span>
      </h2>

      {/* Pipeline stage indicator */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 20, overflowX: 'auto' }}>
        {stateOrder.slice(0, 7).map((state, i) => {
          const isDone = i < currentIdx;
          const isCurrent = i === currentIdx && !isComplete;
          const isFailed = currentState === 'failed' && i === currentIdx;
          return (
            <div
              key={state}
              style={{
                flex: 1,
                textAlign: 'center',
                position: 'relative',
                padding: '8px 4px',
              }}
            >
              <div
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: '50%',
                  margin: '0 auto 6px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 12,
                  fontWeight: 700,
                  background: isFailed
                    ? 'var(--danger)'
                    : isCurrent
                    ? 'var(--primary)'
                    : isDone
                    ? 'var(--success)'
                    : 'var(--border)',
                  color: isDone || isCurrent || isFailed ? 'white' : 'var(--text-muted)',
                }}
              >
                {isDone ? '✓' : i + 1}
              </div>
              <div
                style={{
                  fontSize: 10,
                  color: isCurrent ? 'var(--primary)' : isFailed ? 'var(--danger)' : 'var(--text-muted)',
                  whiteSpace: 'nowrap',
                }}
              >
                {stateLabels[state]}
              </div>
              {i < 6 && (
                <div
                  style={{
                    position: 'absolute',
                    top: 14,
                    right: -2,
                    width: 4,
                    height: 2,
                    background: isDone ? 'var(--success)' : 'var(--border)',
                  }}
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Event feed */}
      <div style={{ maxHeight: 300, overflowY: 'auto' }}>
        {events.length === 0 && (
          <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: 12 }}>
            Waiting for events...
          </div>
        )}
        {events.map((event, i) => (
          <div
            key={i}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 10,
              padding: '6px 0',
              borderBottom: i < events.length - 1 ? '1px solid var(--border)' : 'none',
              fontSize: 13,
            }}
          >
            <span style={{ color: 'var(--text-muted)', fontSize: 16, minWidth: 20 }}>
              {eventIcons[event.type] || '•'}
            </span>
            <div style={{ flex: 1 }}>
              <EventContent event={event} />
              <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                {new Date(event.timestamp).toLocaleTimeString()}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function EventContent({ event }: { event: WSEvent }) {
  switch (event.type) {
    case 'state_change':
      return (
        <div>
          State: <strong>{event.from_state}</strong> → <strong>{event.to_state}</strong>
          {event.attempt_no > 1 && (
            <span style={{ color: 'var(--warning)', marginLeft: 6 }}>
              (attempt {event.attempt_no})
            </span>
          )}
        </div>
      );
    case 'tool_call':
      return (
        <div>
          Tool: <strong>{event.tool}</strong>
          {event.status === 'running' ? (
            <span style={{ color: 'var(--warning)', marginLeft: 6 }}>running...</span>
          ) : (
            <span
              style={{
                color: event.exit_code === 0 ? 'var(--success)' : 'var(--danger)',
                marginLeft: 6,
              }}
            >
              exit {event.exit_code} ({event.duration_seconds?.toFixed(2)}s)
            </span>
          )}
        </div>
      );
    case 'verification_result':
      return (
        <div>
          Check: <strong>{event.check_type}</strong>{' '}
          <span
            className={`badge ${event.passed ? 'badge-success' : 'badge-danger'}`}
            style={{ fontSize: 10 }}
          >
            {event.passed ? 'PASS' : 'FAIL'}
          </span>
          {event.duration_seconds > 0 && (
            <span style={{ color: 'var(--text-muted)', marginLeft: 6 }}>
              {event.duration_seconds.toFixed(2)}s
            </span>
          )}
          {event.error_message && (
            <pre className="check-error" style={{ marginTop: 4 }}>{event.error_message}</pre>
          )}
        </div>
      );
    case 'patch_generated':
      return (
        <div>
          Patch (attempt {event.attempt_no}): {event.changed_files?.join(', ')}
        </div>
      );
    case 'review_complete':
      return (
        <div>
          Review: <strong>{event.decision}</strong>
          {event.findings_count > 0 && (
            <span style={{ color: 'var(--text-muted)', marginLeft: 6 }}>
              {event.findings_count} findings
            </span>
          )}
          {event.blockers?.length > 0 && (
            <div style={{ color: 'var(--danger)', marginTop: 4 }}>
              Blockers: {event.blockers.join(', ')}
            </div>
          )}
        </div>
      );
    case 'run_complete':
      return (
        <div>
          Run complete: <strong>{event.final_state}</strong> ({event.attempts} attempts)
        </div>
      );
    default:
      return <div>{event.type}</div>;
  }
}
