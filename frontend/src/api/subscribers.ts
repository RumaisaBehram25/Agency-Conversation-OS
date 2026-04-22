import client from './client';
import type { SubscriberListItem, SubscriberDetail, PaginatedResponse } from '../types';

export interface SubscriberFilters {
  buyer_stage?: string;
  channel?: string;
  date_from?: string;
  date_to?: string;
  is_converted?: boolean;
  page?: number;
  page_size?: number;
}

export async function getSubscribers(
  filters: SubscriberFilters = {}
): Promise<PaginatedResponse<SubscriberListItem>> {
  const params = new URLSearchParams();
  if (filters.buyer_stage) params.set('buyer_stage', filters.buyer_stage);
  if (filters.channel) params.set('channel', filters.channel);
  if (filters.date_from) params.set('date_from', filters.date_from);
  if (filters.date_to) params.set('date_to', filters.date_to);
  if (filters.is_converted !== undefined)
    params.set('is_converted', String(filters.is_converted));
  if (filters.page) params.set('page', String(filters.page));
  if (filters.page_size) params.set('page_size', String(filters.page_size));

  const response = await client.get<PaginatedResponse<SubscriberListItem>>(
    `/subscribers?${params.toString()}`
  );
  return response.data;
}

export async function getSubscriber(id: string): Promise<SubscriberDetail> {
  const response = await client.get<SubscriberDetail>(`/subscribers/${id}`);
  return response.data;
}

export async function deleteSubscriber(id: string): Promise<void> {
  await client.delete(`/subscribers/${id}`);
}
