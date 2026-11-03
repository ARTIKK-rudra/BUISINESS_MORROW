'use client';
import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { ArrowDownRight, ArrowUpRight, Clock3, PackageCheck, Sparkles, TrendingUp, Boxes, ChartNoAxesCombined, ShoppingBag, Wallet, ReceiptText, ChevronDown, ChevronUp, ChevronLeft, ChevronRight, Plus, Minus, UtensilsCrossed, ShoppingBasket, Trash2 } from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Line, ComposedChart } from 'recharts';
import { PageHeading } from '@/components/ui';
import { SalesChart } from '@/components/charts';
import { dashboardPeriods, forecastSeries, dashboardActivity, dashboardMetrics, inventoryHealth, dashboardRecommendations, dashboardAnomalies, products as demoProducts } from '@/lib/mock-data';
import { money } from '@/lib/format';
import { api, type RealtimeAnalytics } from '@/lib/api';

function LiveDashboardProjection() {
  const [projection, setProjection] = useState<RealtimeAnalytics | null>(null);
  useEffect(() => {
    let active = true;
    const refreshTimers: number[] = [];
    const refresh = () => {
      void api.realtimeAnalytics().then(value => {
        if (active && value) setProjection(value);
      }).catch(() => undefined);
    };
    const refreshAfterEvent = () => {
      refresh();
      refreshTimers.push(window.setTimeout(refresh, 600));
      refreshTimers.push(window.setTimeout(refresh, 2000));
    };
    refresh();
    window.addEventListener('morrow-business-event', refreshAfterEvent);
    return () => {
      active = false;
      refreshTimers.forEach(window.clearTimeout);
      window.removeEventListener('morrow-business-event', refreshAfterEvent);
    };
  }, []);
  if (!projection) return null;
  const sales = Object.entries(projection.amount_totals.sales ?? {});
  const refunds = Object.entries(projection.amount_totals.refunds ?? {});
  const purchases = Object.entries(projection.amount_totals.purchases ?? {});
  const totals = (label: string, values: [string, string][]) => <div className="live-projection-value" key={label}>
    <small>{label}</small><strong>{values.length ? values.map(([currency, amount]) => `${amount} ${currency}`).join(' · ') : '—'}</strong>
  </div>;
  return <section className="live-dashboard-projection" aria-live="polite" aria-label="Realtime event analytics">
    <div><span className="live-projection-dot"/><div><strong>Live event totals</strong><small>Event projection · amounts grouped by currency</small></div></div>
    {totals('Sales', sales)}{totals('Refunds', refunds)}{totals('Purchases', purchases)}
    <div className="live-projection-value"><small>Events processed</small><strong>{projection.event_count}</strong></div>
  </section>;
}

const dashboardChapters = [
  ['cinematic-feature', 'A closer look'], ['menu', 'Menu & bill'], ['overview', 'At a glance'], ['performance', 'Financials'], ['revenue', 'Revenue'], ['forecast', 'What is ahead'],
  ['inventory-health', 'Stock'], ['recommendations', 'Next steps'], ['anomalies', 'Needs review'], ['activity', 'Activity'],
] as const;
const storySlideIds = ['dashboard-intro', 'cinematic-feature', 'menu', 'overview', 'performance', 'revenue', 'operations', 'actions'];
const storyTargetParent: Record<string, string> = { forecast: 'operations', 'inventory-health': 'operations', recommendations: 'actions', anomalies: 'actions', activity: 'actions' };
function requestStoryChapter(target: string) {
  window.dispatchEvent(new CustomEvent('morrow-dashboard-navigate', { detail: { target } }));
}

function AnimatedMetric({ value }: { value: string }) {
  const target = Number(value.replace(/[^\d.-]/g, '')) || 0;
  const prefix = value.match(/^[^\d-]*/)?.[0] ?? '';
  const [display, setDisplay] = useState(target);
  const previous = useRef(target);

  useEffect(() => {
    const from = previous.current;
    if (from === target) return;

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reducedMotion) {
      previous.current = target;
      setDisplay(target);
      return;
    }

    let frame = 0;
    const started = performance.now();
    const duration = 420;
    const animate = (now: number) => {
      const progress = Math.min((now - started) / duration, 1);
      const eased = 1 - (1 - progress) ** 3;
      const next = Math.round(from + (target - from) * eased);
      previous.current = next;
      setDisplay(next);
      if (progress < 1) frame = requestAnimationFrame(animate);
    };
    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
  }, [target]);

  return <strong className="metric-value" aria-label={value}><span aria-hidden="true">{prefix}{display.toLocaleString('en-US')}</span></strong>;
}

