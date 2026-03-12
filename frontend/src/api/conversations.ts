import client from './client';
import type { ConversationListItem, ConversationDetail, PaginatedResponse } from '../types';

export interface ConversationFilters {
  status?: string;
  channel?: string;
  date_from?: string;
  date_to?: string;
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
