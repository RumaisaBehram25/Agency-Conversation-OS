import { describe, expect, it } from 'vitest';
import { resolveTotalConversations } from './analyticsScope';

describe('resolveTotalConversations', () => {
  it('uses analytics total for all/paid scopes', () => {
    expect(resolveTotalConversations(81, null)).toBe(81);
    expect(resolveTotalConversations(4, undefined)).toBe(4);
  });

  it('uses organic total when provided', () => {
    expect(resolveTotalConversations(81, 77)).toBe(77);
  });
});

