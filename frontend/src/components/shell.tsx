'use client';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Activity, Bell, LayoutDashboard, Package, Menu, Search, ShoppingBag, ShoppingCart, Truck, X, ChartNoAxesCombined, ClipboardList, Boxes, ReceiptText, BookOpenText, ChartPie, Sparkles, TriangleAlert, Lightbulb, Mic2, Users, UserRoundCog, FileBarChart, Settings2, ScrollText, Moon, Sun, Command, ArrowUpRight, MessageCircle, FileScan, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { hasApiSession, streamBusinessEvents, type BusinessEventMessage } from '@/lib/api';

function LiveEventFeed() {
  const [events, setEvents] = useState<BusinessEventMessage[]>([]);
  const [connected, setConnected] = useState(false);
  const spokenEvents = useMemo(() => new Set<string>(), []);
  useEffect(() => {
    let stopped = false;
    let cursor: string | undefined;
    let controller: AbortController | undefined;
    const connect = async () => {
      while (!stopped) {
        if (!hasApiSession()) {
          setConnected(false);
          await new Promise(resolve => window.addEventListener('morrow-auth-changed', resolve, { once: true }));
          continue;
        }
        controller = new AbortController();
        try {
          setConnected(true);
          await streamBusinessEvents((event, nextCursor) => {
            cursor = nextCursor;
            setEvents(previous => [event, ...previous].slice(0, 4));
            window.dispatchEvent(new CustomEvent('morrow-business-event', { detail: event }));
            const criticalAnomaly = event.event_type === 'ANOMALY_DETECTED' && event.payload.severity === 'critical';
            const voiceWorthy = ['STOCK_LOW', 'STOCK_CRITICAL', 'STOCK_OUT_OF_STOCK', 'REORDER_RECOMMENDED', 'PURCHASE_CREATED', 'SALE_CREATED', 'REFUND_CREATED'].includes(event.event_type) || criticalAnomaly;
            const summary = typeof event.payload.summary === 'string' ? event.payload.summary : event.event_type.replaceAll('_', ' ').toLowerCase();
            const alertsEnabled = localStorage.getItem('morrow-voice-notifications') === 'enabled';
            if (alertsEnabled && !spokenEvents.has(event.event_id)) {
              spokenEvents.add(event.event_id);
              if ('Notification' in window && Notification.permission === 'granted') {
                new Notification(`Morrow · ${event.event_type.replaceAll('_', ' ').toLowerCase()}`, { body: summary.slice(0, 220), tag: event.event_id });
              }
              if (voiceWorthy && 'speechSynthesis' in window) window.speechSynthesis.speak(new SpeechSynthesisUtterance(summary.slice(0, 220)));
            }
          }, controller.signal, cursor);
        } catch {
          if (!stopped) setConnected(false);
        }
        if (!stopped) await new Promise(resolve => window.setTimeout(resolve, 1500));
      }
    };
    void connect();
    return () => { stopped = true; controller?.abort(); };
  }, []);
  if (!hasApiSession()) return null;
  const latest = events[0];
  const amount = typeof latest?.payload.total === 'string' ? latest.payload.total : null;
  const currency = typeof latest?.payload.currency === 'string' ? latest.payload.currency : '';
  return <div className="live-event-feed" aria-live="polite" aria-label="Live business events">
    <span className={`live-event-state ${connected ? 'is-connected' : ''}`}><i/>{connected ? 'LIVE' : 'RECONNECTING'}</span>
    {latest && <span className="live-event-message"><strong>{latest.event_type.replaceAll('_', ' ')}</strong>
      {amount ? ` · ${amount} ${currency}` : ''}</span>}
  </div>;
}