function DashboardChapterNav() {
  const [active, setActive] = useState('overview');
  useEffect(() => {
    const onNavigate = (event: Event) => {
      const target = (event as CustomEvent<{ target: string }>).detail.target;
      setActive(storyTargetParent[target] ?? target);
    };
    window.addEventListener('morrow-dashboard-navigate', onNavigate);
    return () => window.removeEventListener('morrow-dashboard-navigate', onNavigate);
  }, []);
  return <nav className="dashboard-chapter-nav" aria-label="On this dashboard">{dashboardChapters.map(([id, label]) => <a key={id} href={`#${id}`} aria-current={active === id ? 'location' : undefined} onClick={event => { event.preventDefault(); requestStoryChapter(id); }}>{label}</a>)}</nav>;
}

const commandPaths = [
  { href: '/sales', label: 'Review sales', detail: 'Recorded transactions and payment activity', icon: ShoppingBag, className: 'shortcut-blue' },
  { href: '/inventory', label: 'Check inventory', detail: 'Stock levels, expiry, and rule-based alerts', icon: Boxes, className: 'shortcut-mint' },
  { href: '/forecasting', label: 'View forecasts', detail: 'Historical data beside model predictions', icon: ChartNoAxesCombined, className: 'shortcut-lilac' },
  { href: '/recommendations', label: 'Review actions', detail: 'Recommendations requiring owner approval', icon: PackageCheck, className: 'shortcut-yellow' },
];

function CommandShortcuts() {
  return <section className="command-shortcuts scroll-reveal" aria-labelledby="command-shortcuts-title">
    <div className="shortcuts-heading"><div><div className="section-kicker">MOVE THROUGH YOUR BUSINESS</div><h2 id="command-shortcuts-title">Start with a workflow</h2></div><span>Choose where to look next</span></div>
    <div className="shortcut-grid">{commandPaths.map(item => { const Icon = item.icon; return <Link href={item.href} className={`shortcut-card ${item.className}`} key={item.href}>
      <span className="shortcut-icon"><Icon size={17}/></span><span><strong>{item.label}</strong><small>{item.detail}</small></span><ArrowUpRight className="shortcut-arrow" size={15}/>
    </Link>; })}</div>
  </section>;
}

function StorySlideControls({ number, previous, next, nextLabel }: { number: string; previous?: string; next: string; nextLabel: string }) {
  return <nav className="story-slide-controls" aria-label={`Dashboard chapter ${number}`}>
    <span className="story-slide-index">{number}<i/>08</span>
    <div className="story-slide-actions">
      {previous && <Link href={`#${previous}`} onClick={event => { event.preventDefault(); requestStoryChapter(previous); }} className="story-step-button" aria-label="Previous dashboard chapter"><ChevronUp size={16}/><span>Previous</span></Link>}
      <Link href={`#${next}`} onClick={event => { event.preventDefault(); requestStoryChapter(next); }} className="story-step-button story-step-next"><span>{nextLabel}</span><ChevronDown size={16}/></Link>
    </div>
  </nav>;
}

