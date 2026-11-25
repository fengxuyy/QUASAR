import { useState, useCallback, useEffect, useRef } from 'react';

export interface HistoryRun {
  id: string;
  displayId: string;
  title: string;
  summary: string;
  usageReport: string | null;
  executionOverview: string | null;
  timestamp: string;
}

export function useHistory(enabled = true) {
  const [history, setHistory] = useState<HistoryRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isInitialLoad = useRef(true);

  const fetchHistory = useCallback(async () => {
    if (isInitialLoad.current) {
      setLoading(true);
    }
    try {
      const response = await fetch('/api/history');
      if (!response.ok) throw new Error('Failed to fetch history');
      const data = await response.json();
      setHistory(data);
      isInitialLoad.current = false;
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    fetchHistory();
    // Auto-refresh history every 5 seconds
    const interval = setInterval(fetchHistory, 5000);
    return () => clearInterval(interval);
  }, [enabled, fetchHistory]);

  return {
    history,
    loading,
    error,
    refreshHistory: fetchHistory
  };
}