export const navGroups = [
  { label: 'COMMAND', links: [{ href: '/', name: 'Dashboard', icon: LayoutDashboard }] },
  { label: 'COMMERCE', links: [{ href: '/sales', name: 'Sales', icon: ShoppingBag }, { href: '/pos', name: 'Point of sale', icon: ShoppingCart }, { href: '/orders', name: 'Orders', icon: ClipboardList }, { href: '/customers', name: 'Customers', icon: Users }] },
  { label: 'OPERATIONS', links: [{ href: '/inventory', name: 'Inventory', icon: Package }, { href: '/products', name: 'Products', icon: Boxes }, { href: '/suppliers', name: 'Suppliers', icon: Truck }, { href: '/purchases', name: 'Purchases', icon: ShoppingBag }, { href: '/invoices', name: 'Invoice capture', icon: FileScan }, { href: '/expenses', name: 'Expenses', icon: ReceiptText }, { href: '/employees', name: 'Employees', icon: UserRoundCog }] },
  { label: 'FINANCE', links: [{ href: '/ledger', name: 'Ledger', icon: BookOpenText }, { href: '/profit-loss', name: 'Profit & loss', icon: ChartPie }, { href: '/reports', name: 'Reports', icon: FileBarChart }] },
  { label: 'INTELLIGENCE', links: [{ href: '/assistant', name: 'Business assistant', icon: MessageCircle }, { href: '/forecasting', name: 'Forecasting', icon: ChartNoAxesCombined }, { href: '/ai-insights', name: 'AI insights', icon: Sparkles }, { href: '/anomalies', name: 'Anomalies', icon: TriangleAlert }, { href: '/recommendations', name: 'Recommendations', icon: Lightbulb }, { href: '/voice-assistant', name: 'Voice assistant', icon: Mic2 }, { href: '/provision', name: 'Provision agent', icon: Mic2 }, { href: '/analytics', name: 'Analytics', icon: ChartNoAxesCombined }] },
  { label: 'WORKSPACE', links: [{ href: '/notifications', name: 'Notifications', icon: Bell }, { href: '/audit-log', name: 'Audit log', icon: ScrollText }, { href: '/settings', name: 'Settings', icon: Settings2 }] },
];
const allLinks = navGroups.flatMap(g => g.links);
export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname(); const router = useRouter(); const [open, setOpen] = useState(false); const [collapsed, setCollapsed] = useState(false); const [palette, setPalette] = useState(false); const [query, setQuery] = useState(''); const [activeIndex, setActiveIndex] = useState(0); const [theme, setTheme] = useState<'light' | 'dark'>('light'); const skipSidebarWrite = useRef(true); const skipThemeWrite = useRef(true);
  const filtered = useMemo(() => allLinks.filter(x => x.name.toLowerCase().includes(query.toLowerCase())), [query]);
  useEffect(() => { const savedTheme = localStorage.getItem('morrow-theme'); if (savedTheme === 'dark' || savedTheme === 'light') setTheme(savedTheme); setCollapsed(localStorage.getItem('morrow-sidebar-collapsed') === 'true'); }, []);
  useEffect(() => { if (skipSidebarWrite.current) { skipSidebarWrite.current = false; return; } localStorage.setItem('morrow-sidebar-collapsed', String(collapsed)); }, [collapsed]);
  useEffect(() => { if (skipThemeWrite.current) { skipThemeWrite.current = false; return; } document.documentElement.dataset.theme = theme; localStorage.setItem('morrow-theme', theme); }, [theme]);
  useEffect(() => { const onKey = (event: KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setPalette(true); setQuery(''); setActiveIndex(0); } if (event.key === 'Escape') { setOpen(false); setPalette(false); } }; window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey); }, []);
  if (pathname.startsWith('/auth')) return <>{children}</>;
  const current = allLinks.find(l => l.href === pathname);
  return <><a className="skip-link" href="#main-content">Skip to content</a><div className="app-shell">
    <aside className={`sidebar ${open ? 'sidebar-open' : ''} ${collapsed ? 'sidebar-collapsed' : ''}`}>
      <div className="brand-row"><Link href="/" className="brand" title="Morrow home"><span className="brand-mark"><Activity size={18}/></span><span>morrow<span className="brand-dot">.</span></span><span className="brand-edition">STUDIO</span></Link><button className="collapse-toggle" onClick={() => setCollapsed(value => !value)} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-expanded={!collapsed} aria-controls="workspace-navigation" title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>{collapsed ? <PanelLeftOpen size={16}/> : <PanelLeftClose size={16}/>}</button><button className="sidebar-close" onClick={() => setOpen(false)} aria-label="Close menu"><X size={18}/><span>CLOSE</span></button></div>
      <div className="business-switch" aria-label="Business workspace"><span className="business-avatar">M</span><span className="business-copy"><strong>Business workspace</strong><small>{process.env.NEXT_PUBLIC_DATA_MODE === 'http' ? 'API mode' : 'Sample-data preview'}</small></span></div>
      <nav id="workspace-navigation" className="side-nav" aria-label="Main navigation">{navGroups.map(group => <section className="nav-group" key={group.label}><p>{group.label}</p>{group.links.map(item => { const Icon = item.icon; const active = pathname === item.href; return <Link onClick={() => setOpen(false)} className={`nav-link ${active ? 'active' : ''}`} href={item.href} key={item.href} aria-current={active ? 'page' : undefined} aria-label={collapsed ? item.name : undefined} title={collapsed ? item.name : undefined}><Icon size={16}/><span>{item.name}</span></Link>; })}</section>)}</nav>
      <div className="sidebar-bottom"><div className="profile-button"><span className="profile-avatar">W</span><span className="business-copy"><strong>Workspace account</strong><small>Account controls unavailable</small></span></div></div>
    </aside>
    {open && <button className="scrim" onClick={() => setOpen(false)} aria-label="Close navigation"/>}
    <main className={`main-column ${collapsed ? 'main-column-expanded' : ''}`} id="main-content" tabIndex={-1}><header className="topbar"><Link href="/" className="brand topbar-brand" aria-label="Morrow home"><span className="brand-mark"><Activity size={17}/></span><span>morrow<span className="brand-dot">.</span></span></Link><div className="breadcrumbs"><span>COMMAND CENTER</span><span className="crumb-sep">/</span><strong>{current?.name ?? 'Dashboard'}</strong></div><div className="top-actions"><LiveEventFeed/><button className="search-trigger" onClick={() => { setPalette(true); setQuery(''); }} aria-label="Open command palette"><Search size={15}/><span>Jump to anything</span><kbd><Command size={10}/> K</kbd></button><button className="icon-button theme-button" onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')} aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}>{theme === 'light' ? <Moon size={17}/> : <Sun size={17}/>}</button><Link href="/notifications" className="icon-button notification-button" aria-label="Notifications"><Bell size={17}/></Link><button className="menu-toggle" onClick={() => setOpen(true)} aria-label="Open navigation"><span>MENU</span><Menu size={17}/></button></div></header><div className="page-content" key={pathname}>{process.env.NEXT_PUBLIC_DATA_MODE !== 'http' && <div className="preview-banner" role="note">Sample-data preview · Records and metrics are illustrative; no business data is changed here.</div>}{children}</div></main>
    {palette && <div className="palette-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) setPalette(false); }}><section className="command-palette" role="dialog" aria-modal="true" aria-label="Command palette"><div className="palette-search"><Search size={17}/><input autoFocus placeholder="Where would you like to go?" value={query} onChange={e => { setQuery(e.target.value); setActiveIndex(0); }} onKeyDown={e => { if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIndex(i => Math.min(i + 1, filtered.length - 1)); } if (e.key === 'ArrowUp') { e.preventDefault(); setActiveIndex(i => Math.max(0, i - 1)); } if (e.key === 'Enter' && filtered[activeIndex]) { e.preventDefault(); router.push(filtered[activeIndex].href); setPalette(false); } }}/><kbd>ESC</kbd></div><div className="palette-label">NAVIGATION</div><div className="palette-results">{filtered.map((item, index) => { const Icon = item.icon; return <Link key={item.href} href={item.href} onMouseEnter={() => setActiveIndex(index)} onClick={() => setPalette(false)} className={`palette-item ${index === activeIndex ? 'palette-active' : ''}`}><Icon size={16}/><span>{item.name}</span><kbd>↵</kbd></Link>; })}{filtered.length === 0 && <div className="palette-empty">No matching pages</div>}</div><footer><span><kbd>↑</kbd><kbd>↓</kbd> to navigate</span><span><kbd>↵</kbd> to open</span><span><kbd>ESC</kbd> to close</span></footer></section></div>}
  </div></>;
}
