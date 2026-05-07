import client from './client';
import type { ConversationListItem, ConversationDetail, PaginatedResponse } from '../types';

export interface ConversationFilters {
  status?: string;
  channel?: string;
  date_from?: string;
  date_to?: string;
  is_test?: boolean;
  source_type?: 'paid' | 'organic';
  keywords?: string;
  campaign_id?: string;
  attora_campaign_id?: string;
  page?: number;
  page_size?: number;
}

export async function getConversations(
  filters: ConversationFilters = {}
): Promise<PaginatedResponse<ConversationListItem>> {
  const params = new URLSearchParams();
  if (filters.status) params.set('status', filters.status);
  if (filters.channel) params.set('channel', filters.channel);
  if (filters.date_from) params.set('date_from', filters.date_from);
  if (filters.date_to) params.set('date_to', filters.date_to);
  if (filters.is_test !== undefined) params.set('is_test', String(filters.is_test));
  if (filters.source_type) params.set('source_type', filters.source_type);
  if (filters.keywords) params.set('keywords', filters.keywords);
  if (filters.campaign_id) params.set('campaign_id', filters.campaign_id);
  if (filters.attora_campaign_id) params.set('attora_campaign_id', filters.attora_campaign_id);
  if (filters.page) params.set('page', String(filters.page));
  if (filters.page_size) params.set('page_size', String(filters.page_size));

  const response = await client.get<PaginatedResponse<ConversationListItem>>(
    `/conversations?${params.toString()}`
  );
  return response.data;
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const response = await client.get<ConversationDetail>(`/conversations/${id}`);
  return response.data;
}

export async function deleteConversation(id: string): Promise<void> {
  await client.delete(`/conversations/${id}`);
}
