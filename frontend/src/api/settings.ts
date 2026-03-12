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
