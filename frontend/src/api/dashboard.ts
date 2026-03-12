import client from './client';
import type { DashboardResponse } from '../types';

export async function getDashboard(): Promise<DashboardResponse> {
  const response = await client.get<DashboardResponse>('/dashboard');
  return response.data;
}
