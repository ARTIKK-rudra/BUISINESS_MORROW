import type { InventoryItem, Product, Sale, Supplier } from '@/types';
export const salesSeries = [{ d: 'Mon', v: 2200, p: 680 }, { d: 'Tue', v: 3100, p: 920 }, { d: 'Wed', v: 2700, p: 760 }, { d: 'Thu', v: 3850, p: 1160 }, { d: 'Fri', v: 3400, p: 1030 }, { d: 'Sat', v: 4600, p: 1410 }, { d: 'Sun', v: 4100, p: 1270 }];
export const stockSeries = [{ d: 'Mon', v: 80 }, { d: 'Tue', v: 72 }, { d: 'Wed', v: 76 }, { d: 'Thu', v: 64 }, { d: 'Fri', v: 58 }, { d: 'Sat', v: 52 }, { d: 'Sun', v: 48 }];
export const dashboardSeries = [{ d: 'Sep 1', revenue: 1080 }, { d: 'Sep 4', revenue: 1310 }, { d: 'Sep 7', revenue: 1210 }, { d: 'Sep 10', revenue: 1660 }, { d: 'Sep 13', revenue: 1500 }, { d: 'Sep 16', revenue: 1830 }, { d: 'Sep 19', revenue: 1620 }, { d: 'Sep 22', revenue: 2170 }, { d: 'Sep 25', revenue: 1980 }, { d: 'Sep 28', revenue: 2450 }];
export const analyticsSeries = [
  { d: 'Mon', sales: 2200, profit: 740, expenses: 1280, demand: 82 }, { d: 'Tue', sales: 3100, profit: 980, expenses: 1420, demand: 88 }, { d: 'Wed', sales: 2700, profit: 850, expenses: 1190, demand: 84 }, { d: 'Thu', sales: 3850, profit: 1310, expenses: 1540, demand: 101 }, { d: 'Fri', sales: 3400, profit: 1160, expenses: 1360, demand: 112 }, { d: 'Sat', sales: 4600, profit: 1620, expenses: 1810, demand: 132 }, { d: 'Sun', sales: 4100, profit: 1450, expenses: 1590, demand: 124 },
];
export const forecastSeries = [{ d: 'Mon', demand: 80, lower: 72, upper: 88 }, { d: 'Tue', demand: 84, lower: 74, upper: 96 }, { d: 'Wed', demand: 88, lower: 76, upper: 101 }, { d: 'Thu', demand: 102, lower: 86, upper: 116 }, { d: 'Fri', demand: 115, lower: 96, upper: 134 }, { d: 'Sat', demand: 132, lower: 109, upper: 155 }, { d: 'Sun', demand: 124, lower: 98, upper: 150 }];
export const forecastWorkspaceSeries = [
  { d: 'Mon', actual: 76, prediction: null, lower: null, upper: null },
  { d: 'Tue', actual: 83, prediction: null, lower: null, upper: null },
  { d: 'Wed', actual: 79, prediction: null, lower: null, upper: null },
  { d: 'Thu', actual: 91, prediction: null, lower: null, upper: null },
  { d: 'Fri', actual: 97, prediction: null, lower: null, upper: null },
  { d: 'Sat', actual: 108, prediction: null, lower: null, upper: null },
  { d: 'Sun', actual: 102, prediction: null, lower: null, upper: null },
  { d: 'Mon +1', actual: null, prediction: 88, lower: 78, upper: 98 },
  { d: 'Tue +1', actual: null, prediction: 93, lower: 80, upper: 106 },
  { d: 'Wed +1', actual: null, prediction: 96, lower: 82, upper: 111 },
  { d: 'Thu +1', actual: null, prediction: 105, lower: 88, upper: 121 },
  { d: 'Fri +1', actual: null, prediction: 118, lower: 98, upper: 137 },
  { d: 'Sat +1', actual: null, prediction: 132, lower: 107, upper: 156 },
  { d: 'Sun +1', actual: null, prediction: 125, lower: 98, upper: 151 },
];
export const dashboardActivity = [
  { title: 'New sale recorded', detail: 'Order #2081 · $18.25', time: '2 min ago', tone: 'activity-green', icon: '↗' },
  { title: 'Inventory alert created', detail: 'Oat milk is below reorder point', time: '18 min ago', tone: 'activity-amber', icon: '!' },
  { title: 'Forecast refreshed', detail: '7 day demand outlook updated', time: '1 hr ago', tone: 'activity-violet', icon: '✦' },
  { title: 'Purchase order received', detail: 'Field & Flour Bakery · 12 items', time: '3 hr ago', tone: 'activity-blue', icon: '↓' },
];
export const dashboardMetrics = [
  { label: 'Revenue', value: '$42,680', change: '12.8%', trend: 'up', tone: 'sage', note: 'vs previous period', icon: '↗' },
  { label: 'Net profit', value: '$14,920', change: '8.4%', trend: 'up', tone: 'lavender', note: '34.9% margin', icon: '↗' },
  { label: 'Expenses', value: '$11,380', change: '3.2%', trend: 'down', tone: 'sand', note: 'vs previous period', icon: '↘' },
  { label: 'Orders', value: '1,284', change: '6.1%', trend: 'up', tone: 'blue', note: 'avg. $33.24 / order', icon: '↗' },
];
export const dashboardPeriods = {
  '7 days': {
    revenue: '$10,842', profit: '$3,791', expenses: '$2,846', orders: '326',
    revenueChange: '5.4%', profitChange: '6.2%', expenseChange: '1.8%', orderChange: '4.1%',
    series: [{ d: 'Mon', revenue: 1280 }, { d: 'Tue', revenue: 1410 }, { d: 'Wed', revenue: 1370 }, { d: 'Thu', revenue: 1590 }, { d: 'Fri', revenue: 1710 }, { d: 'Sat', revenue: 1910 }, { d: 'Sun', revenue: 1571 }],
    performance: [{ d: 'Mon', profit: 330, expenses: 312 }, { d: 'Tue', profit: 418, expenses: 354 }, { d: 'Wed', profit: 395, expenses: 330 }, { d: 'Thu', profit: 527, expenses: 388 }, { d: 'Fri', profit: 610, expenses: 405 }, { d: 'Sat', profit: 768, expenses: 522 }, { d: 'Sun', profit: 743, expenses: 535 }],
  },
  '30 days': {
    revenue: '$42,680', profit: '$14,920', expenses: '$11,380', orders: '1,284',
    revenueChange: '12.8%', profitChange: '8.4%', expenseChange: '3.2%', orderChange: '6.1%',
    series: dashboardSeries,
    performance: [{ d: 'Sep 1', profit: 370, expenses: 1120 }, { d: 'Sep 4', profit: 421, expenses: 1190 }, { d: 'Sep 7', profit: 398, expenses: 1090 }, { d: 'Sep 10', profit: 510, expenses: 1230 }, { d: 'Sep 13', profit: 482, expenses: 1170 }, { d: 'Sep 16', profit: 590, expenses: 1300 }, { d: 'Sep 19', profit: 560, expenses: 1260 }, { d: 'Sep 22', profit: 652, expenses: 1410 }, { d: 'Sep 25', profit: 621, expenses: 1360 }, { d: 'Sep 28', profit: 740, expenses: 1530 }],
  },
  '90 days': {
    revenue: '$126,940', profit: '$43,180', expenses: '$33,760', orders: '3,806',
    revenueChange: '9.6%', profitChange: '7.1%', expenseChange: '2.6%', orderChange: '5.8%',
    series: [{ d: 'Jul 1', revenue: 3010 }, { d: 'Jul 10', revenue: 3260 }, { d: 'Jul 19', revenue: 3150 }, { d: 'Jul 28', revenue: 3480 }, { d: 'Aug 6', revenue: 3890 }, { d: 'Aug 15', revenue: 3710 }, { d: 'Aug 24', revenue: 4160 }, { d: 'Sep 2', revenue: 4380 }, { d: 'Sep 11', revenue: 4510 }, { d: 'Sep 20', revenue: 4820 }],
    performance: [{ d: 'Jul 1', profit: 870, expenses: 3020 }, { d: 'Jul 10', profit: 940, expenses: 3150 }, { d: 'Jul 19', profit: 910, expenses: 3080 }, { d: 'Jul 28', profit: 1010, expenses: 3260 }, { d: 'Aug 6', profit: 1120, expenses: 3450 }, { d: 'Aug 15', profit: 1090, expenses: 3390 }, { d: 'Aug 24', profit: 1220, expenses: 3580 }, { d: 'Sep 2', profit: 1310, expenses: 3710 }, { d: 'Sep 11', profit: 1340, expenses: 3790 }, { d: 'Sep 20', profit: 1420, expenses: 3880 }],
  },
};
export const dashboardSignals = [
  { href: '/inventory', label: 'INVENTORY RISK', title: '8 items need attention', aside: '2 critical', tone: 'risk', icon: '!' },
  { href: '/forecasting', label: 'PREDICTED DEMAND', title: '+14% this week', aside: 'View forecast', tone: 'demand', icon: '↗' },
  { href: '/anomalies', label: 'ANOMALIES', title: '2 unusual patterns', aside: 'Review', tone: 'alert', icon: '!' },
  { href: '/recommendations', label: 'PENDING ACTIONS', title: '3 recommendations', aside: 'Review', tone: 'pending', icon: '✦' },
];
export const inventoryHealth = [
  { label: 'Healthy stock', value: '54 items', percent: '82%', tone: 'healthy' },
  { label: 'Running low', value: '6 items', percent: '35%', tone: 'low' },
  { label: 'Critical', value: '2 items', percent: '16%', tone: 'critical' },
];
export const dashboardRecommendations = [
  { title: 'Restock oat milk today', detail: 'Current stock covers ~2 days. Supplier delivery takes 2 days.', meta: 'Inventory · High impact', priority: 'High', tone: 'green', icon: '▦' },
  { title: 'Prepare for weekend demand', detail: 'Pastry demand is trending 18% above your weekly average.', meta: 'Demand planning · Medium impact', priority: 'Med', tone: 'violet', icon: '✦' },
  { title: 'Review afternoon promotion', detail: 'Recent lift is strongest between 2 and 4 pm on weekdays.', meta: 'Sales · Opportunity', priority: 'Med', tone: 'amber', icon: '↗' },
];
export const dashboardAnomalies = [
  { title: 'Refund volume increased', detail: 'Yesterday · 3× your usual daily average', severity: 'High', tone: 'high' },
  { title: 'Supplier cost changed', detail: 'House blend beans · +8.5% from last order', severity: 'Review', tone: 'watch' },
];
export const analyticsSummary = [
  { title: 'Sales', value: '$48,290', change: '+12.8%', metric: 'sales', chart: 'area' },
  { title: 'Profit', value: '$16,420', change: '+8.4%', metric: 'profit', chart: 'line' },
  { title: 'Expenses', value: '$9,840', change: '-3.2%', metric: 'expenses', chart: 'bar' },
  { title: 'Demand', value: '1,284 units', change: '+6.1%', metric: 'demand', chart: 'line' },
] as const;
export const products: Product[] = [
  { id: 'p1', name: 'House blend coffee', category: 'Coffee', sku: 'COF-001', price: 4.5, stock: 82, unit: 'cup', color: 'sand' },
  { id: 'p2', name: 'Oat latte', category: 'Coffee', sku: 'COF-002', price: 5.25, stock: 41, unit: 'cup', color: 'mint' },
  { id: 'p3', name: 'Butter croissant', category: 'Bakery', sku: 'BAK-001', price: 3.75, stock: 16, unit: 'each', color: 'peach' },
  { id: 'p4', name: 'Blueberry muffin', category: 'Bakery', sku: 'BAK-002', price: 4, stock: 9, unit: 'each', color: 'lilac' },
  { id: 'p5', name: 'Avocado toast', category: 'Kitchen', sku: 'KIT-001', price: 9.5, stock: 24, unit: 'plate', color: 'mint' },
  { id: 'p6', name: 'Matcha tonic', category: 'Drinks', sku: 'DRK-001', price: 6.25, stock: 32, unit: 'glass', color: 'lilac' },
  { id: 'p7', name: 'Cold brew', category: 'Drinks', sku: 'DRK-002', price: 5.5, stock: 27, unit: 'glass', color: 'sand' },
  { id: 'p8', name: 'Granola bowl', category: 'Kitchen', sku: 'KIT-002', price: 8.75, stock: 18, unit: 'bowl', color: 'peach' },
];
export const sales: Sale[] = [
  { id: 'INV-2081', customer: 'Maya Chen', date: 'Today, 10:42 AM', items: 3, total: 18.25, status: 'Completed', method: 'Visa •• 4242' },
  { id: 'INV-2080', customer: 'Walk-in customer', date: 'Today, 10:31 AM', items: 2, total: 9.75, status: 'Completed', method: 'Cash' },
  { id: 'INV-2079', customer: 'Oliver James', date: 'Today, 10:18 AM', items: 4, total: 27.5, status: 'Completed', method: 'Apple Pay' },
  { id: 'INV-2078', customer: 'Walk-in customer', date: 'Today, 9:56 AM', items: 1, total: 6.25, status: 'Refunded', method: 'Visa •• 1810' },
  { id: 'INV-2077', customer: 'Priya Shah', date: 'Today, 9:43 AM', items: 2, total: 13.5, status: 'Completed', method: 'Visa •• 4242' },
  { id: 'INV-2076', customer: 'Walk-in customer', date: 'Today, 9:22 AM', items: 3, total: 16.75, status: 'Pending', method: 'Cash' },
];
export const inventory: InventoryItem[] = [
  { id: 'STK-001', name: 'Oat milk', sku: 'ING-041', category: 'Dairy alternatives', stock: 6, unit: 'cartons', reorderAt: 12, expiry: 'Oct 02, 2026', location: 'Cold storage A' },
  { id: 'STK-002', name: 'Blueberry muffins', sku: 'BAK-002', category: 'Bakery', stock: 9, unit: 'each', reorderAt: 15, expiry: 'Sep 28, 2026', location: 'Display case' },
  { id: 'STK-003', name: 'House blend beans', sku: 'ING-001', category: 'Coffee', stock: 24, unit: 'kg', reorderAt: 10, expiry: 'Feb 14, 2027', location: 'Dry storage B' },
  { id: 'STK-004', name: 'Avocados', sku: 'ING-023', category: 'Produce', stock: 4, unit: 'kg', reorderAt: 8, expiry: 'Sep 29, 2026', location: 'Cold storage B' },
  { id: 'STK-005', name: 'Croissants', sku: 'BAK-001', category: 'Bakery', stock: 16, unit: 'each', reorderAt: 12, expiry: 'Sep 28, 2026', location: 'Display case' },
  { id: 'STK-006', name: 'Matcha powder', sku: 'ING-052', category: 'Tea', stock: 8, unit: 'tins', reorderAt: 5, expiry: 'Jan 11, 2027', location: 'Dry storage A' },
];
export const suppliers: Supplier[] = [
  { id: 'SUP-01', name: 'Northstar Roasters', contact: 'Elliot Park', email: 'elliot@northstar.example', products: 8, status: 'Active', spend: 4820, leadTime: 2 },
  { id: 'SUP-02', name: 'Field & Flour Bakery', contact: 'Amara Singh', email: 'orders@fieldflour.example', products: 12, status: 'Active', spend: 3260, leadTime: 1 },
  { id: 'SUP-03', name: 'Green Basket Produce', contact: 'Noah Rivera', email: 'hello@greenbasket.example', products: 16, status: 'Active', spend: 2180, leadTime: 3 },
  { id: 'SUP-04', name: 'Daily Dairy Co.', contact: 'Sofia Patel', email: 'supply@dailydairy.example', products: 6, status: 'Pending', spend: 940, leadTime: 2 },
];
