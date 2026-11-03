import Link from 'next/link';
import { ArrowUpRight, Boxes, CircleDollarSign, Clock3, FileText, Package, ShieldCheck, Truck, Users, type LucideIcon } from 'lucide-react';
import type { PreviewPage } from '@/lib/workspace-preview';

function ColumnSection({ title, eyebrow, rows, columns, icon: Icon }: { title: string; eyebrow: string; rows: string[][]; columns: string[]; icon: LucideIcon }) {
  return <section className="preview-feature-section" aria-label={title}>
    <div className="preview-feature-heading"><div><span>{eyebrow}</span><h2>{title}</h2></div><small>Illustrative preview</small></div>
    <div className="preview-feature-grid">{rows.slice(0, 4).map((row, index) => <article className="panel preview-feature-card" key={`${row[0]}-${index}`}>
      <span className="preview-feature-icon"><Icon size={16}/></span><strong>{row[0]}</strong>
      <p>{row.slice(1, -1).filter(Boolean).join(' · ') || columns[index % columns.length]}</p>
      <small>{row[row.length - 1]}</small>
    </article>)}</div>
  </section>;
}

export function WorkspacePreviewSection({ section, page }: { section: string; page: PreviewPage }) {
  const rows = page.rows;
  switch (section) {
    case 'orders':
      return <section className="preview-feature-section" aria-label="Order fulfillment overview">
        <div className="preview-feature-heading"><div><span>FULFILLMENT FLOW</span><h2>Orders in progress</h2></div><small>Preview records</small></div>
        <div className="order-flow-strip">{['Placed', 'Preparing', 'Ready', 'Completed'].map((step, index) => <div className="order-flow-step" key={step}><span>{String(index + 1).padStart(2, '0')}</span><strong>{step}</strong>{index < 3 && <i/>}</div>)}</div>
        <div className="preview-feature-grid">{rows.slice(0, 3).map(row => <article className="panel preview-feature-card order-preview-card" key={row[0]}><div><span className="preview-feature-icon"><Package size={16}/></span><span className={`status-pill ${row[5] === 'Completed' ? 'completed' : 'pending'}`}>{row[5]}</span></div><strong>{row[0]} · {row[1]}</strong><p>{row[2]} · {row[3]}</p><small>{row[4]}</small></article>)}</div>
      </section>;
    case 'products':
      return <section className="preview-feature-section" aria-label="Product catalog preview">
        <div className="preview-feature-heading"><div><span>PRODUCT CATALOG</span><h2>Popular products</h2></div><small>Visual preview</small></div>
        <div className="catalog-preview-grid">{rows.map(row => <article className="panel catalog-preview-card" key={row[1]}><span className="catalog-product-art"><Boxes size={23}/></span><div><small>{row[2]} · {row[1]}</small><strong>{row[0]}</strong><span>{row[3]} <i>{row[4]} on hand</i></span></div><span className={`status-pill ${row[5] === 'Active' ? 'completed' : 'pending'}`}>{row[5]}</span></article>)}</div>
      </section>;
    case 'purchases':
      return <section className="preview-feature-section" aria-label="Incoming purchase orders">
        <div className="preview-feature-heading"><div><span>INBOUND STOCK</span><h2>Purchase orders to track</h2></div><small>Supplier activity · preview</small></div>
        <div className="preview-feature-grid">{rows.map(row => <article className="panel purchase-preview-card" key={row[0]}><span className="preview-feature-icon"><Truck size={16}/></span><strong>{row[0]}</strong><p>{row[1]}</p><div><span>{row[3]}</span><span className="status-pill pending">{row[5]}</span></div><small>{row[4]}</small></article>)}</div>
      </section>;
    case 'ledger':
      return <div className="ledger-source-note"><span><CircleDollarSign size={17}/></span><div><strong>System-generated activity</strong><p>Ledger entries are presented from recorded business events. Manual journal entry is not available in this workspace preview.</p></div><Link href="/profit-loss" className="mini-link">View profit &amp; loss <ArrowUpRight size={13}/></Link></div>;
    case 'ai-insights':
      return <ColumnSection title="Findings to review" eyebrow="AI INSIGHT · PREVIEW" rows={rows} columns={page.columns} icon={ArrowUpRight}/>;
    case 'anomalies':
      return <section className="preview-feature-section" aria-label="Anomaly review queue"><div className="preview-feature-heading"><div><span>INVESTIGATION QUEUE</span><h2>Signals that need a closer look</h2></div><small>Review signals · not conclusions</small></div><div className="preview-feature-grid">{rows.map(row => <article className="panel anomaly-preview-card" key={row[0]}><span className="anomaly-preview-mark">!</span><div><small>{row[1]} · {row[2]}</small><strong>{row[0]}</strong><p>{row[3]} · {row[4]}</p></div><span className="status-pill pending">{row[5]}</span></article>)}</div></section>;
    case 'customers':
      return <ColumnSection title="Customer directory" eyebrow="CUSTOMER RELATIONSHIPS · PREVIEW" rows={rows} columns={page.columns} icon={Users}/>;
    case 'employees':
      return <section className="preview-feature-section" aria-label="Team access overview"><div className="preview-feature-heading"><div><span>TEAM ACCESS</span><h2>Roles across the workspace</h2></div><small>Role assignments · preview</small></div><div className="preview-feature-grid">{rows.map(row => <article className="panel role-preview-card" key={row[0]}><span className="preview-feature-icon"><ShieldCheck size={16}/></span><strong>{row[0]}</strong><p>{row[1]}</p><small>{row[4]} · {row[3]}</small></article>)}</div></section>;
    case 'reports':
      return <section className="preview-feature-section" aria-label="Report library"><div className="preview-feature-heading"><div><span>REPORT LIBRARY</span><h2>Browse reports by schedule</h2></div><small>Exports unavailable in preview</small></div><div className="preview-feature-grid">{rows.map(row => <article className="panel report-preview-card" key={row[0]}><span className="preview-feature-icon"><FileText size={16}/></span><strong>{row[0]}</strong><p>{row[1]} · Updated {row[2]}</p><small>{row[4]}</small></article>)}</div></section>;
    case 'audit-log':
      return <section className="preview-feature-section" aria-label="Recent audit timeline"><div className="preview-feature-heading"><div><span>ACTIVITY TIMELINE</span><h2>Recent workspace events</h2></div><small>Illustrative events · not authoritative records</small></div><div className="audit-preview-list">{rows.map(row => <article className="audit-preview-item" key={`${row[0]}-${row[3]}`}><span className="audit-preview-dot"/><div><strong>{row[0]} · {row[1]}</strong><p>{row[2]}</p></div><time><Clock3 size={12}/>{row[3]}</time></article>)}</div></section>;
    default:
      return null;
  }
}
