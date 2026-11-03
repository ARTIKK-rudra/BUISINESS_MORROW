'use client';

import { useCallback, useEffect, useState } from 'react';
import { Check, Lightbulb, RefreshCw, ShieldCheck } from 'lucide-react';
import { PageHeading } from '@/components/ui';
import { ApiError, api, hasApiSession, isDemoMode, type ApprovedPurchase, type BusinessRecommendation, type ReorderQuote } from '@/lib/api';

export default function RecommendationsPage() {
  const [rows, setRows] = useState<BusinessRecommendation[]>([]);
  const [selected, setSelected] = useState<BusinessRecommendation | null>(null);
  const [quote, setQuote] = useState<ReorderQuote | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [result, setResult] = useState<ApprovedPurchase | null>(null);
  const load = useCallback(async () => {
    if (!hasApiSession() && !isDemoMode()) { setRows([]); setLoading(false); return; }
    setLoading(true); setError('');
    try { setRows(await api.recommendations()); }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Could not load recommendations.'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  async function openReview(row: BusinessRecommendation) {
    setBusy(true); setError(''); setSelected(null); setQuote(null);
    try { setQuote(await api.previewRecommendation(row.id)); setSelected(row); }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Could not load current supplier pricing.'); }
    finally { setBusy(false); }
  }
  async function approve() {
    if (!selected || !quote) return;
    setBusy(true); setError(''); setResult(null);
    try { setResult(await api.approveRecommendation(selected.id, quote)); setSelected(null); setQuote(null); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Could not approve this purchase recommendation.'); }
    finally { setBusy(false); }
  }
  return <><PageHeading eyebrow="HUMAN APPROVAL REQUIRED" title="Recommendations" description="Review suggested actions, evidence, and supplier quotes. Financial actions remain owner-approved." action={<button className="button button-secondary" onClick={() => void load()}><RefreshCw size={14}/> Refresh</button>}/>
    {isDemoMode() && <div className="preview-banner" role="note">Illustrative recommendation records only. Supplier quotes, approvals, and purchase creation require the connected API.</div>}
    {!hasApiSession() && !isDemoMode() && <div className="panel state-box">Connect the API and sign in to view recommendations from this business.</div>}
    {loading && (hasApiSession() || isDemoMode()) && <div className="panel state-box" role="status">Loading recommendations…</div>}
    {error && <div className="assistant-error" role="alert">{error}<button className="button button-secondary" onClick={() => void load()}>Retry</button></div>}
    {result && <div className="invoice-success" role="status"><Check size={17}/> Purchase order created: {result.total} {result.currency} · {result.status}</div>}
    {!loading && (hasApiSession() || isDemoMode()) && rows.length === 0 && !error && <div className="panel state-box">No recommendations are currently stored for this business.</div>}
    <div className="recommendation-list">{rows.map(row => <article className="panel recommendation-card" key={row.id}><div className="recommendation-card-icon"><Lightbulb size={17}/></div><div className="recommendation-card-body"><div className="recommendation-card-meta"><span>{String(row.provenance?.source ?? 'business rule').replaceAll('_', ' ')}</span><span className={`status-pill ${row.status === 'pending' ? 'pending' : 'completed'}`}>{row.status}</span></div><h2>{row.summary}</h2><p>{row.rationale}</p><small>Inventory reference · {row.target_id}</small></div>{row.status === 'pending' && row.recommendation_type === 'reorder' && (isDemoMode() ? <span className="unavailable-action" title="A live quote and owner session are required">Approval available with API</span> : <button className="button button-primary" disabled={busy} onClick={() => void openReview(row)}><ShieldCheck size={14}/> Review purchase</button>)}</article>)}</div>
    {selected && quote && <div className="palette-backdrop" role="presentation" onMouseDown={e => { if (e.target === e.currentTarget && !busy) { setSelected(null); setQuote(null); } }}><section className="command-palette approval-dialog" role="dialog" aria-modal="true" aria-labelledby="approval-title"><div className="eyebrow">OWNER APPROVAL</div><h2 id="approval-title">Review purchase order</h2><p>{selected.summary}</p><dl className="approval-quote"><div><dt>Item</dt><dd>{quote.item_name}</dd></div><div><dt>Quantity</dt><dd>{quote.quantity} {quote.unit}</dd></div><div><dt>Supplier</dt><dd>{quote.supplier_name}</dd></div><div><dt>Recommended date</dt><dd>{quote.recommended_date ?? 'As soon as practical'}</dd></div><div><dt>Unit cost</dt><dd>{quote.unit_cost} {quote.currency}</dd></div><div><dt>Estimated total</dt><dd>{quote.estimated_total} {quote.currency}</dd></div></dl><p className="approval-detail">Approval rechecks stock, supplier pricing, and lead time. If the quote changed, regenerate the recommendation. Inventory changes only when goods are received.</p><p className="approval-detail">Only a business owner can approve. This creates a purchase commitment and is recorded in the audit log.</p>{error && <div className="assistant-error" role="alert">{error}</div>}<div className="invoice-actions"><button className="button button-secondary" disabled={busy} onClick={() => { setSelected(null); setQuote(null); }}>Cancel</button><button className="button button-primary" disabled={busy} onClick={() => void approve()}>{busy ? 'Creating purchase…' : 'Approve and create purchase'}</button></div></section></div>}
  </>;
}
