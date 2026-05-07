export function resolveTotalConversations(
  analyticsTotalConversations: number,
  organicTotalConversations?: number | null
): number {
  if (organicTotalConversations != null) {
    return organicTotalConversations;
  }
  return analyticsTotalConversations;
}

