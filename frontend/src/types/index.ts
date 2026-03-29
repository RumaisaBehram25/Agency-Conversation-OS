// ─── Auth ────────────────────────────────────────────────────────────────────

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user_id: string;
  email: string;
}

export interface RefreshResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  org_id: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

// ─── Products ────────────────────────────────────────────────────────────────

export interface Product {
  id: string;
  org_id: string;
  name: string;
  description: string;
  price: number;
  conversion_value: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProductCreate {
  name: string;
  description: string;
  price: number;
  conversion_value: number;
  is_active?: boolean;
}

export interface ProductUpdate {
  name?: string;
  description?: string;
  price?: number;
  conversion_value?: number;
  is_active?: boolean;
}

// ─── AI Config ───────────────────────────────────────────────────────────────

export interface AIConfig {
  id: string;
  org_id: string;
  brand_voice: string;
  product_knowledge: string;
  compliance_rules: string;
  greeting_message: string;
  conversion_playbook: string;
  fallback_message: string;
  objection_handlers: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface AIConfigUpdate {
  brand_voice?: string;
  product_knowledge?: string;
  compliance_rules?: string;
  greeting_message?: string;
  conversion_playbook?: string;
  fallback_message?: string;
  objection_handlers?: Record<string, string>;
}

// ─── Conversations ───────────────────────────────────────────────────────────

export interface ConversationListItem {
  id: string;
  subscriber_id: string;
  subscriber_name: string;
  channel: string;
  status: string;
  buyer_stage: string;
  last_message_preview: string;
  last_message_at: string;
  message_count: number;
  created_at: string;
}

export interface ConversationMessage {
  id: string;
  conversation_id: string;
  sender_type: string; // 'user' | 'ai' | 'system'
  content: string;
  buyer_stage: string;
  compliance_flags: string[];
  intent: string;
  created_at: string;
}

export interface ConversationDetail {
  id: string;
  subscriber_id: string;
  subscriber_name: string;
  subscriber_channel: string;
  channel: string;
  status: string;
  buyer_stage: string;
  products_discussed: string[];
  messages: ConversationMessage[];
  created_at: string;
  updated_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ─── Subscribers ─────────────────────────────────────────────────────────────

export interface SubscriberListItem {
  id: string;
  first_name: string | null;
  last_name: string | null;
  channel: string;
  buyer_stage: string;
  is_converted: boolean;
  conversion_value: number | null;
  total_messages: number;
  first_message_at: string | null;
  last_message_at: string | null;
  created_at: string;
}

export interface SubscriberConversation {
  id: string;
  channel: string;
  status: string;
  message_count: number;
  started_at: string | null;
  last_activity_at: string | null;
}

export interface SubscriberDetail {
  id: string;
  manychat_subscriber_id: string;
  channel: string;
  first_name: string | null;
  last_name: string | null;
  phone: string | null;
  email: string | null;
  buyer_stage: string;
  interests: string[] | null;
  objections_raised: string[] | null;
  conversation_summary: string | null;
  is_converted: boolean;
  conversion_value: number | null;
  converted_at: string | null;
  first_message_at: string | null;
  last_message_at: string | null;
  total_messages: number;
  created_at: string;
  updated_at: string;
  conversations: SubscriberConversation[];
}

// ─── Campaigns ──────────────────────────────────────────────────────────────

export interface CampaignSummary {
  meta_campaign_id: string;
  meta_campaign_name: string | null;
  status: string | null;
  spend: number;
  impressions: number;
  clicks: number;
  leads: number;
  link_clicks: number;
  video_views: number;
  cpc: number | null;
  cpm: number | null;
  ctr: number | null;
}

export interface AdSetSummary {
  meta_adset_id: string;
  meta_adset_name: string | null;
  status: string | null;
  spend: number;
  impressions: number;
  clicks: number;
  leads: number;
  link_clicks: number;
  video_views: number;
  cpc: number | null;
  cpm: number | null;
  ctr: number | null;
}

export interface AdSummary {
  meta_ad_id: string;
  meta_ad_name: string | null;
  status: string | null;
  spend: number;
  impressions: number;
  clicks: number;
  leads: number;
  link_clicks: number;
  video_views: number;
  cpc: number | null;
  cpm: number | null;
  ctr: number | null;
}

// ─── Breakdowns ─────────────────────────────────────────────────────────────

export interface BreakdownItem {
  breakdown_key: string;
  spend: number;
  impressions: number;
  clicks: number;
  leads: number;
}

// ─── Analytics ───────────────────────────────────────────────────────────────

export interface DailyTrend {
  date: string;
  value: number;
}

export interface FunnelStep {
  name: string;
  volume: number;
  drop_off_rate: number | null;
}

export interface AnalyticsResponse {
  cpqc: number;
  ccr: number;
  avg_response_time_ms: number;
  qualification_rate: number;
  total_conversations: number;
  total_conversions: number;
  total_revenue: number;
  funnel: FunnelStep[];
  cpqc_trend: DailyTrend[];
  ccr_trend: DailyTrend[];
}

export interface ROIResponse {
  ad_spend: number;
  conversations_count: number;
  cost_per_conversation: number;
  qualified_count: number;
  cost_per_qualified: number;
  converted_count: number;
  cpa: number;
  revenue: number;
  roas: number;
  baseline_cpa: number;
  current_cpa: number;
}

export interface AIPerformanceResponse {
  fallback_rate: number;
  fallback_trend: DailyTrend[];
  avg_response_time_ms: number;
  total_ai_tokens: number;
  total_ai_cost: number;
}

// ─── Dashboard ───────────────────────────────────────────────────────────────

export interface CampaignHealth {
  campaign_name: string;
  status: 'healthy' | 'warning' | 'critical';
  metric: string;
  value: number;
}

export interface DashboardResponse {
  cpqc: number;
  cpqc_trend: DailyTrend[];
  ccr: number;
  ccr_trend: DailyTrend[];
  active_conversations_count: number;
  todays_conversions: number;
  todays_revenue: number;
  campaign_health: CampaignHealth[];
}

// ─── Settings ────────────────────────────────────────────────────────────────

export interface SettingsResponse {
  id: string;
  org_id: string;
  manychat_api_key: string;
  manychat_page_id: string;
  manychat_account_id: string;
  meta_pixel_id: string;
  meta_capi_token: string;
  meta_ad_account_id: string;
  meta_page_id: string;
  meta_business_manager_id: string;
  created_at: string;
  updated_at: string;
}

export interface SettingsUpdate {
  manychat_api_key?: string;
  manychat_page_id?: string;
  manychat_account_id?: string;
  meta_pixel_id?: string;
  meta_capi_token?: string;
  meta_ad_account_id?: string;
  meta_page_id?: string;
  meta_business_manager_id?: string;
}