function MenuBillingSlide() {
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [carouselEdges, setCarouselEdges] = useState({ start: true, end: false });
  const carouselRef = useRef<HTMLDivElement>(null);
  const menuItems = demoProducts.slice(0, 4);
  const count = Object.values(quantities).reduce((total, quantity) => total + quantity, 0);
  const subtotal = menuItems.reduce((total, item) => total + item.price * (quantities[item.id] ?? 0), 0);
  const tax = subtotal * .08;
  const updateQuantity = (id: string, delta: number) => setQuantities(current => {
    const next = Math.max(0, (current[id] ?? 0) + delta);
    return { ...current, [id]: next };
  });
  const scrollMenu = (direction: -1 | 1) => {
    const carousel = carouselRef.current;
    const firstCard = carousel?.querySelector<HTMLElement>('.menu-item-window');
    if (!carousel || !firstCard) return;
    carousel.scrollBy({ left: direction * (firstCard.offsetWidth + 12), behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  };
  const updateCarouselEdges = (carousel: HTMLDivElement) => setCarouselEdges({ start: carousel.scrollLeft <= 3, end: carousel.scrollLeft + carousel.clientWidth >= carousel.scrollWidth - 3 });
  return <>
    <div className="menu-billing-backdrop" aria-hidden="true"/>
    <div className="menu-billing-content">
      <header className="menu-slide-heading"><span className="section-kicker">MENU · BILLING PREVIEW</span><h2 id="menu-title">A menu made for a quick checkout.</h2><p>Choose items to build an illustrative bill. Product photos can be connected to your catalog when the backend is ready.</p></header>
      <div className="menu-billing-layout">
        <section className="menu-catalog" aria-label="Sample menu items">
          <div className="menu-carousel-toolbar"><span>FEATURED MENU <small>Swipe to browse</small></span><div><button aria-label="Previous dishes" disabled={carouselEdges.start} onClick={() => scrollMenu(-1)}><ChevronLeft size={14}/></button><button aria-label="Next dishes" disabled={carouselEdges.end} onClick={() => scrollMenu(1)}><ChevronRight size={14}/></button></div></div>
          <div className="menu-item-carousel" ref={carouselRef} onScroll={event => updateCarouselEdges(event.currentTarget)}>{menuItems.map((item, index) => {
          const dishMarks = ['☕', '🥛', '🥐', '🫐'];
          return <article className={`menu-item-window menu-image-${index + 1}`} key={item.id}>
            <div className="menu-dish-image" role="img" aria-label={item.imageUrl ? item.name : `Dish image placeholder for ${item.name}`}>{item.imageUrl ? <img className="menu-product-photo" src={item.imageUrl} alt="" loading="lazy"/> : <span className="menu-image-placeholder">{dishMarks[index]}</span>}<span className="menu-image-status"><UtensilsCrossed size={11}/> {item.imageUrl ? 'CATALOG IMAGE' : 'PHOTO SLOT'}</span></div>
            <div className="menu-item-overlay"><span><strong>{item.name}</strong><small>{item.category} · {item.stock} available in sample data</small></span><b>{money(item.price)}</b></div>
            <button className="menu-add-item" onClick={() => updateQuantity(item.id, 1)} aria-label={`Add ${item.name} to bill`}><Plus size={15}/></button>
            {(quantities[item.id] ?? 0) > 0 && <span className="menu-item-quantity" aria-label={`${quantities[item.id]} added`}>{quantities[item.id]}</span>}
          </article>;
          })}</div>
        </section>
        <aside className="menu-bill-panel" aria-label="Bill preview">
          <div className="menu-bill-heading"><span className="menu-bill-icon"><ShoppingBasket size={16}/></span><span><strong>Current bill</strong><small>Preview only · not a sale</small></span><b>{count} {count === 1 ? 'item' : 'items'}</b><button className="menu-clear-bill" disabled={!count} onClick={() => setQuantities({})} aria-label="Clear bill"><Trash2 size={14}/></button></div>
          <div className="menu-bill-lines">{menuItems.filter(item => quantities[item.id]).map(item => <div className="menu-bill-line" key={item.id}><span><strong>{item.name}</strong><small>{money(item.price)} each</small></span><div className="menu-quantity-stepper"><button aria-label={`Remove one ${item.name}`} onClick={() => updateQuantity(item.id, -1)}><Minus size={12}/></button><b>{quantities[item.id]}</b><button aria-label={`Add one ${item.name}`} onClick={() => updateQuantity(item.id, 1)}><Plus size={12}/></button></div><strong>{money(item.price * quantities[item.id])}</strong></div>)}{!count && <div className="menu-bill-empty"><span>＋</span><strong>Your bill starts here</strong><small>Add a menu item to preview its cost.</small></div>}</div>
          <div className="menu-bill-totals"><div><span>Subtotal</span><b>{money(subtotal)}</b></div><div><span>Estimated tax · 8%</span><b>{money(tax)}</b></div><div className="menu-bill-total"><strong>Total due</strong><strong>{money(subtotal + tax)}</strong></div></div>
          <div className="menu-bill-note"><span>Illustrative pricing</span><span>No payment is processed</span></div>
        </aside>
      </div>
      <StorySlideControls number="03" previous="cinematic-feature" next="overview" nextLabel="Business overview"/>
    </div>
  </>;
}

export default function Dashboard() {
  const [period, setPeriod] = useState<keyof typeof dashboardPeriods>('30 days');
  const [activeSlide, setActiveSlide] = useState('dashboard-intro');
  const [leavingSlide, setLeavingSlide] = useState('');
  const [storyDirection, setStoryDirection] = useState<'down' | 'up'>('down');
  const activeSlideRef = useRef(activeSlide);
  const navigationLock = useRef(false);
  activeSlideRef.current = activeSlide;
  const slideClass = (id: string, extra: string) => `dashboard-story-slide ${extra} ${activeSlide === id ? `is-current story-enter-${storyDirection} ${leavingSlide ? 'is-transitioning' : ''}` : ''} ${leavingSlide === id ? `is-leaving story-leave-${storyDirection}` : ''}`;
  const selectedPeriod = dashboardPeriods[period];
  const kpiValues = [selectedPeriod.revenue, selectedPeriod.profit, selectedPeriod.expenses, selectedPeriod.orders];
  const kpiChanges = [selectedPeriod.revenueChange, selectedPeriod.profitChange, selectedPeriod.expenseChange, selectedPeriod.orderChange];
  const orderCount = Number(selectedPeriod.orders.replace(/,/g, '')) || 1;
  const averageOrder = money(Math.round(Number(selectedPeriod.revenue.replace(/[$,]/g, '')) / orderCount));
  const profitMargin = `${(Number(selectedPeriod.profit.replace(/[$,]/g, '')) / Number(selectedPeriod.revenue.replace(/[$,]/g, '') || 1) * 100).toFixed(1)}%`;
  useEffect(() => {
    document.documentElement.classList.toggle('dashboard-story-transitioning', Boolean(leavingSlide));
    return () => document.documentElement.classList.remove('dashboard-story-transitioning');
  }, [leavingSlide]);
  useEffect(() => {
    document.documentElement.classList.add('dashboard-story-active');
    let unlockTimer = 0;
    let leaveTimer = 0;
    let wheelTotal = 0;
    let wheelResetTimer = 0;
    let touchStartY = 0;
    const navigate = (requested: string, direction?: 'down' | 'up', explicit = false) => {
      const target = storyTargetParent[requested] ?? requested;
      const nextIndex = storySlideIds.indexOf(target);
      if (nextIndex < 0 || target === activeSlideRef.current || navigationLock.current && !explicit) return;
      const currentId = activeSlideRef.current;
      const currentIndex = storySlideIds.indexOf(currentId);
      const nextDirection = direction ?? (nextIndex > currentIndex ? 'down' : 'up');
      navigationLock.current = true;
      setStoryDirection(nextDirection);
      setLeavingSlide(currentId);
      activeSlideRef.current = target;
      setActiveSlide(target);
      history.replaceState(null, '', `#${requested}`);
      window.clearTimeout(unlockTimer);
      window.clearTimeout(leaveTimer);
      unlockTimer = window.setTimeout(() => { navigationLock.current = false; }, 900);
      leaveTimer = window.setTimeout(() => setLeavingSlide(''), 820);
    };
    const onRequest = (event: Event) => navigate((event as CustomEvent<{ target: string }>).detail.target, undefined, true);
    const onWheel = (event: WheelEvent) => {
      if (event.ctrlKey || event.metaKey || Math.abs(event.deltaX) > Math.abs(event.deltaY) || (event.target instanceof Element && event.target.closest('[role="dialog"],.sidebar,.scrim,.palette-backdrop'))) return;
      event.preventDefault();
      wheelTotal += event.deltaY;
      window.clearTimeout(wheelResetTimer);
      wheelResetTimer = window.setTimeout(() => { wheelTotal = 0; }, 140);
      if (Math.abs(wheelTotal) < 42) return;
      const direction = wheelTotal > 0 ? 'down' : 'up';
      wheelTotal = 0;
      const index = storySlideIds.indexOf(activeSlideRef.current);
      navigate(storySlideIds[Math.max(0, Math.min(storySlideIds.length - 1, index + (direction === 'down' ? 1 : -1)))], direction);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey || event.target instanceof HTMLElement && event.target.closest('a,button,input,select,textarea,[role="dialog"]')) return;
      const direction = event.key === 'ArrowDown' || event.key === 'PageDown' || event.key === ' ' ? 'down' : event.key === 'ArrowUp' || event.key === 'PageUp' ? 'up' : null;
      if (!direction) return;
      event.preventDefault();
      const index = storySlideIds.indexOf(activeSlideRef.current);
      navigate(storySlideIds[Math.max(0, Math.min(storySlideIds.length - 1, index + (direction === 'down' ? 1 : -1)))], direction);
    };
    const onTouchStart = (event: TouchEvent) => { touchStartY = event.touches[0]?.clientY ?? 0; };
    const onTouchEnd = (event: TouchEvent) => {
      if (event.target instanceof Element && event.target.closest('a,button,input,select,textarea,[role="dialog"],.sidebar,.scrim,.palette-backdrop')) return;
      const delta = touchStartY - (event.changedTouches[0]?.clientY ?? touchStartY);
      if (Math.abs(delta) < 52) return;
      const direction = delta > 0 ? 'down' : 'up';
      const index = storySlideIds.indexOf(activeSlideRef.current);
      navigate(storySlideIds[Math.max(0, Math.min(storySlideIds.length - 1, index + (direction === 'down' ? 1 : -1)))], direction);
    };
    const initialTarget = location.hash.slice(1);
    if (initialTarget) {
      const target = storyTargetParent[initialTarget] ?? initialTarget;
      if (storySlideIds.includes(target)) { activeSlideRef.current = target; setActiveSlide(target); }
    }
    window.addEventListener('morrow-dashboard-navigate', onRequest);
    document.addEventListener('wheel', onWheel, { passive: false });
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('touchstart', onTouchStart, { passive: true });
    document.addEventListener('touchend', onTouchEnd, { passive: true });
    return () => {
      document.documentElement.classList.remove('dashboard-story-active');
      window.removeEventListener('morrow-dashboard-navigate', onRequest);
      document.removeEventListener('wheel', onWheel);
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('touchstart', onTouchStart);
      document.removeEventListener('touchend', onTouchEnd);
      window.clearTimeout(unlockTimer);
      window.clearTimeout(leaveTimer);
      window.clearTimeout(wheelResetTimer);
    };
  }, []);
  useEffect(() => {
    const nodes = Array.from(document.querySelectorAll<HTMLElement>('.scroll-reveal'));
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduceMotion || !('IntersectionObserver' in window)) {
      nodes.forEach(node => node.classList.add('is-visible'));
      return;
    }
    document.documentElement.classList.add('scroll-reveal-ready');
    const observer = new IntersectionObserver(entries => entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      }
    }), { threshold: .12, rootMargin: '0px 0px -7% 0px' });
    nodes.forEach(node => observer.observe(node));
    return () => { observer.disconnect(); document.documentElement.classList.remove('scroll-reveal-ready'); };
  }, []);
  useEffect(() => {
    const active = document.getElementById(activeSlide);
    if (!active) return;
    window.requestAnimationFrame(() => {
      if (active.matches('.scroll-reveal')) active.classList.add('is-visible');
      active.querySelectorAll<HTMLElement>('.scroll-reveal').forEach(node => node.classList.add('is-visible'));
    });
  }, [activeSlide]);
  const heroVideoRef = useRef<HTMLVideoElement>(null);
  const cinematicVideoRef = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const hero = heroVideoRef.current;
    const cinematic = cinematicVideoRef.current;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const syncPlayback = () => {
      if (reduced || document.hidden) { hero?.pause(); cinematic?.pause(); return; }
      if (activeSlide === 'dashboard-intro') void hero?.play().catch(() => undefined); else hero?.pause();
      if (activeSlide === 'cinematic-feature') void cinematic?.play().catch(() => undefined); else cinematic?.pause();
    };
    syncPlayback();
    document.addEventListener('visibilitychange', syncPlayback);
    return () => document.removeEventListener('visibilitychange', syncPlayback);
  }, [activeSlide]);
  return <div className="dashboard-story-stage">
  <section id="dashboard-intro" className={slideClass('dashboard-intro', 'dashboard-opening-slide')} aria-hidden={activeSlide !== 'dashboard-intro'} aria-labelledby="dashboard-hero-title">
    <section className="dashboard-hero">
      <video ref={heroVideoRef} className="dashboard-hero-video" autoPlay muted loop playsInline preload="metadata" poster="/media/command-center-poster.jpg" aria-hidden="true">
        <source src="/media/command-center-motion.mp4" type="video/mp4"/>
      </video>
      <div className="dashboard-hero-overlay" aria-hidden="true"/>
      <div className="dashboard-hero-content">
        <div className="eyebrow">BUSINESS COMMAND CENTER</div>
        <h1 id="dashboard-hero-title">YOUR BUSINESS,<br/>IN FOCUS.</h1>
        <p>A clearer view of what’s happening, what’s ahead, and where to act.</p>
        <label className="hero-period-control"><span className="sr-only">Hero reporting period</span><select aria-label="Hero reporting period" value={period} onChange={event => setPeriod(event.target.value as keyof typeof dashboardPeriods)}><option>7 days</option><option>30 days</option><option>90 days</option></select></label>
      </div>
    </section>
    <StorySlideControls number="01" next="cinematic-feature" nextLabel="Scroll to explore"/>
  </section>

  <section id="cinematic-feature" className={slideClass('cinematic-feature', 'cinematic-feature scroll-reveal')} aria-hidden={activeSlide !== 'cinematic-feature'} aria-labelledby="cinematic-feature-title">
    <div className="cinematic-copy"><span className="section-kicker">A BUSINESS IN MOTION</span><h2 id="cinematic-feature-title">See the bigger picture.</h2><p>Sales, stock, and demand are connected. Morrow brings the signals into one clear view.</p></div>
    <div className="cinematic-stage" aria-label="Decorative cinematic preview of connected business operations">
      <span className="cinematic-shape shape-left shape-blue" aria-hidden="true"/><span className="cinematic-shape shape-left shape-lilac" aria-hidden="true"/><span className="cinematic-shape shape-right shape-mint" aria-hidden="true"/><span className="cinematic-shape shape-right shape-amber" aria-hidden="true"/>
      <div className="cinematic-window"><video ref={cinematicVideoRef} className="cinematic-video" muted loop playsInline preload="none" poster="/media/menu-slide-poster.jpg" aria-hidden="true"><source src="/media/menu-slide-motion.mp4" type="video/mp4"/></video><div className="cinematic-window-shade"/><div className="cinematic-caption"><span className="cinematic-live-dot"/><span>ONE CONNECTED VIEW</span><strong>From daily signals<br/>to better decisions.</strong></div><span className="cinematic-window-index">01 — 03</span></div>
    </div>
    <div className="cinematic-foot"><span>Performance · inventory · outlook</span><Link href="/analytics" className="mini-link">Explore analytics <ArrowUpRight size={13}/></Link></div>
    <StorySlideControls number="02" previous="dashboard-intro" next="menu" nextLabel="Explore the menu"/>
  </section>

  <section id="menu" className={slideClass('menu', 'menu-billing-slide')} aria-hidden={activeSlide !== 'menu'} aria-labelledby="menu-title"><MenuBillingSlide/></section>

  <section id="overview" className={slideClass('overview', 'story-overview-slide story-photo-slide story-photo-overview')} aria-hidden={activeSlide !== 'overview'} aria-labelledby="overview-title">
    <div className="story-slide-heading"><div><span className="section-kicker">THE BUSINESS AT A GLANCE</span><h2 id="overview-title">Your business, clearly.</h2><p>Key signals for the selected {period.toLowerCase()} period.</p></div><label className="story-period-control"><span>PERIOD</span><select aria-label="Dashboard reporting period" value={period} onChange={event => setPeriod(event.target.value as keyof typeof dashboardPeriods)}><option>7 days</option><option>30 days</option><option>90 days</option></select></label></div>
    <DashboardChapterNav/>
    <LiveDashboardProjection/>
    <section className="metric-grid command-metrics scroll-reveal" aria-label="Business at a glance">
      <article className="metric-card command-metric metric-revenue" aria-label="Revenue">
        <div className="metric-top"><span>Revenue</span><span className="metric-context">THIS PERIOD</span></div><AnimatedMetric value={kpiValues[0]}/>
        <div className="metric-foot"><span className="change positive"><ArrowUpRight size={13}/>{kpiChanges[0]}</span><span>compared with previous period</span></div>
        <div className="revenue-sparkline" aria-hidden="true"><svg viewBox="0 0 300 44" preserveAspectRatio="none"><path d="M0 35 C24 33 28 18 52 23 S86 37 108 20 S143 29 166 14 S204 26 224 12 S257 21 277 8 S291 12 300 3"/></svg></div>
      </article>
      <article className="metric-card command-metric metric-profit"><div className="metric-top"><span>Net profit</span><span className="metric-icon lavender"><Wallet size={15}/></span></div><AnimatedMetric value={kpiValues[1]}/><div className="metric-foot"><span className="change positive"><ArrowUpRight size={13}/>{kpiChanges[1]}</span><span>{profitMargin} margin</span></div><div className="metric-subline"><span>Profit margin</span><strong>{profitMargin}</strong></div></article>
      <article className="metric-card command-metric metric-expenses"><div className="metric-top"><span>Expenses</span><span className="metric-icon sand"><ReceiptText size={15}/></span></div><AnimatedMetric value={kpiValues[2]}/><div className="metric-foot"><span className="change neutral-change"><ArrowDownRight size={13}/>{kpiChanges[2]}</span><span>costs vs previous period</span></div></article>
      <article className="metric-card command-metric metric-orders"><div className="metric-top"><span>Orders</span><span className="metric-icon blue"><ShoppingBag size={15}/></span></div><AnimatedMetric value={kpiValues[3]}/><div className="metric-foot"><span className="change positive"><ArrowUpRight size={13}/>{kpiChanges[3]}</span><span>orders this period</span></div><div className="metric-subline"><span>Average order</span><strong>{averageOrder}</strong></div></article>
    </section>
    <CommandShortcuts/>
    <StorySlideControls number="04" previous="menu" next="performance" nextLabel="Financial performance"/>
  </section>

  <section id="performance" className={slideClass('performance', 'story-performance-slide story-photo-slide story-photo-performance')} aria-hidden={activeSlide !== 'performance'} aria-labelledby="performance-title">
    <div className="story-slide-heading"><div><span className="section-kicker">WHAT IS HAPPENING</span><h2 id="performance-title">Financial performance</h2><p>Compare profit, expenses, and revenue over {period.toLowerCase()}.</p></div><span className="story-period-badge">{period} · illustrative</span></div>
    <section className="financial-trends-grid scroll-reveal" aria-label="Financial trends">
      <article className="panel financial-trend-card"><div className="panel-heading"><div><div className="section-kicker">FINANCIAL PERFORMANCE</div><h2>Profit trend</h2><p>Illustrative operating result · {period}</p></div><strong className="financial-trend-value">{selectedPeriod.profit}</strong></div><SalesChart kind="line" metric="profit" data={selectedPeriod.performance}/></article>
      <article className="panel financial-trend-card"><div className="panel-heading"><div><div className="section-kicker">COST CONTROL</div><h2>Expenses</h2><p>Illustrative operating costs · {period}</p></div><strong className="financial-trend-value">{selectedPeriod.expenses}</strong></div><SalesChart kind="bar" metric="expenses" data={selectedPeriod.performance}/></article>
    </section>
    <StorySlideControls number="05" previous="overview" next="revenue" nextLabel="Revenue detail"/>
  </section>

  <section id="revenue" className={slideClass('revenue', 'story-revenue-slide story-photo-slide story-photo-revenue')} aria-hidden={activeSlide !== 'revenue'} aria-labelledby="revenue-title">
    <section className="panel command-chart-panel story-revenue-panel scroll-reveal">
      <div className="panel-heading"><div><div className="section-kicker">REVENUE · WHAT IS HAPPENING</div><h2 id="revenue-title">Revenue performance</h2><p>Illustrative sales history · {period}</p></div><span className="chart-period-label">{period} view</span></div>
      <div className="chart-kpi"><strong>{selectedPeriod.revenue}</strong><span className="change positive"><ArrowUpRight size={14}/> {selectedPeriod.revenueChange}</span><span>vs. previous {period}</span></div>
      <div className="chart-wrap command-chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={selectedPeriod.series} margin={{ top: 12, right: 4, left: -25, bottom: 0 }}><defs><linearGradient id="commandRevenue" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2563eb" stopOpacity={.2}/><stop offset="95%" stopColor="#2563eb" stopOpacity={0}/></linearGradient></defs><CartesianGrid vertical={false} stroke="var(--chart-grid)"/><XAxis dataKey="d" axisLine={false} tickLine={false} tick={{ fill: 'var(--muted)', fontSize: 11 }}/><YAxis hide/><Tooltip formatter={v => money(Number(v))}/><Area type="monotone" dataKey="revenue" stroke="#2563eb" strokeWidth={2.5} fill="url(#commandRevenue)"/></AreaChart></ResponsiveContainer></div>
      <div className="chart-legend"><span><i className="legend-dot healthy"/>Revenue</span><span><i className="legend-line muted-line"/>Previous period</span></div>
    </section>
    <StorySlideControls number="06" previous="performance" next="operations" nextLabel="Demand & inventory"/>
  </section>

  <section id="operations" className={slideClass('operations', 'story-operations-slide story-photo-slide story-photo-operations')} aria-hidden={activeSlide !== 'operations'} aria-labelledby="operations-title">
    <div className="story-slide-heading"><div><span className="section-kicker ai-kicker"><Sparkles size={12}/> WHAT WILL HAPPEN</span><h2 id="operations-title">Demand meets inventory.</h2><p>Forecasts and rule-based stock health, together in one view.</p></div></div>
    <div className="story-operations-grid">
      <section id="forecast" className="panel forecast-panel scroll-reveal"><div className="panel-heading"><div><div className="section-kicker ai-kicker"><Sparkles size={12}/> PREDICTION · PREVIEW DATA</div><h2>Demand outlook</h2><p>Illustrative outlook · next 7 days</p></div><Link href="/forecasting" className="mini-link">Details <ArrowUpRight size={13}/></Link></div><div className="forecast-callout"><span className="forecast-mark"><Sparkles size={15}/></span><div><strong>Demand may rise</strong><small>Illustrative outlook points to a busier weekend.</small></div><span className="confidence">Range<small>preview</small></span></div><div className="chart-wrap forecast-chart"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={forecastSeries} margin={{ top: 10, right: 4, left: -25, bottom: 0 }}><CartesianGrid vertical={false} stroke="var(--chart-grid)"/><XAxis dataKey="d" axisLine={false} tickLine={false} tick={{ fill: 'var(--muted)', fontSize: 10 }}/><YAxis hide/><Tooltip/><Area type="monotone" dataKey="upper" stroke="none" fill="#dcefff"/><Area type="monotone" dataKey="lower" stroke="none" fill="var(--panel)"/><Line type="monotone" dataKey="demand" stroke="#1683e5" strokeWidth={2.4} dot={false} strokeDasharray="5 4"/></ComposedChart></ResponsiveContainer></div><div className="chart-legend"><span><i className="legend-line ai-line"/>Predicted demand</span><span><i className="legend-dot forecast-band"/>Confidence range</span></div></section>
      <section id="inventory-health" className="panel health-panel scroll-reveal"><div className="panel-heading"><div><div className="section-kicker">OPERATIONS</div><h2>Inventory health</h2></div><Link href="/inventory" className="mini-link">View inventory <ArrowUpRight size={13}/></Link></div><div className="health-overview"><div className="health-score"><strong>86</strong><span>/100</span></div><div><strong>In good shape</strong><p>A sample view of stock levels and expiry risk.</p></div></div>{inventoryHealth.map(row => <div className="health-row" key={row.label}><span><i className={`legend-dot ${row.tone}`}/>{row.label}</span><strong>{row.value}</strong><div className="health-track"><i className={row.tone === 'low' ? 'low-track' : row.tone === 'critical' ? 'critical-track' : ''} style={{ width: row.percent }}/></div></div>)}<div className="expiry-note"><Clock3 size={14}/> 4 sample ingredients expire within 7 days <Link href="/inventory">Review</Link></div></section>
    </div>
    <StorySlideControls number="07" previous="revenue" next="actions" nextLabel="Recommended actions"/>
  </section>

  <section id="actions" className={slideClass('actions', 'story-actions-slide story-photo-slide story-photo-actions')} aria-hidden={activeSlide !== 'actions'} aria-labelledby="actions-title">
    <div className="story-slide-heading"><div><span className="section-kicker ai-kicker"><Sparkles size={12}/> WHAT SHOULD I DO</span><h2 id="actions-title">The next best actions.</h2><p>Review recommendations, investigate unusual patterns, and follow recent activity.</p></div></div>
    <div className="story-actions-grid">
      <section id="recommendations" className="panel actions-panel scroll-reveal"><div className="panel-heading"><div><div className="section-kicker ai-kicker"><Sparkles size={12}/> RECOMMENDATION</div><h2>Recommended next steps</h2></div><Link href="/recommendations" className="mini-link">All recommendations <ArrowUpRight size={13}/></Link></div>{dashboardRecommendations.map((r, i) => <Link href="/recommendations" className="recommendation-row" key={r.title}><span className={`recommendation-symbol ${r.tone}-symbol`}>{i === 0 ? <PackageCheck size={16}/> : i === 1 ? <Sparkles size={16}/> : <TrendingUp size={16}/>}</span><span className="recommendation-copy"><strong>{r.title}</strong><small>{r.detail}</small><em>{r.meta}</em></span><span className={`recommendation-score ${r.priority === 'Med' ? 'medium-score' : ''}`}>{r.priority}<small>priority</small></span></Link>)}</section>
      <div className="story-review-stack"><section id="anomalies" className="panel anomaly-panel scroll-reveal"><div className="panel-heading"><div><div className="section-kicker risk-kicker">NEEDS REVIEW</div><h2>Anomaly alerts</h2><p>Patterns outside your normal range</p></div><Link href="/anomalies" className="mini-link">View all <ArrowUpRight size={13}/></Link></div>{dashboardAnomalies.map(a => <Link href="/anomalies" key={a.title} className="anomaly-row"><span className={`anomaly-indicator ${a.tone === 'high' ? 'high-indicator' : 'low-indicator'}`}/><span><strong>{a.title}</strong><small>{a.detail}</small></span><span className={`risk-tag ${a.tone === 'high' ? 'high-tag' : 'watch-tag'}`}>{a.severity}</span></Link>)}</section>
      <section id="activity" className="panel activity-panel scroll-reveal"><div className="panel-heading"><div><div className="section-kicker">ACTIVITY</div><h2>Recent activity</h2></div><Link href="/audit-log" className="mini-link">Audit log <ArrowUpRight size={13}/></Link></div><div className="activity-list">{dashboardActivity.map((a, i) => <div className="activity-row" key={i}><span className={`activity-marker ${a.tone}`}>{a.icon}</span><span><strong>{a.title}</strong><small>{a.detail}</small></span><time>{a.time}</time></div>)}</div></section></div>
    </div>
    <p className="sample-disclaimer"><Sparkles size={12}/> Illustrative preview · Charts and cards use sample values. Live event totals use the connected API projection when available.</p>
    <StorySlideControls number="08" previous="operations" next="dashboard-intro" nextLabel="Back to beginning"/>
  </section>
  </div>;
}
