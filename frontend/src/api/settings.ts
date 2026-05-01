import client from './client';
import type { SettingsResponse, SettingsUpdate } from '../types';

export async function getSettings(): Promise<SettingsResponse> {
  const response = await client.get<SettingsResponse>('/settings');
  return response.data;
}

export async function updateSettings(data: SettingsUpdate): Promise<SettingsResponse> {
  const response = await client.put<SettingsResponse>('/settings', data);
  return response.data;
}

export interface MetaSyncNowResponse {
  started: boolean;
  days_back: number;
  granular: boolean;
  message: string;
}

export interface MetaSyncStatus {
  run_id?: string;
  started_at?: string;
  finished_at?: string | null;
  in_progress?: boolean;
  days_back?: number;
  granular?: boolean;
  summary?: {
    campaigns_imported?: number | null;
    campaigns_synced?: number | null;
    adsets_synced?: number | null;
    ads_synced?: number | null;
    dates_updated?: number | null;
    total_spend?: number | null;
    errors?: string[] | null;
  } | null;
  message?: string;
}

export async function syncMetaNow(
  days_back = 7,
  granular = true,
  source_type?: 'paid' | 'organic',
): Promise<MetaSyncNowResponse> {
  const response = await client.post<MetaSyncNowResponse>(
    '/settings/meta/sync-now',
    { days_back, granular, source_type: source_type ?? null },
  );
  return response.data;
}

export async function getMetaSyncStatus(): Promise<MetaSyncStatus> {
  const response = await client.get<MetaSyncStatus>('/settings/meta/sync-status');
  return response.data;
}

export interface HyrosSyncResult {
  subscribers_scanned: number;
  sales_scanned: number;
  matched_by_email: number;
  matched_by_name: number;
  matched_by_origin_lead: number;
  total_matched: number;
  purchases_found: number;
  unmatched_hyros_leads: number;
  skipped?: boolean;
  skip_reason?: string;
}

export async function syncHyrosNow(): Promise<HyrosSyncResult> {
  const response = await client.post<HyrosSyncResult>('/settings/hyros/sync');
  return response.data;
}

export interface AdLookupResult {
  ad_id: string;
  campaign_id: string;
}

export async function lookupAdCampaignId(adId: string): Promise<AdLookupResult> {
  const response = await client.get<AdLookupResult>(
    `/settings/meta/lookup-ad?ad_id=${encodeURIComponent(adId)}`
  );
  return response.data;
}
