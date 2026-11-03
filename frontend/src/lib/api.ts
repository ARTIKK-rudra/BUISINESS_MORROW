import { inventory, products, sales, suppliers } from './mock-data';
import { notificationsPreview, recommendationsPreview, supplierIntelligencePreview } from '@/mocks/business-preview';
import type { InventoryItem, Product, Sale, Supplier } from '@/types';

export class ApiError extends Error { constructor(message: string, public status?: number) { super(message); this.name = 'ApiError'; } }
const mode = process.env.NEXT_PUBLIC_DATA_MODE ?? 'mock';
const base = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1';
// Keep the bearer token scoped to the current browser tab.  Production should use
// an httpOnly-cookie BFF/session flow; sessionStorage only prevents a harmless page
// refresh from disconnecting the local browser voice experience.
let accessToken: string | null = null;
const sessionTokenKey = 'morrow.access-token';

function currentAccessToken(): string | null {
  if (accessToken) return accessToken;
  if (typeof window === 'undefined') return null;
  accessToken = window.sessionStorage.getItem(sessionTokenKey);
  return accessToken;
}

function rememberAccessToken(token: string): void {
  accessToken = token;
  if (typeof window !== 'undefined') window.sessionStorage.setItem(sessionTokenKey, token);
}
export type RealtimeAnalytics = {
  event_count: number;
  event_counts: Record<string, number>;
  amount_totals: Record<string, Record<string, string>>;
  last_event_at: string | null;
};
export type SupplierIntelligence = { id: string; name: string; email: string | null; contact_name: string | null; is_active: boolean; availability_count: number; purchase_count: number; purchase_spend: string; currency: string; delivered_line_count: number; reliability_observation_count: number; on_time_rate: string | null; average_actual_lead_days: string | null; offers: { supplier_product_id: string; item_id: string; item_name: string; item_type: string; available: boolean; unit_cost: string; currency: string; lead_time_days: number; minimum_order_quantity: string; price_change_percent: string | null; price_observations: number; price_history: { unit_cost: string; currency: string; effective_at: string }[]; purchase_quantity: string; purchase_count: number; delivered_line_count: number; on_time_line_count: number; reliability_observation_count: number }[] };
export type BusinessNotification = { id: string; title: string; body: string; channel: string; status: string; created_at: string };
type ApiInventory = { id: string; product_id: string | null; ingredient_id: string | null; quantity: string | number; reorder_point: string | number; expires_on: string | null; location: string };
type ApiCatalogItem = { id: string; name: string; sku: string; unit?: string; category_id?: string | null };
type ApiCategory = { id: string; name: string };
type ApiSale = { id: string; customer_id: string | null; status: string; total: string | number; currency: string; placed_at: string; items: { quantity: string | number }[] };
type ApiProduct = { id: string; name: string; sku: string; category_id: string | null; price: string | number; unit: string };
async function loadProducts(): Promise<Product[]> {
  const [rows, stock, categories] = await Promise.all([
    request<ApiProduct[]>('/products'), request<ApiInventory[]>('/inventory'), request<ApiCategory[]>('/categories'),
  ]);
  const categoryById = new Map(categories.map(category => [category.id, category.name]));
  const stockByProduct = new Map<string, number>();
  for (const item of stock) if (item.product_id) stockByProduct.set(item.product_id, (stockByProduct.get(item.product_id) ?? 0) + Number(item.quantity));
  const colors = ['sand', 'mint', 'peach', 'lilac'];
  return rows.map((row, index) => ({
    id: row.id, name: row.name, sku: row.sku,
    category: row.category_id ? categoryById.get(row.category_id) ?? 'Uncategorized' : 'Uncategorized',
    price: Number(row.price), stock: stockByProduct.get(row.id) ?? 0, unit: row.unit, color: colors[index % colors.length],
  }));
}
async function loadInventory(): Promise<InventoryItem[]> {
  const [stock, products, ingredients, categories] = await Promise.all([
    request<ApiInventory[]>('/inventory'), request<ApiCatalogItem[]>('/products'),
    request<ApiCatalogItem[]>('/ingredients'), request<ApiCategory[]>('/categories'),
  ]);
  const itemById = new Map([...products, ...ingredients].map(item => [item.id, item]));
  const categoryById = new Map(categories.map(category => [category.id, category.name]));
  return stock.map(row => {
    const item = itemById.get(row.product_id ?? row.ingredient_id ?? '');
    return {
      id: row.id, name: item?.name ?? 'Unnamed inventory item', sku: item?.sku ?? '—',
      category: item?.category_id ? categoryById.get(item.category_id) ?? 'Uncategorized' : 'Uncategorized',
      stock: Number(row.quantity), unit: item?.unit ?? 'units', reorderAt: Number(row.reorder_point),
      expiry: row.expires_on ?? 'Not recorded', location: row.location,
    };
  });
}
async function loadSales(): Promise<Sale[]> {
  const rows = await request<ApiSale[]>('/sales');
  return rows.map(row => ({
    id: row.id, customer: row.customer_id ? `Customer ${row.customer_id.slice(0, 8)}` : 'Walk-in customer',
    date: new Date(row.placed_at).toLocaleString(), items: row.items.length,
    total: Number(row.total), status: row.status === 'completed' ? 'Completed' : row.status === 'refunded' ? 'Refunded' : 'Pending',
    method: 'Payment method not recorded',
  }));
}
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  const headers = new Headers(init?.headers);
  if (!(init?.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const token = currentAccessToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  try { response = await fetch(`${base}${path}`, { ...init, headers }); }
  catch { throw new ApiError('Could not reach the server. Check your connection and try again.'); }
  if (!response.ok) {
    let message = `Request failed (${response.status}). Please try again.`;
    try { const body = await response.json(); if (typeof body?.error?.message === 'string') message = body.error.message; }
    catch { /* Preserve the generic status message for non-JSON errors. */ }
    if (response.status === 401) message = 'Your session has expired. Sign in again, then retry your voice question.';
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}
function wait<T>(value: T): Promise<T> { return new Promise(resolve => setTimeout(() => resolve(structuredClone(value)), 220)); }
export const api = {
  products: (): Promise<Product[]> => mode === 'http' ? loadProducts() : wait(products),
  sales: (): Promise<Sale[]> => mode === 'http' ? loadSales() : wait(sales),
  inventory: (): Promise<InventoryItem[]> => mode === 'http' ? loadInventory() : wait(inventory),
  suppliers: (): Promise<Supplier[]> => mode === 'http' ? request('/suppliers') : wait(suppliers),
  supplierIntelligence: (): Promise<SupplierIntelligence[]> => mode === 'http' ? request('/suppliers/intelligence') : wait(supplierIntelligencePreview),
  voiceContacts: () => request<VoiceContact[]>('/voice/contacts'),
  notifications: (): Promise<BusinessNotification[]> => mode === 'http' ? request('/notifications') : wait(notificationsPreview),
  realtimeAnalytics: (): Promise<RealtimeAnalytics | null> => mode === 'http' ? request<RealtimeAnalytics>('/analytics/realtime') : Promise.resolve(null),
  askAssistant: (question: string, current_route = '/assistant', conversation_history: string[] = []) => mode === 'http' ? request<AssistantResponse>('/assistant/ask', { method: 'POST', body: JSON.stringify({ question, current_route, conversation_history }) }) : Promise.reject(new ApiError('Connect the API and sign in to ask questions about business data.')),
  askByVoice: (question: string, consent: boolean, current_route = '/voice-assistant', conversation_history: string[] = [], conversation_session?: string) => {
    if (mode !== 'http') return Promise.reject(new ApiError('Connect the API and sign in to use voice with business data.'));
    if (!currentAccessToken()) return Promise.reject(new ApiError('Sign in to use voice with business data.', 401));
    return request<AssistantResponse>('/voice/ask', { method: 'POST', body: JSON.stringify({ question, consent_to_store_transcript: consent, current_route, conversation_history, conversation_session }) });
  },
  transcribeVoiceAudio: (audio: Blob) => {
    const form = new FormData();
    form.append('audio', audio, `voice-command.${audio.type.includes('mp4') ? 'm4a' : 'webm'}`);
    return request<{ transcript: string; provider: 'gemini' }>('/voice/transcribe', { method: 'POST', body: form });
  },
  createInvoiceCapture: (file: File) => { const form = new FormData(); form.append('file', file); return mode === 'http' ? request<OCRCapture>('/invoices/ocr-captures', { method: 'POST', body: form }) : Promise.reject(new ApiError('Connect the API and sign in to process supplier invoices.')); },
  invoiceCaptures: () => mode === 'http' ? request<OCRCapture[]>('/invoices/ocr-captures') : Promise.reject(new ApiError('Connect the API and sign in to retrieve invoice drafts.')),
  confirmInvoiceCapture: (captureId: string, input: OCRInvoiceConfirmation) => mode === 'http' ? request<Record<string, unknown>>(`/invoices/ocr-captures/${captureId}/confirm`, { method: 'POST', body: JSON.stringify(input) }) : Promise.reject(new ApiError('Connect the API and sign in to confirm supplier invoices.')),
  rejectInvoiceCapture: (captureId: string) => mode === 'http' ? request<OCRCapture>(`/invoices/ocr-captures/${captureId}/reject`, { method: 'POST' }) : Promise.reject(new ApiError('Connect the API and sign in to reject supplier invoices.')),
  recommendations: () => mode === 'http' ? request<BusinessRecommendation[]>('/recommendations') : wait(recommendationsPreview),
  previewRecommendation: (recommendationId: string) => mode === 'http' ? request<ReorderQuote>(`/recommendations/${recommendationId}/preview`) : Promise.reject(new ApiError('Connect the API and sign in to review recommendations.')),
  approveRecommendation: (recommendationId: string, quote: ReorderQuote) => mode === 'http' ? request<ApprovedPurchase>(`/recommendations/${recommendationId}/approve`, { method: 'POST', body: JSON.stringify({ supplier_product_id: quote.supplier_product_id, quantity: String(quote.quantity), unit_cost: String(quote.unit_cost) }) }) : Promise.reject(new ApiError('Connect the API and sign in to approve recommendations.')),
  provisionCases: () => request<ProvisionCase[]>('/voice/provision/cases'),
  startProvisionCase: (demo_mode: boolean) => request<ProvisionCase>('/voice/provision/cases', { method: 'POST', body: JSON.stringify({ demo_mode }) }),
  ownerProvisionDecision: (id: string, transcript: string) => request<ProvisionCase>(`/voice/provision/cases/${id}/owner-decision`, { method: 'POST', body: JSON.stringify({ transcript }) }),
  managerProvisionResponse: (id: string, contactId: string, transcript: string, quantities: { inventory_id: string; quantity: string }[]) => request<ProvisionCase>(`/voice/provision/cases/${id}/managers/${contactId}/response`, { method: 'POST', body: JSON.stringify({ transcript, quantities }) }),
  resolveProvisionConflict: (id: string, transcript: string, quantities: { inventory_id: string; quantity: string }[]) => request<ProvisionCase>(`/voice/provision/cases/${id}/resolve-conflict`, { method: 'POST', body: JSON.stringify({ transcript, quantities }) }),
  supplierProvisionResponse: (id: string, transcript: string, currency: string, delivery_days: number, items: { inventory_id: string; available_quantity: string; unit_cost: string }[]) => request<ProvisionCase>(`/voice/provision/cases/${id}/supplier-response`, { method: 'POST', body: JSON.stringify({ transcript, currency, delivery_days, items }) }),
  purchaseProvisionDecision: (id: string, approve: boolean, transcript: string) => request<ProvisionCase>(`/voice/provision/cases/${id}/purchase-decision`, { method: 'POST', body: JSON.stringify({ approve, transcript }) }),
  login: async (email: string, password: string) => { if (mode !== 'http') throw new ApiError('Authentication is not connected in preview mode. No session was created.'); const result = await request<{ access_token: string }>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }); rememberAccessToken(result.access_token); window.dispatchEvent(new Event('morrow-auth-changed')); return result; },
  register: async (input: { name: string; email: string; password: string; business_name: string }) => { if (mode !== 'http') throw new ApiError('Registration is not connected in preview mode. No account was created.'); const result = await request<{ access_token: string }>('/auth/register', { method: 'POST', body: JSON.stringify(input) }); rememberAccessToken(result.access_token); window.dispatchEvent(new Event('morrow-auth-changed')); return result; },
  resetPassword: async (email: string) => { if (mode !== 'http') throw new ApiError('Password reset is unavailable in preview mode.'); return request('/auth/password-reset', { method: 'POST', body: JSON.stringify({ email }) }); },
};

