import type { BusinessNotification, BusinessRecommendation, SupplierIntelligence } from '@/lib/api';

// These records are for visual development only; mock mode never writes them to the API.
export const supplierIntelligencePreview: SupplierIntelligence[] = [
  {
    id: 'preview-supplier-01', name: 'Northstar Roasters', email: 'hello@northstar.example', contact_name: 'Elliot Park', is_active: true,
    availability_count: 8, purchase_count: 31, purchase_spend: '4820.00', currency: 'USD', delivered_line_count: 24,
    reliability_observation_count: 19, on_time_rate: '0.92', average_actual_lead_days: '2.1',
    offers: [{ supplier_product_id: 'preview-offer-01', item_id: 'preview-beans', item_name: 'House blend beans', item_type: 'ingredient', available: true, unit_cost: '18.40', currency: 'USD', lead_time_days: 2, minimum_order_quantity: '5', price_change_percent: '2.4', price_observations: 4, price_history: [{ unit_cost: '18.40', currency: 'USD', effective_at: '2026-10-21T00:00:00Z' }, { unit_cost: '17.95', currency: 'USD', effective_at: '2026-09-21T00:00:00Z' }], purchase_quantity: '86', purchase_count: 9, delivered_line_count: 8, on_time_line_count: 7, reliability_observation_count: 7 }],
  },
  {
    id: 'preview-supplier-02', name: 'Field & Flour Bakery', email: 'orders@fieldflour.example', contact_name: 'Amara Singh', is_active: true,
    availability_count: 12, purchase_count: 24, purchase_spend: '3260.00', currency: 'USD', delivered_line_count: 21,
    reliability_observation_count: 16, on_time_rate: '0.88', average_actual_lead_days: '1.2',
    offers: [{ supplier_product_id: 'preview-offer-02', item_id: 'preview-croissant', item_name: 'Butter croissant', item_type: 'product', available: true, unit_cost: '1.55', currency: 'USD', lead_time_days: 1, minimum_order_quantity: '12', price_change_percent: null, price_observations: 1, price_history: [{ unit_cost: '1.55', currency: 'USD', effective_at: '2026-10-24T00:00:00Z' }], purchase_quantity: '264', purchase_count: 12, delivered_line_count: 11, on_time_line_count: 10, reliability_observation_count: 10 }],
  },
  {
    id: 'preview-supplier-03', name: 'Green Basket Produce', email: 'hello@greenbasket.example', contact_name: 'Noah Rivera', is_active: true,
    availability_count: 16, purchase_count: 18, purchase_spend: '2180.00', currency: 'USD', delivered_line_count: 13,
    reliability_observation_count: 9, on_time_rate: '0.78', average_actual_lead_days: '3.0',
    offers: [{ supplier_product_id: 'preview-offer-03', item_id: 'preview-avocado', item_name: 'Avocados', item_type: 'ingredient', available: true, unit_cost: '2.80', currency: 'USD', lead_time_days: 3, minimum_order_quantity: '4', price_change_percent: '8.5', price_observations: 3, price_history: [{ unit_cost: '2.80', currency: 'USD', effective_at: '2026-10-25T00:00:00Z' }, { unit_cost: '2.58', currency: 'USD', effective_at: '2026-09-20T00:00:00Z' }], purchase_quantity: '42', purchase_count: 5, delivered_line_count: 4, on_time_line_count: 3, reliability_observation_count: 3 }],
  },
];

export const notificationsPreview: BusinessNotification[] = [
  { id: 'preview-notice-01', title: 'Oat milk below reorder point', body: 'Sample stock has reached the configured minimum level.', channel: 'in_app', status: 'Unread', created_at: '2026-10-31T10:24:00+05:30' },
  { id: 'preview-notice-02', title: 'Demand outlook refreshed', body: 'An illustrative seven-day forecast is ready to review.', channel: 'in_app', status: 'Unread', created_at: '2026-10-31T09:42:00+05:30' },
  { id: 'preview-notice-03', title: 'Purchase receipt recorded', body: 'A sample delivery was marked as received for visual development.', channel: 'in_app', status: 'Read', created_at: '2026-10-30T16:10:00+05:30' },
];

export const recommendationsPreview: BusinessRecommendation[] = [
  { id: 'preview-rec-01', recommendation_type: 'reorder', target_type: 'ingredient', target_id: 'preview-oat-milk', summary: 'Review an oat milk reorder', rationale: 'Illustrative stock cover is below the sample supplier lead time. Review current stock and the supplier quote before placing an order.', status: 'pending', provenance: { source: 'rule_based_preview' } },
  { id: 'preview-rec-02', recommendation_type: 'demand_preparation', target_type: 'category', target_id: 'preview-bakery', summary: 'Prepare for a busier bakery weekend', rationale: 'The demonstration demand series is higher toward the end of the week. Compare it with recorded sales before changing production.', status: 'pending', provenance: { source: 'forecast_preview' } },
  { id: 'preview-rec-03', recommendation_type: 'investigation', target_type: 'supplier', target_id: 'preview-green-basket', summary: 'Review a sample supplier price change', rationale: 'A demonstration catalog price differs from the previous sample observation. Confirm the current offer with the supplier.', status: 'pending', provenance: { source: 'supplier_price_rule_preview' } },
];
