import client from './client';

export interface AITestChatRequest {
  subscriber_id: string;
  message: string;
  channel?: string;
  custom_fields?: Record<string, unknown> | null;
}

export interface AITestChatResponse {
  response_text: string;
  buyer_stage: string;
  model_used: string | null;
  response_time_ms: number | null;
  quick_replies: string[];
  conversion_ready: boolean;
  needs_human_handoff: boolean;
  handoff_reason: string | null;
  compliance_flags: string[];
  attora_campaign_id: string | null;
  subscriber_tagged_urls: Record<string, string>;
}

export interface AITestResetResponse {
  deleted_conversations: number;
  deleted_messages: number;
  subscriber_reset: boolean;
}

export async function aiTestChat(
  payload: AITestChatRequest,
): Promise<AITestChatResponse> {
  const response = await client.post<AITestChatResponse>(
    '/ai-test/chat',
    payload,
  );
  return response.data;
}

export async function aiTestReset(
  subscriber_id: string,
): Promise<AITestResetResponse> {
  const response = await client.post<AITestResetResponse>('/ai-test/reset', {
    subscriber_id,
  });
  return response.data;
}
