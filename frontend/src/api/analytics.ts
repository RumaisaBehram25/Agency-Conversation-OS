import client from './client';
import type { AnalyticsResponse, ROIResponse, AIPerformanceResponse } from '../types';

export interface AnalyticsFilters {
  date_from?: string;
  date_to?: string;
  channel?: string;
}

export async function getAnalytics(
  filters: AnalyticsFilters = {}
): Promise<AnalyticsResponse> {
  const params = new URLSearchParams();
  if (filters.date_from) params.set('date_from', filters.date_from);
  if (filters.date_to) params.set('date_to', filters.date_to);
  if (filters.channel) params.set('channel', filters.channel);

  const response = await client.get<AnalyticsResponse>(
    `/analytics?${params.toString()}`
  );
  return response.data;
}

export async function getROI(filters: {
  date_from?: string;
  date_to?: string;
} = {}): Promise<ROIResponse> {
  const params = new URLSearchParams();
  if (filters.date_from) params.set('date_from', filters.date_from);
  if (filters.date_to) params.set('date_to', filters.date_to);

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

export function getExportUrl(filters: AnalyticsFilters = {}): string {
  const params = new URLSearchParams();
  if (filters.date_from) params.set('date_from', filters.date_from);
  if (filters.date_to) params.set('date_to', filters.date_to);
  if (filters.channel) params.set('channel', filters.channel);
  return `/api/analytics/export?${params.toString()}`;
}
