import client from './client';
import type { CampaignSummary, AdSetSummary, AdSummary, BreakdownItem } from '../types';

export async function getCampaigns(
  params: { date_from?: string; date_to?: string } = {}
): Promise<CampaignSummary[]> {
  const qs = new URLSearchParams();
  if (params.date_from) qs.set('date_from', params.date_from);
  if (params.date_to) qs.set('date_to', params.date_to);

  const response = await client.get<CampaignSummary[]>(
    `/campaigns?${qs.toString()}`
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
    `/campaigns/${campaignId}/adsets?${qs.toString()}`
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
    `/campaigns/${campaignId}/adsets/${adsetId}/ads?${qs.toString()}`
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
    `/campaigns/${campaignId}/breakdowns?${qs.toString()}`
  );
  return response.data;
}
