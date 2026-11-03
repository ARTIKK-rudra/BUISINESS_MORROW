'use client';
import Link from 'next/link';
import { useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import { AuthFrame } from '@/components/auth-frame';
import { api } from '@/lib/api';

export default function RegisterPage() {
  const [form, setForm] = useState({ name: '', email: '', password: '', business_name: 'Local Development Restaurant (Voice Agent)' });
  const [error, setError] = useState(''); const [done, setDone] = useState(false); const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try { await api.register(form); setDone(true); }
    catch (x) { setError(x instanceof Error ? x.message : 'Could not create account.'); }
    finally { setBusy(false); }
  }
  return <AuthFrame><Link href="/auth/login" className="auth-back"><ArrowLeft size={15}/> Back to sign in</Link><div className="auth-form-wrap"><div className="eyebrow">GET STARTED</div><h1>Your business, in good shape.</h1><p>Create a workspace to get started. The workspace creator becomes its owner.</p>{done ? <div className="auth-notice">{process.env.NEXT_PUBLIC_DATA_MODE === 'http' ? 'Your account and workspace are ready.' : 'Demo workspace request accepted. No account was created.'}<Link href="/auth/login">Go to sign in →</Link></div> : <form className="auth-form" onSubmit={submit}><label>Your name<input required autoComplete="name" placeholder="Jordan Davis" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}/></label><label>Restaurant or workspace name<input required maxLength={160} autoComplete="organization" value={form.business_name} onChange={e => setForm({ ...form, business_name: e.target.value })}/></label><label>Work email<input required type="email" autoComplete="email" placeholder="you@business.com" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })}/></label><label>Password<input required minLength={12} type="password" autoComplete="new-password" placeholder="At least 12 characters" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })}/></label>{error && <div className="form-error" role="alert">{error}</div>}<button className="button button-primary auth-submit" disabled={busy}>{busy ? 'Creating workspace…' : 'Create account'}</button><div className="auth-switch">Already have an account? <Link href="/auth/login">Sign in</Link></div></form>}</div><div className="auth-footer">© 2026 Morrow · Built for better business days</div></AuthFrame>;
}
