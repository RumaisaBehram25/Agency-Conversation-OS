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

export async function syncMetaNow(
  days_back = 7,
  granular = true,
): Promise<MetaSyncNowResponse> {
  const response = await client.post<MetaSyncNowResponse>(
    '/settings/meta/sync-now',
    { days_back, granular },
  );
  return response.data;
}
