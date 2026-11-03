'use client';
import Link from 'next/link';
import { useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import { ArrowUpRight, Download, Search, Sparkles, SlidersHorizontal, X } from 'lucide-react';
import { PageHeading } from '@/components/ui';
import { ForecastWorkspaceChart, SalesChart } from '@/components/charts';
import { workspacePreview, workspacePreviewValues } from '@/lib/workspace-preview';
import { WorkspacePreviewSection } from '@/features/workspace/preview-sections';

const settingsSections: Record<string, { columns: string[]; rows: string[][] }> = {
  Business: { columns: ['SETTING', 'DESCRIPTION', 'PREVIEW VALUE'], rows: [['Business name', 'Name shown across this workspace', 'Sample business'], ['Time zone', 'Used for reporting and activity dates', 'Asia/Kolkata · preview'], ['Currency', 'Default currency for business views', 'USD · preview']] },
  Preferences: { columns: ['PREFERENCE', 'DESCRIPTION', 'PREVIEW VALUE'], rows: [['Date format', 'How dates appear in reports', 'DD MMM YYYY'], ['Week starts on', 'First day in weekly reports', 'Monday'], ['Default report period', 'Date range used when opening reports', 'Last 30 days']] },
  Notifications: { columns: ['NOTIFICATION', 'DESCRIPTION', 'PREVIEW VALUE'], rows: [['Critical stock alerts', 'When inventory reaches its critical threshold', 'Enabled · preview'], ['Forecast updates', 'When a new forecast is available', 'Daily · preview'], ['Delivery channel', 'Where workspace notices are delivered', 'In-app · preview']] },
  'Team & roles': { columns: ['ROLE', 'ACCESS SUMMARY', 'PREVIEW VALUE'], rows: [['Owner', 'All workspace and financial controls', '1 seat · preview'], ['Manager', 'Operations, purchases, and reports', '2 seats · preview'], ['Staff', 'Assigned operational screens', '4 seats · preview']] },
  Integrations: { columns: ['INTEGRATION', 'PURPOSE', 'STATUS'], rows: [['Accounting export', 'Share ledger reports with an accounting system', 'Not connected'], ['Payment provider', 'Accept and reconcile external payments', 'Not connected'], ['Supplier email', 'Send purchase inquiries and updates', 'Not connected']] },
  Security: { columns: ['CONTROL', 'DESCRIPTION', 'STATUS'], rows: [['Multi-factor authentication', 'Additional sign-in verification', 'Not configured'], ['Session duration', 'How long a signed-in session remains active', '30 minutes · preview'], ['Audit history', 'Retain a reviewable record of workspace actions', 'Available in API mode']] },
};

export default function WorkspacePage() {
  const params = useParams<{ section: string }>();
  const key = params.section;
  const page = workspacePreview[key];
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState('All');
  const [settingsSection, setSettingsSection] = useState('Business');
  const [selectedRecord, setSelectedRecord] = useState<string[] | null>(null);
  const settingsView = key === 'settings' ? settingsSections[settingsSection] : undefined;
  const columns = settingsView?.columns ?? page?.columns ?? [];
  const sourceRows = settingsView?.rows ?? page?.rows ?? [];
  const rows = useMemo(() => sourceRows.filter(row =>
    row.join(' ').toLowerCase().includes(query.toLowerCase())
    && (selected === 'All' || row.some(cell => cell.toLowerCase().includes(selected.toLowerCase()))),
  ), [sourceRows, query, selected]);

  if (!page) return <section className="panel not-found-panel"><div className="eyebrow">PAGE NOT FOUND</div><h1>This page isn’t in the workspace.</h1><p>Choose a destination from the navigation or return to your command center.</p><Link className="button button-primary" href="/">Go to dashboard <ArrowUpRight size={15}/></Link></section>;
  const values = workspacePreviewValues[key] ?? ['—', '—', '—'];
  const ai = page.kind === 'ai';

  return <>
    <PageHeading eyebrow={page.eyebrow} title={page.title} description={page.description} action={ai ? <span className="ai-chip"><Sparkles size={13}/> AI workspace</span> : undefined}/>
    <div className="workspace-summary">{page.statLabels.map((label, index) => <article className="panel workspace-stat" key={label}><span>{label}</span><strong>{values[index]}</strong><small>Visual preview</small></article>)}</div>
    {page.insight && <div className={`workspace-note ${page.kind === 'risk' ? 'note-risk' : 'note-ai'}`}><span>{ai ? <Sparkles size={15}/> : page.kind === 'risk' ? '!' : 'i'}</span><p>{page.insight}</p></div>}
    {key === 'forecasting' && <section className="panel workspace-visualization"><div className="panel-heading"><div><div className="section-kicker">PREDICTION · PREVIEW DATA</div><h2>Historical demand and outlook</h2><p>The dashed blue series is illustrative; the shaded area shows an example uncertainty range.</p></div><span className="preview-period">Next 7 days · preview</span></div><ForecastWorkspaceChart/></section>}
    {(key === 'expenses' || key === 'profit-loss') && <section className="panel workspace-visualization"><div className="panel-heading"><div><div className="section-kicker">PERFORMANCE · PREVIEW DATA</div><h2>{key === 'expenses' ? 'Expense trend' : 'Revenue trend'}</h2><p>Illustrative sample values for visual development.</p></div></div><SalesChart kind={key === 'expenses' ? 'bar' : 'area'} metric={key === 'expenses' ? 'expenses' : 'sales'}/></section>}
    <WorkspacePreviewSection section={key} page={page}/>
    {key === 'settings' && <div className="settings-tabs" role="tablist" aria-label="Settings areas">{Object.keys(settingsSections).map((section, index, sections) => <button key={section} id={`settings-tab-${section.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`} type="button" role="tab" aria-controls="settings-preview-panel" aria-selected={settingsSection === section} tabIndex={settingsSection === section ? 0 : -1} className={settingsSection === section ? 'selected' : ''} onClick={() => { setSettingsSection(section); setQuery(''); setSelected('All'); }} onKeyDown={event => { const nextIndex = event.key === 'ArrowRight' ? (index + 1) % sections.length : event.key === 'ArrowLeft' ? (index - 1 + sections.length) % sections.length : event.key === 'Home' ? 0 : event.key === 'End' ? sections.length - 1 : -1; if (nextIndex >= 0) { event.preventDefault(); const next = sections[nextIndex]; setSettingsSection(next); event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[nextIndex]?.focus(); } }}>{section}</button>)}</div>}
    {key === 'voice-assistant' && <div className="voice-preview panel"><span className="voice-orb"><span/></span><div className="eyebrow">VOICE CAPTURE OFF</div><h2>Ask your business a question.</h2><p>Voice interactions will be available once a speech provider and privacy settings are configured.</p><button className="button button-secondary" disabled>Microphone unavailable</button></div>}
    <section id={key === 'settings' ? 'settings-preview-panel' : undefined} role={key === 'settings' ? 'tabpanel' : undefined} aria-labelledby={key === 'settings' ? `settings-tab-${settingsSection.toLowerCase().replace(/[^a-z0-9]+/g, '-')}` : undefined} className="panel workspace-table-panel"><div className="workspace-toolbar"><div><div className="section-kicker">{key === 'settings' ? settingsSection.toUpperCase() : 'OVERVIEW'}</div><h2>{key === 'settings' ? settingsSection : key === 'audit-log' ? 'Recent events' : key === 'notifications' ? 'Recent updates' : 'Recent records'}</h2></div><div className="workspace-tools"><label className="search-field"><Search size={15}/><input placeholder="Search this view..." aria-label={`Search ${page.title}`} value={query} onChange={event => setQuery(event.target.value)}/></label>{key !== 'settings' && key !== 'voice-assistant' && <label className="workspace-filter"><SlidersHorizontal size={14}/><select aria-label="Filter table" value={selected} onChange={event => setSelected(event.target.value)}><option>All</option><option>Open</option><option>Active</option><option>High</option><option>Review</option></select></label>}<button className="icon-button export-icon" aria-label="Export unavailable in preview" title="Export is not connected" disabled><Download size={15}/></button></div></div>
      {rows.length ? <div className="table-scroll"><table><thead><tr>{columns.map((column, index) => <th key={`${column}-${index}`}>{column}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={rowIndex} tabIndex={0} role="button" aria-label={`View ${page.title} record ${row[0]}`} className="clickable-row" onClick={() => setSelectedRecord(row)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedRecord(row); } }}>{row.map((cell, cellIndex) => <td key={`${rowIndex}-${cellIndex}`} className={cellIndex === 0 ? 'strong-cell' : ''}>{cellIndex === row.length - 1 && /^(High|Medium|Watch|Review|Open|New|Suggested|Active|Paid|Completed|In transit|Confirmed|Ready|Preparing|Low stock|Unread|Read|Resolved|Not connected|Not configured)$/.test(cell) ? <span className={`status-pill ${/High|Watch|Review|Open|New|Low stock|Not connected|Not configured/.test(cell) ? 'pending' : 'completed'}`}>{cell}</span> : cell}</td>)}</tr>)}</tbody></table></div> : <div className="state-box">No matching preview records.</div>}
      <div className="table-footer"><span>Preview data · {rows.length} records shown</span>{key === 'settings' ? <button className="button button-secondary button-small" disabled title="Saving settings is not connected">Save unavailable</button> : <Link href="/settings" className="mini-link">Data connections <ArrowUpRight size={13}/></Link>}</div>
    </section><p className="sample-disclaimer">Design preview · Values and records are illustrative. This page does not make changes to business data.</p>
    {selectedRecord && <div className="modal-scrim" onClick={() => setSelectedRecord(null)}><section className="receipt-modal detail-modal workspace-record-dialog" role="dialog" aria-modal="true" aria-labelledby="workspace-record-title" onClick={event => event.stopPropagation()}><button className="modal-close" onClick={() => setSelectedRecord(null)} aria-label="Close record details"><X size={18}/></button><div className="eyebrow">{page.eyebrow} · PREVIEW RECORD</div><h2 id="workspace-record-title">{selectedRecord[0]}</h2><div className="detail-rule"/>{columns.map((column, index) => <div className="receipt-item" key={`${column}-${index}`}><span>{column}</span><strong>{selectedRecord[index] ?? '—'}</strong></div>)}<p className="sample-disclaimer">Illustrative detail only. No business record was changed.</p></section></div>}
  </>;
}
