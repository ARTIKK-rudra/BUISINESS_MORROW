'use client';
import { useId } from 'react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, BarChart, Bar, Cell, LineChart, Line, ComposedChart, ReferenceLine } from 'recharts';
import { analyticsSeries, forecastWorkspaceSeries, stockSeries } from '@/lib/mock-data';
export type AnalyticsMetric = 'sales' | 'profit' | 'expenses' | 'demand';
export function SalesChart({ kind = 'area', metric = 'sales', data }: { kind?: 'area' | 'bar' | 'line'; metric?: AnalyticsMetric; data?: Array<Record<string, string | number>> }) {
  const sales: Array<Record<string, string | number>> = data ?? analyticsSeries;
  const color = metric === 'profit' ? '#258b64' : metric === 'expenses' ? '#c68a32' : metric === 'demand' ? '#7774b8' : '#2563eb';
  const expensePalette = [
    ['#7ae4c4','#42b79a','#18866f'], ['#9db8ff','#678fe9','#3f63c2'],
    ['#ffda85','#efb44b','#b97522'], ['#ff9d8f','#e77b6e','#b84e58'],
    ['#c4a8f3','#9a79d5','#6946a7'], ['#9cdb9e','#67b87b','#37845c'],
    ['#8ce3ea','#47b8c8','#257c96'], ['#f2a8c3','#d8799f','#a64d77'],
  ];
  const chartId = useId().replace(/:/g, '');
  const fillId = `bar-fill-${metric}-${chartId}`;
  const valueFormatter = (value: unknown) => metric === 'demand' ? `${Number(value)} units` : `$${Number(value).toLocaleString()}`;
  return <div className={`chart-wrap sales-chart sales-chart-${metric}`}><ResponsiveContainer width="100%" height="100%">{kind === 'bar' ? <BarChart data={sales} margin={{ top: 10, right: 8, bottom: 0, left: 4 }} barCategoryGap="24%">
    <defs>
      <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color}/><stop offset="100%" stopColor={color} stopOpacity=".84"/></linearGradient>
      {metric === 'expenses' && expensePalette.map((stops, index) => <linearGradient key={index} id={`expense-gradient-${chartId}-${index}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={stops[0]}/><stop offset="52%" stopColor={stops[1]}/><stop offset="100%" stopColor={stops[2]}/></linearGradient>)}
    </defs>
    <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeDasharray="3 5"/>
    <XAxis dataKey="d" axisLine={false} tickLine={false} tick={{ fill: 'var(--muted)', fontSize: 10 }} dy={7}/><YAxis hide domain={[0, 'dataMax + 5%']}/>
    <Tooltip cursor={{ fill: metric === 'expenses' ? 'rgba(198,138,50,.08)' : 'rgba(37,99,235,.06)' }} formatter={valueFormatter}/>
    <Bar dataKey={metric} fill={`url(#${fillId})`} radius={[8,8,3,3]} maxBarSize={38} background={{ fill: 'var(--chart-grid)', fillOpacity: .16 }}>
      {metric === 'expenses' && sales.map((_, index) => <Cell key={`expense-bar-${index}`} fill={`url(#expense-gradient-${chartId}-${index % expensePalette.length})`} stroke="rgba(255,255,255,.45)" strokeWidth={.7}/>)}
    </Bar>
  </BarChart> : kind === 'line' ? <LineChart data={sales}><CartesianGrid vertical={false} stroke="var(--chart-grid)"/><XAxis dataKey="d" axisLine={false} tickLine={false}/><YAxis hide/><Tooltip formatter={valueFormatter}/><Line type="monotone" dataKey={metric} stroke={color} strokeWidth={2.5} dot={false}/></LineChart> : <AreaChart data={sales}><defs><linearGradient id={`fill-${metric}-${chartId}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity={0.18}/><stop offset="100%" stopColor={color} stopOpacity={0}/></linearGradient></defs><CartesianGrid vertical={false} stroke="var(--chart-grid)"/><XAxis dataKey="d" axisLine={false} tickLine={false} tick={{ fill: 'var(--muted)', fontSize: 11 }}/><YAxis hide/><Tooltip formatter={valueFormatter}/><Area type="monotone" dataKey={metric} stroke={color} strokeWidth={2.5} fill={`url(#fill-${metric}-${chartId})`}/></AreaChart>}</ResponsiveContainer></div>;
}
export function InventoryChart() { return <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><LineChart data={stockSeries}><CartesianGrid vertical={false} stroke="var(--chart-grid)"/><XAxis dataKey="d" axisLine={false} tickLine={false} tick={{ fill: 'var(--muted)', fontSize: 11 }}/><YAxis hide/><Tooltip/><Line type="monotone" dataKey="v" stroke="#1683e5" strokeWidth={2.5} dot={false}/></LineChart></ResponsiveContainer></div>; }

export function ForecastWorkspaceChart() { return <div className="forecast-workspace-chart"><div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={forecastWorkspaceSeries} margin={{ top: 10, right: 8, bottom: 0, left: -22 }}><CartesianGrid vertical={false} stroke="var(--chart-grid)"/><XAxis dataKey="d" axisLine={false} tickLine={false} tick={{ fill: 'var(--muted)', fontSize: 9 }}/><YAxis hide/><Tooltip/><ReferenceLine x="Sun" stroke="var(--line)" strokeDasharray="3 3"/><Area type="monotone" dataKey="upper" stroke="none" fill="#dcefff" connectNulls/><Area type="monotone" dataKey="lower" stroke="none" fill="var(--panel)" connectNulls/><Line type="monotone" dataKey="actual" name="Historical demand" stroke="#168773" strokeWidth={2.4} dot={false}/><Line type="monotone" dataKey="prediction" name="Predicted demand" stroke="#1683e5" strokeWidth={2.4} strokeDasharray="5 4" dot={false}/></ComposedChart></ResponsiveContainer></div><div className="chart-legend"><span><i className="legend-line history-line"/>Historical demand</span><span><i className="legend-line prediction-line"/>Prediction</span><span><i className="legend-dot forecast-band"/>Uncertainty range</span></div></div>; }