export type AssistantResponse = { answer: string; intent: string; sources: string[]; generated_at: string; grounded: boolean; navigation_path?: string | null };
export type OCRCapture = { id: string; status: string; ocr_engine: string; raw_text: string; draft: { supplier_name: string; invoice_number: string; issued_date: string; currency: string; subtotal: string; tax: string; total: string; items: { description: string; quantity: string; unit_price: string }[]; field_confidence: number; needs_manual_review: boolean }; review_required: boolean };
export type OCRInvoiceConfirmation = { invoice_number: string; supplier_id: string; subtotal: string; tax: string; total: string; currency: string; issued_at?: string; items: { description: string; quantity: string; unit_price: string }[] };
export type BusinessRecommendation = { id: string; recommendation_type: string; target_type: string; target_id: string; summary: string; rationale: string; status: string; provenance?: Record<string, unknown> | null };
export type ApprovedPurchase = { id: string; supplier_id: string; status: string; total: string; currency: string; items: { quantity: string; unit_cost: string }[] };
export type ProvisionCase = { id: string; status: string; demo_mode: boolean; shortage_snapshot: { items: { inventory_id: string; name: string; unit: string; available?: string; shortage_to_minimum: string; pending_demand?: string; committed_inbound?: string; replenishment_required?: string }[]; pending_order_count: number; affected_order_count?: number | string; data_quality_issues?: { type: string; message: string }[]; demo?: boolean }; manager_recommendations: Record<string, { contact?: string; quantities?: Record<string, string> } | Record<string, string>>; supplier_quote: { supplier?: string; currency?: string; delivery_days?: number; items?: { inventory_id: string; available_quantity: string; unit_cost: string }[] } | null; approval: { approved: boolean; transcript: string } | null; purchase_id: string | null; created_at: string; completed_at: string | null };
export type VoiceContact = { id: string; full_name: string; role: 'owner' | 'manager' | 'supplier'; phone: string; is_active: boolean; calling_consent: boolean };
export type ReorderQuote = { recommendation_id: string; item_name: string; quantity: string | number; unit: string; supplier_id: string; supplier_name: string; supplier_product_id: string; unit_cost: string | number; estimated_total: string | number; currency: string; recommended_date?: string | null };

