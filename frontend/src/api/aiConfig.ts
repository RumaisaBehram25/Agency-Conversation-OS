import client from './client';
import type { AIConfig, AIConfigUpdate } from '../types';

export async function getAIConfig(): Promise<AIConfig> {
  const response = await client.get<AIConfig>('/ai-config');
  return response.data;
}

export async function updateAIConfig(data: AIConfigUpdate): Promise<AIConfig> {
  const response = await client.put<AIConfig>('/ai-config', data);
  return response.data;
}
