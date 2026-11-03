'use client';

import { useEffect, useMemo, useState } from 'react';
import { Mic, Play, ShieldCheck, Volume2 } from 'lucide-react';
import { PageHeading } from '@/components/ui';
import { api, ApiError, type ProvisionCase, type VoiceContact } from '@/lib/api';

type ProvisionRecognition = {
  lang: string;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: (() => void) | null;
  start(): void;
};
type ProvisionRecognitionConstructor = new () => ProvisionRecognition;

function speak(text: string) { if ('speechSynthesis' in window) { window.speechSynthesis.cancel(); window.speechSynthesis.speak(new SpeechSynthesisUtterance(text)); } }

export default function ProvisionPage() {
  const [caseData, setCaseData] = useState<ProvisionCase | null>(null);
  const [contacts, setContacts] = useState<VoiceContact[]>([]);
  const [transcript, setTranscript] = useState(''); const [price, setPrice] = useState('10'); const [deliveryDays, setDeliveryDays] = useState('1');
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  useEffect(() => { void Promise.all([api.provisionCases(), api.voiceContacts()]).then(([cases, configuredContacts]) => { setCaseData(cases[0] ?? null); setContacts(configuredContacts); }).catch(reason => setError(reason instanceof Error ? reason.message : 'Could not load provision workflow.')); }, []);
  const items = caseData?.shortage_snapshot.items ?? [];
  const managers = contacts.filter(contact => contact.role === 'manager' && contact.is_active);
  const responseSummary = useMemo(() => caseData ? `Workflow status: ${caseData.status.replaceAll('_', ' ')}.` : '', [caseData]);
  async function perform(action: () => Promise<ProvisionCase>) { setBusy(true); setError(''); try { const result = await action(); setCaseData(result); speak(`Recorded. ${result.status.replaceAll('_', ' ')}.`); } catch (reason) { setError(reason instanceof ApiError ? reason.message : 'The workflow could not be updated.'); } finally { setBusy(false); } }
  function dictate() {
    const browser = window as unknown as { SpeechRecognition?: ProvisionRecognitionConstructor; webkitSpeechRecognition?: ProvisionRecognitionConstructor };
    const Constructor = browser.SpeechRecognition || browser.webkitSpeechRecognition;
    if (!Constructor) { setError('Speech recognition is unavailable in this browser. Type the response instead.'); return; }
    const recognition = new Constructor(); recognition.lang = navigator.language || 'en-US';
    recognition.onresult = event => setTranscript(event.results[0]?.[0]?.transcript ?? '');
    recognition.onerror = () => setError('Speech recognition stopped. Type the response instead.');
    recognition.start();
  }
  const quantities = items.map(item => ({ inventory_id: item.inventory_id, quantity: item.replenishment_required ?? item.shortage_to_minimum }));
  return <><PageHeading eyebrow="LOCAL-ONLY PROCUREMENT" title="Provision agent" description="Browser speech and text simulation. No phone call, payment, or supplier message is sent."/><section className="panel provision-panel"><div className="provision-intro"><div><div className="eyebrow">₹0 LOCAL DEMO</div><h2>Multi-stakeholder replenishment workflow</h2><p>Use browser speech recognition or text. Gemini is optional; deterministic workflow rules remain available offline.</p></div><button className="button button-secondary" disabled={busy} onClick={dictate}><Mic size={15}/> Dictate response</button></div>{!caseData && <button className="button button-primary" disabled={busy} onClick={() => void perform(() => api.startProvisionCase(true))}><Play size={15}/> Start labeled demo</button>}{caseData && <><div className="provision-stage"><strong>{caseData.demo_mode ? 'DEMONSTRATION DATA' : 'LIVE DATABASE SHORTAGE'}</strong><span>{responseSummary}</span></div><p className="provision-impact">{caseData.shortage_snapshot.pending_order_count} pending orders assessed · {caseData.shortage_snapshot.affected_order_count ?? 0} currently affected</p><div className="provision-items">{items.map(item => <article key={item.inventory_id}><strong>{item.name}</strong><span>{item.replenishment_required ?? item.shortage_to_minimum} {item.unit} to replenish</span>{item.pending_demand && <small>{item.pending_demand} {item.unit} committed to pending orders · {item.committed_inbound ?? '0'} inbound</small>}</article>)}</div>{caseData.shortage_snapshot.data_quality_issues?.length ? <div className="assistant-error" role="status">Manager review needed: {caseData.shortage_snapshot.data_quality_issues.map(issue => issue.message).join(' ')}</div> : null}<label className="voice-typed-form"><span>Conversation response</span><div><input value={transcript} onChange={event => setTranscript(event.target.value)} placeholder="Say or type the stakeholder response"/><button type="button" className="button button-secondary" onClick={() => speak(transcript)}><Volume2 size={15}/> Speak</button></div></label>{caseData.status === 'awaiting_owner_authorization' && <button className="button button-primary" disabled={busy || !transcript.trim()} onClick={() => void perform(() => api.ownerProvisionDecision(caseData.id, transcript))}><ShieldCheck size={15}/> Record owner supplier-contact decision</button>}{caseData.status === 'awaiting_manager_quantities' && <div className="provision-actions">{managers.map(manager => <button key={manager.id} className="button button-secondary" disabled={busy || !transcript.trim()} onClick={() => void perform(() => api.managerProvisionResponse(caseData.id, manager.id, transcript, quantities))}>Record {manager.full_name}&apos;s quantities</button>)}</div>}{caseData.status === 'awaiting_owner_conflict_resolution' && <button className="button button-primary" disabled={busy || !transcript.trim()} onClick={() => void perform(() => api.resolveProvisionConflict(caseData.id, transcript, quantities))}>Record owner quantity resolution</button>}{caseData.status === 'awaiting_supplier_quotation' && <div className="provision-quote"><label>Unit cost<input value={price} onChange={event => setPrice(event.target.value)} inputMode="decimal"/></label><label>Delivery days<input value={deliveryDays} onChange={event => setDeliveryDays(event.target.value)} inputMode="numeric"/></label><button className="button button-primary" disabled={busy || !transcript.trim()} onClick={() => void perform(() => api.supplierProvisionResponse(caseData.id, transcript, 'USD', Number(deliveryDays), items.map(item => ({ inventory_id: item.inventory_id, available_quantity: item.replenishment_required ?? item.shortage_to_minimum, unit_cost: price }))))}>Record simulated supplier quote</button></div>}{caseData.status === 'awaiting_owner_purchase_approval' && <div className="provision-actions"><button className="button button-primary" disabled={busy || !transcript.trim()} onClick={() => void perform(() => api.purchaseProvisionDecision(caseData.id, true, transcript))}>Approve exact terms</button><button className="button button-secondary" disabled={busy || !transcript.trim()} onClick={() => void perform(() => api.purchaseProvisionDecision(caseData.id, false, transcript))}>Decline terms</button></div>}{caseData.purchase_id && <p className="invoice-success">Purchase order recorded: {caseData.purchase_id}. Goods are not received automatically.</p>}</>}{error && <p className="assistant-error" role="alert">{error}</p>}</section></>;
}
