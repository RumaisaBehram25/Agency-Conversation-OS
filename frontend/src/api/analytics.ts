import client from './client';
import type { AnalyticsResponse, ROIResponse, AIPerformanceResponse } from '../types';

export interface AnalyticsFilters {
  date_from?: string;
  date_to?: string;
  channel?: string;
  campaign_id?: string;
  attora_campaign_id?: string;
  source_type?: 'paid' | 'organic';
}

export async function getAnalytics(
  filters: AnalyticsFilters = {}
): Promise<AnalyticsResponse> {
  const params = new URLSearchParams();
  if (filters.date_from) params.set('date_from', filters.date_from);
  if (filters.date_to) params.set('date_to', filters.date_to);
  if (filters.channel) params.set('channel', filters.channel);
  if (filters.campaign_id) params.set('campaign_id', filters.campaign_id);
  if (filters.attora_campaign_id)
    params.set('attora_campaign_id', filters.attora_campaign_id);
  if (filters.source_type) params.set('source_type', filters.source_type);

  const response = await client.get<AnalyticsResponse>(
    `/analytics?${params.toString()}`
  );
  return response.data;
}

export async function getROI(filters: {
  date_from?: string;
  date_to?: string;
  campaign_id?: string;
  attora_campaign_id?: string;
  source_type?: 'paid' | 'organic';
} = {}): Promise<ROIResponse> {
  const params = new URLSearchParams();
  if (filters.date_from) params.set('date_from', filters.date_from);
  if (filters.date_to) params.set('date_to', filters.date_to);
  if (filters.campaign_id) params.set('campaign_id', filters.campaign_id);
  if (filters.attora_campaign_id)
    params.set('attora_campaign_id', filters.attora_campaign_id);
  if (filters.source_type) params.set('source_type', filters.source_type);

  const response = await client.get<ROIResponse>(`/analytics/roi?${params.toString()}`);
  return response.data;
}

export async function getAIPerformance(filters: {
  date_from?: string;
  date_to?: string;
} = {}): Promise<AIPerformanceResponse> {
  const params = new URLSearchParams();
  if (filters.date_from) params.set('date_from', filters.date_from);
  if (filters.date_to) params.set('date_to', filters.date_to);

  const response = await client.get<AIPerformanceResponse>(
    `/analytics/ai-performance?${params.toString()}`
  );
  return response.data;
}

export interface OrganicKeywordStats {
  total_conversations: number;
  total_conversions: number;
  total_revenue: number;
  funnel_conversations: number;
  funnel_qualified: number;
  funnel_converted: number;
}

export async function getOrganicKeywordStats(filters: {
  date_from?: string;
  date_to?: string;
  keyword?: string;
} = {}): Promise<OrganicKeywordStats> {
  const params = new URLSearchParams();
  if (filters.date_from) params.set('date_from', filters.date_from);
  if (filters.date_to) params.set('date_to', filters.date_to);
  if (filters.keyword) params.set('keyword', filters.keyword);
  const response = await client.get<OrganicKeywordStats>(
    `/analytics/organic-keyword-stats?${params.toString()}`
  );
  return response.data;
}

export function getExportUrl(filters: AnalyticsFilters = {}): string {
  const params = new URLSearchParams();
  if (filters.date_from) params.set('date_from', filters.date_from);
  if (filters.date_to) params.set('date_to', filters.date_to);
  if (filters.channel) params.set('channel', filters.channel);
  return `/api/analytics/export?${params.toString()}`;
}
