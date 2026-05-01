import client from './client';
import type {
  AdCampaign,
  AdCampaignCreate,
  AdCampaignUpdate,
  AdSetSummary,
  AdSummary,
  BreakdownItem,
  CampaignSourceType,
  CampaignSummary,
  CampaignUTM,
  UTMGenerateRequest,
} from '../types';

// ─── Attora-managed Ad Campaigns (CRUD + UTM) ───────────────────────────────

export async function listAdCampaigns(
  params: {
    is_attora_managed?: boolean;
    is_active?: boolean;
    source_type?: CampaignSourceType;
  } = {}
): Promise<AdCampaign[]> {
  const qs = new URLSearchParams();
  if (params.is_attora_managed !== undefined)
    qs.set('is_attora_managed', String(params.is_attora_managed));
  if (params.is_active !== undefined) qs.set('is_active', String(params.is_active));
  if (params.source_type !== undefined) qs.set('source_type', params.source_type);

  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  const response = await client.get<AdCampaign[]>(`/campaigns${suffix}`);
  return response.data;
}

export async function createAdCampaign(payload: AdCampaignCreate): Promise<AdCampaign> {
  const response = await client.post<AdCampaign>('/campaigns', payload);
  return response.data;
}

export async function getAdCampaign(campaignId: string): Promise<AdCampaign> {
  const response = await client.get<AdCampaign>(`/campaigns/${campaignId}`);
  return response.data;
}

export async function updateAdCampaign(
  campaignId: string,
  payload: AdCampaignUpdate
): Promise<AdCampaign> {
  const response = await client.patch<AdCampaign>(`/campaigns/${campaignId}`, payload);
  return response.data;
}

export async function deleteAdCampaign(campaignId: string): Promise<void> {
  await client.delete(`/campaigns/${campaignId}`);
}

export async function generateCampaignUtms(
  campaignId: string,
  payload: UTMGenerateRequest
): Promise<CampaignUTM> {
  const response = await client.post<CampaignUTM>(
    `/campaigns/${campaignId}/generate-utms`,
    payload
  );
  return response.data;
}

export async function getCampaignUtmForSubscriber(
  campaignId: string,
  subscriberId: string
): Promise<CampaignUTM> {
  const qs = new URLSearchParams({ subscriber_id: subscriberId });
  const response = await client.get<CampaignUTM>(
    `/campaigns/${campaignId}/utm-for-subscriber?${qs.toString()}`
  );
  return response.data;
}

// ─── Campaign Metrics (Meta drill-down) ─────────────────────────────────────

export async function getCampaigns(
  params: { date_from?: string; date_to?: string; source_type?: string } = {}
): Promise<CampaignSummary[]> {
  const qs = new URLSearchParams();
  if (params.date_from) qs.set('date_from', params.date_from);
  if (params.date_to) qs.set('date_to', params.date_to);
  if (params.source_type) qs.set('source_type', params.source_type);

  const response = await client.get<CampaignSummary[]>(
    `/campaign-metrics?${qs.toString()}`
  );
  return response.data;
}

export async function getCampaignAdSets(
  campaignId: string,
  params?: { date_from?: string; date_to?: string }
): Promise<AdSetSummary[]> {
  const qs = new URLSearchParams();
  if (params?.date_from) qs.set('date_from', params.date_from);
  if (params?.date_to) qs.set('date_to', params.date_to);

  const response = await client.get<AdSetSummary[]>(
    `/campaign-metrics/${campaignId}/adsets?${qs.toString()}`
  );
  return response.data;
}

export async function getAdSetAds(
  campaignId: string,
  adsetId: string,
  params?: { date_from?: string; date_to?: string }
): Promise<AdSummary[]> {
  const qs = new URLSearchParams();
  if (params?.date_from) qs.set('date_from', params.date_from);
  if (params?.date_to) qs.set('date_to', params.date_to);

  const response = await client.get<AdSummary[]>(
    `/campaign-metrics/${campaignId}/adsets/${adsetId}/ads?${qs.toString()}`
  );
  return response.data;
}

export async function getCampaignBreakdowns(
  campaignId: string,
  type: 'age_gender' | 'platform',
  params?: { date_from?: string; date_to?: string }
): Promise<BreakdownItem[]> {
  const qs = new URLSearchParams();
  qs.set('type', type);
  if (params?.date_from) qs.set('date_from', params.date_from);
  if (params?.date_to) qs.set('date_to', params.date_to);

  const response = await client.get<BreakdownItem[]>(
    `/campaign-metrics/${campaignId}/breakdowns?${qs.toString()}`
  );
  return response.data;
}
