'use client';
import Link from 'next/link';
import { ArrowLeft, Mail } from 'lucide-react';
import { AuthFrame } from '@/components/auth-frame';

export default function ResetPasswordPage() {
  return <AuthFrame>
    <Link href="/auth/login" className="auth-back"><ArrowLeft size={15}/> Back to sign in</Link>
    <div className="auth-form-wrap">
      <span className="auth-mark"><Mail size={20}/></span>
      <div className="eyebrow">ACCOUNT RECOVERY</div>
      <h1>Password reset unavailable</h1>
      <p>An email delivery provider has not been configured, so reset instructions cannot be sent.</p>
      <div className="auth-notice" role="status">Contact your workspace administrator to recover account access.</div>
    </div>
    <div className="auth-footer">© 2026 Morrow</div>
  </AuthFrame>;
}
