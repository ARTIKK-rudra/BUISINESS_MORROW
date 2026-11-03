'use client';
import { useEffect, useState } from 'react';
import { Bell, Volume2, VolumeX } from 'lucide-react';
import { PageHeading } from '@/components/ui';
import { AsyncState, useResource } from '@/components/async-state';
import { api } from '@/lib/api';

export default function NotificationsPage() {
  const resource = useResource(api.notifications);
  const [enabled, setEnabled] = useState(false);
  const [permission, setPermission] = useState<NotificationPermission | 'unsupported'>('default');
  useEffect(() => { setEnabled(localStorage.getItem('morrow-voice-notifications') === 'enabled'); }, []);
  useEffect(() => { setPermission('Notification' in window ? Notification.permission : 'unsupported'); }, []);
  useEffect(() => {
    const refresh = () => resource.retry();
    window.addEventListener('morrow-business-event', refresh);
    return () => window.removeEventListener('morrow-business-event', refresh);
  }, [resource.retry]);
  async function toggle() {
    let next = !enabled;
    if (next && 'Notification' in window && Notification.permission === 'default') {
      const result = await Notification.requestPermission();
      setPermission(result);
      if (result === 'denied') next = false;
    }
    setEnabled(next);
    localStorage.setItem('morrow-voice-notifications', next ? 'enabled' : 'disabled');
    if (next && 'speechSynthesis' in window) window.speechSynthesis.speak(new SpeechSynthesisUtterance('Business alerts enabled.'));
  }
  return <><PageHeading eyebrow="BUSINESS ALERTS" title="Notifications" description="Follow important changes across your business while you work." action={<button className="button button-secondary" onClick={toggle}>{enabled ? <VolumeX size={15}/> : <Volume2 size={15}/>} Browser and voice alerts {enabled ? 'on' : 'off'}</button>}/><div className="panel state-box" style={{ marginBottom: 16, textAlign: 'left' }}><Bell size={17}/><span>With permission, new business events appear as browser notifications. Stock, purchase, sale, refund, and critical anomaly alerts can also be spoken while this workspace is open. Browser permission: {permission}. Calls and SMS delivery are not connected; this preview stores no recipient phone number. Customer and payment details are never spoken.</span></div>{!resource.error && resource.data && <div className="preview-banner" role="note">{resource.data.some(row => row.id.startsWith('preview-')) ? 'Illustrative notification records · live updates require the connected API.' : 'Notifications from this business workspace.'}</div>}<div className="panel data-panel"><AsyncState loading={resource.loading} error={resource.error} empty={!resource.data?.length} retry={resource.retry}><div className="table-scroll"><table><thead><tr><th>ALERT</th><th>DETAIL</th><th>CHANNEL</th><th>STATUS</th><th>TIME</th></tr></thead><tbody>{resource.data?.map(row => <tr key={row.id}><td className="strong-cell">{row.title}</td><td>{row.body}</td><td>{row.channel.replaceAll('_', ' ')}</td><td><span className={`status-pill ${row.status === 'Unread' ? 'pending' : 'completed'}`}>{row.status}</span></td><td>{new Date(row.created_at).toLocaleString()}</td></tr>)}</tbody></table></div></AsyncState></div></>;
}