export function hasApiSession(): boolean { return mode === 'http' && currentAccessToken() !== null; }
export function isDemoMode(): boolean { return mode !== 'http'; }

export type BusinessEventMessage = {
  event_id: string;
  event_type: string;
  aggregate_type: string;
  aggregate_id: string;
  occurred_at: string;
  payload: Record<string, unknown>;
};

/** Authenticated SSE reader used instead of EventSource because the app uses bearer tokens. */
export async function streamBusinessEvents(
  onEvent: (event: BusinessEventMessage, cursor: string) => void,
  signal: AbortSignal,
  after?: string,
): Promise<void> {
  if (mode !== 'http') return;
  const query = after ? `?after=${encodeURIComponent(after)}` : '';
  const headers = new Headers({ Accept: 'text/event-stream' });
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  const response = await fetch(`${base}/events/stream${query}`, { headers, signal, cache: 'no-store' });
  if (!response.ok || !response.body) throw new ApiError(`Event stream unavailable (${response.status}).`, response.status);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    while (!signal.aborted) {
      const { value, done } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf('\n\n');
      while (boundary >= 0) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const lines = block.split(/\r?\n/);
        const cursor = lines.find(line => line.startsWith('id:'))?.slice(3).trim();
        const data = lines.find(line => line.startsWith('data:'))?.slice(5).trim();
        if (cursor && data && lines.some(line => line === 'event: business')) {
          try { onEvent(JSON.parse(data) as BusinessEventMessage, cursor); } catch { /* Ignore malformed frames. */ }
        }
        boundary = buffer.indexOf('\n\n');
      }
    }
  } finally {
    await reader.cancel().catch(() => undefined);
  }
}
