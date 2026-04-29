import client from './client';
import type {
  AnalyticsResponse,
  ROIResponse,
  AIPerformanceResponse,
  ManyChatFlowStatsResponse,
} from '../types';

export interface AnalyticsFilters {
  date_from?: string;
  date_to?: string;
  channel?: string;
  campaign_id?: string;
  organic?: boolean;
}

export async function getAnalytics(
  filters: AnalyticsFilters = {}
): Promise<AnalyticsResponse> {
  const params = new URLSearchParams();
  if (filters.date_from) params.set('date_from', filters.date_from);
  if (filters.date_to) params.set('date_to', filters.date_to);
  if (filters.channel) params.set('channel', filters.channel);
  if (filters.campaign_id) params.set('campaign_id', filters.campaign_id);
  if (filters.organic) params.set('organic', 'true');

  const response = await client.get<AnalyticsResponse>(
    `/analytics?${params.toString()}`
  );
  return response.data;
}

export async function getROI(filters: {
  date_from?: string;
  date_to?: string;
  campaign_id?: string;
} = {}): Promise<ROIResponse> {
  const params = new URLSearchParams();
  if (filters.date_from) params.set('date_from', filters.date_from);
  if (filters.date_to) params.set('date_to', filters.date_to);
  if (filters.campaign_id) params.set('campaign_id', filters.campaign_id);

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

export async function getManyChatFlowStats(channel: 'all' | 'instagram' | 'messenger' = 'all'): Promise<ManyChatFlowStatsResponse> {
  const params = new URLSearchParams();
  params.set('channel', channel);
  const response = await client.get<ManyChatFlowStatsResponse>(
    `/analytics/manychat-flow-stats?${params.toString()}`
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
