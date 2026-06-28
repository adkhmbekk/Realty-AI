export type Role = "superadmin" | "agency_admin" | "agent";

export interface UserProfile {
  id: number;
  telegram_id: number;
  username?: string | null;
  full_name?: string | null;
  role: Role;
  is_owner: boolean;
  agency_id?: number | null;
  // Acting-контекст: суперадмин работает внутри своего личного агентства.
  // real_role === "superadmin" + acting_as_agency_id → показываем баннер «Выйти».
  acting_as_agency_id?: number | null;
  acting_as_agency_name?: string | null;
  real_role?: string | null;
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
  // Тип сделки: "sale" (продажа) | "rent" (аренда). Срок аренды: "month" | "day".
  deal_type?: string | null;
  rent_period?: string | null;
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
  source?: string | null;
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
  // Личное агентство владельца платформы (если задано — это «моё»).
  owner_telegram_id?: number | null;
  // Телефон человека, открывшего агентство (необязательный, виден владельцу).
  client_phone?: string | null;
  admin_telegram_id?: number | null;
  admin_name?: string | null;
}

// Ссылка активации агентства (создание «по ссылке»).
export interface Activation {
  code: string;
  link?: string | null;
  expires_at: string;
  status: string; // active | expired | used
}

export interface AgencyDraftOut {
  agency: AgencyOut;
  activation: Activation;
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
  support_url?: string | null;
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
  deal_type?: string | null;
  rent_period?: string | null;
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
  // Источник: "@канал" для Telegram (как в массовом импорте) или домен площадки.
  source?: string | null;
  photo_urls: string[];
  warnings: string[];
}

// Статус подключения Google-таблицы агентства.
export interface SheetStatus {
  connected: boolean;
  status: string;
  has_spreadsheet: boolean;
  spreadsheet_url?: string | null;
  sheet_title?: string | null;
  error_note?: string | null;
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
  deal_type?: string;
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

// ── Клиентская база ──────────────────────────────────────────────────
export interface ClientRequest {
  id: number;
  client_id: number;
  deal_type?: string | null;
  types?: string[] | null;
  districts?: string[] | null;
  rooms_min?: number | null;
  rooms_max?: number | null;
  floor_min?: number | null;
  floor_max?: number | null;
  land_area_min?: number | null;
  land_area_max?: number | null;
  price_min?: number | null;
  price_max?: number | null;
  currency?: string | null;
  note?: string | null;
  status: string;
  created_at: string;
  match_count: number;
  new_match_count: number;
}

export interface Client {
  id: number;
  name: string;
  last_name?: string | null;
  phone?: string | null;
  note?: string | null;
  status: string;
  created_by?: number | null;
  created_by_name?: string | null;
  created_at: string;
  requests: ClientRequest[];
  active_requests: number;
  new_match_count: number;
}

export interface Match {
  id: number;
  status: string;
  created_at: string;
  request_id: number;
  client_id: number;
  client_name: string;
  request_label?: string | null;
  apartment: Apartment;
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

// ── Наблюдение за агентствами (использование) ───────────────────────
export interface AgencyUsage {
  agency_id: number;
  objects_total: number;
  added_today: number;
  added_7d: number;
  added_30d: number;
  logins_7d: number;
  active_users: number;
  total_users: number;
  last_activity_at?: string | null;
  engagement: string; // active | quiet | asleep | new
}

export interface DailyCount {
  date: string; // YYYY-MM-DD
  added: number;
}

export interface EmployeeActivity {
  user_id?: number | null;
  name?: string | null;
  last_login_at?: string | null;
  added: number;
}

export interface AgencyActivity {
  objects_total: number;
  active: number;
  deposit: number;
  sold: number;
  rented: number;
  sale: number;
  rent: number;
  added_today: number;
  added_yesterday: number;
  added_2d: number;
  added_7d: number;
  added_30d: number;
  daily: DailyCount[];
  source_manual: number;
  source_link: number;
  source_channel: number;
  logins_7d: number;
  logins_30d: number;
  active_users: number;
  total_users: number;
  last_activity_at?: string | null;
  employees: EmployeeActivity[];
}

// Свод платежей по всем агентствам.
export interface PaymentsSummary {
  all_time: CurrencyTotal[];
  this_month: CurrencyTotal[];
  total_records: number;
}
