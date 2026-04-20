import apiClient from './client';
import type { AdCampaign, CampaignUTM, CampaignCreate, CampaignUpdate, UTMGenerateRequest } from '../types';

export async function getCampaigns(params?: { is_attora_managed?: boolean; is_active?: boolean }): Promise<AdCampaign[]> {
  const { data } = await apiClient.get('/campaigns', { params });
  return data;
}

export async function createCampaign(payload: CampaignCreate): Promise<AdCampaign> {
  const { data } = await apiClient.post('/campaigns', payload);
  return data;
}

export async function updateCampaign(id: string, payload: CampaignUpdate): Promise<AdCampaign> {
  const { data } = await apiClient.put(`/campaigns/${id}`, payload);
  return data;
}

export async function deleteCampaign(id: string): Promise<void> {
  await apiClient.delete(`/campaigns/${id}`);
}

export async function generateUTMs(id: string, payload: UTMGenerateRequest): Promise<CampaignUTM> {
  const { data } = await apiClient.post(`/campaigns/${id}/generate-utms`, payload);
  return data;
}
