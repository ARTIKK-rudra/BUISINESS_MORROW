'use client';
import { useMemo, useState } from 'react';
import { ChevronDown, Search } from 'lucide-react';
import { PageHeading } from '@/components/ui';
import { AsyncState, useResource } from '@/components/async-state';
import { api } from '@/lib/api';

export default function InventoryPage() {
  const resource = useResource(api.inventory);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('All stock');
  const [category, setCategory] = useState('All categories');
  const categories = useMemo(() => [...new Set((resource.data ?? []).map(item => item.category))].sort(), [resource.data]);
  const rows = useMemo(() => resource.data?.filter(item => {
    const level = item.stock <= item.reorderAt / 2 ? 'Critical' : item.stock <= item.reorderAt ? 'Low stock' : 'Healthy';
    return (status === 'All stock' || level === status)
      && (category === 'All categories' || category === item.category)
      && `${item.name} ${item.sku}`.toLowerCase().includes(query.toLowerCase());
  }), [resource.data, status, category, query]);
  const summary = useMemo(() => {
    const items = resource.data ?? [];
    return {
      total: items.length,
      low: items.filter(item => item.stock <= item.reorderAt).length,
      critical: items.filter(item => item.stock <= item.reorderAt / 2).length,
      expiring: items.filter(item => {
        const expiry = Date.parse(item.expiry);
        const days = (expiry - Date.now()) / 86_400_000;
        return Number.isFinite(expiry) && days >= 0 && days <= 7;
      }).length,
    };
  }, [resource.data]);
  const stats = [
    { label: 'Total items', value: summary.total, note: `Across ${categories.length} categories`, tone: '' },
    { label: 'Low stock', value: summary.low, note: 'At or below reorder point', tone: 'warning-text' },
    { label: 'Critical', value: summary.critical, note: 'At or below half of reorder point', tone: 'danger-text' },
    { label: 'Expiring soon', value: summary.expiring, note: 'Within the next 7 days', tone: 'amber-text' },
  ];

  return <>
    <PageHeading eyebrow="OPERATIONS" title="Inventory" description="Keep an eye on what’s in stock and what needs attention." />
    <AsyncState loading={resource.loading} error={resource.error} empty={!resource.data?.length} retry={resource.retry}>
      <div className="inventory-summary">{stats.map(stat => <div className="panel inventory-stat" key={stat.label}>
        <span>{stat.label}</span><strong className={stat.tone}>{stat.value}</strong><small>{stat.note}</small>
      </div>)}</div>
      <div className="panel data-panel"><div className="data-toolbar">
        <div className="search-field"><Search size={16}/><input placeholder="Search inventory..." aria-label="Search inventory" value={query} onChange={event => setQuery(event.target.value)}/></div>
        <label className="filter-select"><span className="sr-only">Filter stock status</span><select value={status} onChange={event => setStatus(event.target.value)}><option>All stock</option><option>Healthy</option><option>Low stock</option><option>Critical</option></select><ChevronDown size={15}/></label>
        <label className="filter-select"><span className="sr-only">Filter inventory category</span><select value={category} onChange={event => setCategory(event.target.value)}><option>All categories</option>{categories.map(value => <option key={value}>{value}</option>)}</select><ChevronDown size={15}/></label>
      </div>
      <AsyncState loading={false} error="" empty={!rows?.length} retry={resource.retry}>
        <div className="table-scroll"><table><thead><tr><th>ITEM</th><th>SKU</th><th>CATEGORY</th><th>STOCK LEVEL</th><th>STATUS</th><th>EXPIRY DATE</th><th>LOCATION</th></tr></thead><tbody>
          {rows?.map(item => {
            const level = item.stock <= item.reorderAt / 2 ? 'Critical' : item.stock <= item.reorderAt ? 'Low stock' : 'Healthy';
            const pct = item.reorderAt > 0 ? Math.min(100, item.stock / (item.reorderAt * 2) * 100) : 100;
            return <tr key={item.id}><td className="strong-cell">{item.name}</td><td className="muted-cell">{item.sku}</td><td>{item.category}</td><td><div className="stock-cell"><span>{item.stock} {item.unit}</span><i><b className={level === 'Critical' ? 'bar-critical' : level === 'Low stock' ? 'bar-low' : ''} style={{ width: `${pct}%` }}/></i></div></td><td><span className={`status-pill ${level === 'Healthy' ? 'completed' : level === 'Critical' ? 'refunded' : 'pending'}`}>{level}</span></td><td>{item.expiry}</td><td>{item.location}</td></tr>;
          })}
        </tbody></table></div><div className="table-footer">Showing {rows?.length} of {resource.data?.length} items</div>
      </AsyncState></div>
    </AsyncState>
  </>;
}
