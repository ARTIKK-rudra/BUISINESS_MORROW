'use client';
import { useEffect, useState } from 'react';
import { AlertCircle, LoaderCircle } from 'lucide-react';

export function useResource<T>(load: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null); const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [attempt, setAttempt] = useState(0);
  useEffect(() => { let active = true; setLoading(true); setError(''); load().then(value => { if (active) setData(value); }).catch(e => { if (active) setError(e instanceof Error ? e.message : 'Something went wrong.'); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, attempt]);
  return { data, loading, error, retry: () => setAttempt(n => n + 1) };
}
export function AsyncState({ loading, error, empty, retry, children }: { loading: boolean; error: string; empty: boolean; retry: () => void; children: React.ReactNode }) {
  if (loading) return <div className="state-box" role="status"><LoaderCircle className="spin" size={19}/> Loading your data…</div>;
  if (error) return <div className="state-box error-state" role="alert"><AlertCircle size={19}/><span>{error}</span><button className="button button-small" onClick={retry}>Retry</button></div>;
  if (empty) return <div className="state-box">Nothing to show yet.</div>;
  return <>{children}</>;
}
