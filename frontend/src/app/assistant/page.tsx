'use client';
import { FormEvent, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { ArrowUpRight, MessageCircle, Send, Sparkles } from 'lucide-react';
import { PageHeading } from '@/components/ui';
import { api, ApiError, type AssistantResponse } from '@/lib/api';

const examples = ['What caused profit to decrease?', 'What should I order tomorrow?', 'Which items are at stock-out risk?', 'Show unusual refunds.', 'How did sales compare with last week?'];
export default function AssistantPage() {
  const router = useRouter(); const pathname = usePathname();
  const [question, setQuestion] = useState(''); const [answer, setAnswer] = useState<AssistantResponse | null>(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [history, setHistory] = useState<string[]>([]);
  async function ask(event?: FormEvent, text = question) { event?.preventDefault(); if (!text.trim() || busy) return; setBusy(true); setError(''); setAnswer(null); try { const result = await api.askAssistant(text.trim(), pathname, history); setAnswer(result); setHistory(previous => [...previous, text.trim()].slice(-6)); if (result.navigation_path) router.push(result.navigation_path); } catch (e) { setError(e instanceof ApiError ? e.message : 'Could not retrieve business data. Try again.'); } finally { setBusy(false); } }
  return <><PageHeading eyebrow="GROUNDED BUSINESS ANSWERS" title="Business assistant" description="Ask questions about your actual sales, inventory, forecasts, and ledger records." action={<span className="ai-chip"><Sparkles size={13}/> Data connected answers</span>}/>
    <section className="panel assistant-panel"><div className="assistant-intro"><span className="assistant-icon"><MessageCircle size={18}/></span><div><h2>What would you like to understand?</h2><p>Answers use your business records. If a forecast or anomaly record is missing, the assistant says so instead of estimating.</p></div></div>
      <div className="assistant-prompts">{examples.map(item => <button type="button" key={item} onClick={() => { setQuestion(item); void ask(undefined, item); }}>{item}<ArrowUpRight size={13}/></button>)}</div>
      <form className="assistant-form" onSubmit={ask}><label className="sr-only" htmlFor="assistant-question">Ask about your business</label><textarea id="assistant-question" value={question} onChange={e => setQuestion(e.target.value)} placeholder="Ask about your business data…" rows={3} maxLength={1000}/><div className="assistant-form-footer"><span>Read-only · No transactions are executed by the assistant</span><button className="button button-primary" disabled={busy || !question.trim()}>{busy ? 'Checking records…' : 'Ask'} <Send size={14}/></button></div></form>
      {busy && <div className="state-box" role="status">Reading the relevant business records…</div>}{error && <div className="assistant-error" role="alert"><span>{error}</span><button className="button button-secondary" onClick={() => void ask()}>Retry</button></div>}
      {answer && <article className="assistant-answer" aria-live="polite"><div className="assistant-answer-label"><Sparkles size={14}/> ANSWER <span>{new Date(answer.generated_at).toLocaleString()}</span></div><p>{answer.answer}</p>{answer.sources.length > 0 && <div className="assistant-sources"><strong>Records checked</strong>{answer.sources.map(source => <span key={source}>{source}</span>)}</div>}</article>}
      <p className="assistant-capability-note">This assistant explains verified website modules, supports allowed page navigation, and uses tenant-scoped query templates for live business information. Unsupported questions are identified explicitly.</p>
    </section>
  </>;
}
