// Shapes returned by the FastAPI backend.

export interface DashboardSummary {
  username: string;
  today: string;
  current_month: string;
  total_sales: number;
  total_expenses: number;
  net_profit: number;
  total_outstanding: number;
  outstanding_sale_count: number;
  month_income: number;
  month_expenses: number;
  month_net: number;
  income_note: string;
  expense_note: string;
  net_note: string;
  today_collected: number;
  today_expenses: number;
  today_net: number;
  low_stock_items: { item_name: string; stock: number; threshold: number }[];
}

export interface Sale {
  id: number;
  description: string;
  total_value: number;
  amount_paid: number;
  balance_owed: number;
  customer_name: string;
  payment_mode: string;
  date: string;
  receipt_id: string;
  checkout_id: string | null;
  checkout_line_id: string | null;
  inventory_item_id: number | null;
  quantity: number;
  unit_price: number;
  sale_type: "unit" | "bulk";
  bundle_count: number | null;
  bundle_size: number | null;
}

export interface Expense {
  server_id: number;
  amount: number;
  category: string;
  description: string;
  date: string;
  synced: boolean;
}

export interface Product {
  id: number;
  item_name: string;
  price: number;
  stock: number;
  track_stock: boolean;
  low_stock_threshold: number;
  bulk_quantity: number | null;
  bulk_price: number | null;
  image_url?: string | null;
}

export interface BusinessProfile {
  id?: number;
  company_name: string;
  business_phone: string;
  business_address: string;
  instagram_handle: string;
  whatsapp_number: string;
  store_policy: string;
  brand_color: string;
  logo_url: string;
  store_slug: string;
  profile_updated_at: string;
  profile_change_reason: string;
  profile_change_note: string;
}

export interface CheckoutLine {
  inventory_item_id: number | null;
  quantity: number;
  unit_price?: number;
  item_name?: string;
  sale_type?: "unit" | "bulk";
  checkout_line_id?: string;
}
