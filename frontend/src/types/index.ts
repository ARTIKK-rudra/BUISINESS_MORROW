export type Product = { id: string; name: string; category: string; sku: string; price: number; stock: number; unit: string; color: string; imageUrl?: string };
export type Sale = { id: string; customer: string; date: string; items: number; total: number; status: 'Completed' | 'Refunded' | 'Pending'; method: string };
export type InventoryItem = { id: string; name: string; sku: string; category: string; stock: number; unit: string; reorderAt: number; expiry: string; location: string };
export type Supplier = { id: string; name: string; contact: string; email: string; products: number; status: string; spend: number; leadTime: number };
export type Metrics = { revenue: number; orders: number; margin: number; lowStock: number };
