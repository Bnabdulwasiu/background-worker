import { useEffect, useRef, useState } from 'react';

/**
 * Hook that connects to the SSE endpoint and provides live job updates
 * and dashboard stats.
 */
export function useSSE() {
  const [stats, setStats] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);
  const sourceRef = useRef(null);

  useEffect(() => {
    const source = new EventSource('/api/events');
    sourceRef.current = source;

    source.addEventListener('dashboard_stats', (e) => {
      try {
        setStats(JSON.parse(e.data));
      } catch { /* ignore parse errors */ }
    });

    source.addEventListener('job_update', (e) => {
      try {
        const data = JSON.parse(e.data);
        setLastUpdate({ ...data, _ts: Date.now() });
      } catch { /* ignore */ }
    });

    source.onerror = () => {
      // EventSource auto-reconnects, nothing to do
    };

    return () => {
      source.close();
    };
  }, []);

  return { stats, lastUpdate };
}
