import { useEffect, useRef, useState, useCallback } from 'react';

export interface WSEvent {
  type: string;
  run_id: string;
  timestamp: string;
  [key: string]: any;
}

export function useRunWebSocket(runId: string | undefined) {
  const [events, setEvents] = useState<WSEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!runId) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/runs/${runId}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);

    ws.onmessage = (e) => {
      try {
        const event: WSEvent = JSON.parse(e.data);
        if (event.type === 'pong') return;
        setEvents(prev => [...prev, event]);
      } catch {}
    };

    const pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send('ping');
      }
    }, 30000);

    return () => {
      clearInterval(pingInterval);
      ws.close();
      setEvents([]);
      setConnected(false);
    };
  }, [runId]);

  const clearEvents = useCallback(() => setEvents([]), []);

  return { events, connected, clearEvents };
}
