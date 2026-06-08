export type Role = "superadmin" | "agency_admin" | "agent";

export interface UserProfile {
  id: number;
  telegram_id: number;
  username?: string | null;
  full_name?: string | null;
  role: Role;
  is_owner: boolean;
  agency_id?: number | null;
}

export interface AuthResponse {
  access_token: string;
  refresh_token?: string | null;
  token_type: string;
  subscription_active?: boolean | null;
  user: UserProfile;
}

export interface Apartment {
  id: number;
  display_id: string;
  status: string;
  name?: string | null;
  owner_phone?: string | null;
  district?: string | null;
  address?: string | null;
  type?: string | null;
  rooms?: number | null;
  floor?: number | null;
  total_floors?: number | null;
  area?: number | null;
  land_area?: number | null;
  condition?: string | null;
  furniture_appliances?: string | null;
  price?: number | null;
  currency: string;
  description?: string | null;
  comment?: string | null;
  photo_url?: string | null;
  source_link?: string | null;
  created_by?: number | null;
  created_by_name?: string | null;
  created_at: string;
  updated_at: string;
  archived_at?: string | null;
  deleted_at?: string | null;
}

export interface ApartmentList {
  items: Apartment[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApartmentStats {
  active: number;
  deposit: number;
  sold: number;
  total: number;
}

export interface ApartmentEvent {
  action: string;
  note?: string | null;
  user_name?: string | null;
  created_at: string;
}

export interface AgentActivity {
  user_id?: number | null;
  name?: string | null;
  total: number;
  sold: number;
}

export interface ApartmentAnalytics {
  active: number;
  deposit: number;
  sold: number;
  total: number;
  added_this_month: number;
  sold_this_month: number;
  agents: AgentActivity[];
}

export interface TimeseriesPoint {
  label: string;
  added: number;
  sold: number;
}

export interface Timeseries {
  period: string;
  buckets: TimeseriesPoint[];
}

export interface AgentEvent {
  display_id: string;
  action: string;
  note?: string | null;
  created_at: string;
}

export interface AgencyOut {
  id: number;
  name: string;
  project_name?: string | null;
  status: string;
  subscription_expires_at?: string | null;
  activated_at?: string | null;
  created_at: string;
  admin_telegram_id?: number | null;
  admin_name?: string | null;
}

export interface AgencySettings {
  id: number;
  name: string;
  project_name?: string | null;
  status: string;
  subscription_expires_at?: string | null;
  timezone: string;
  default_currency: string;
  contact_phone?: string | null;
  contact_username?: string | null;
}

export interface Member {
  id: number;
  telegram_id: number;
  username?: string | null;
  full_name?: string | null;
  role: Role;
  is_owner: boolean;
  is_active: boolean;
}

export interface Invite {
  id: number;
  code: string;
  role: string;
  status: string;
  join_link?: string | null;
  expires_at: string;
  used_at?: string | null;
  used_by_telegram_id?: number | null;
  created_at: string;
}

// Результат предпросмотра импорта объявления по ссылке (AI-разбор).
export interface ListingImport {
  name?: string | null;
  type?: string | null;
  district?: string | null;
  address?: string | null;
  rooms?: number | null;
  floor?: number | null;
  total_floors?: number | null;
  land_area?: number | null;
  area?: number | null;
  condition?: string | null;
  furniture_appliances?: string | null;
  price?: number | null;
  currency?: string | null;
  owner_phone?: string | null;
  description?: string | null;
  source_link?: string | null;
  photo_urls: string[];
  warnings: string[];
}

export interface DictItem {
  id: number;
  category: string;
  value: string;
  sort_order: number;
  is_active: boolean;
}

export interface ApartmentPhoto {
  id: number;
  url: string;
  sort_order: number;
}

export interface SearchParams {
  status?: string;
  districts?: string[];
  types?: string[];
  rooms_min?: string | number;
  rooms_max?: string | number;
  floor_min?: string | number;
  floor_max?: string | number;
  land_area_min?: string | number;
  land_area_max?: string | number;
  price_min?: string | number;
  price_max?: string | number;
  currency?: string;
  created_by?: string | number;
  created_from?: string;
  created_to?: string;
  q?: string;
  [k: string]: unknown;
}

// История платежей/продлений подписки агентства (для владельца платформы).
export interface AgencyPayment {
  id: number;
  action: string;
  days?: number | null;
  amount?: number | null;
  currency?: string | null;
  method?: string | null;
  note?: string | null;
  created_at: string;
}

export interface CurrencyTotal {
  currency: string;
  amount: number;
  count: number;
}

// Свод платежей по всем агентствам.
export interface PaymentsSummary {
  all_time: CurrencyTotal[];
  this_month: CurrencyTotal[];
  total_records: number;
}
