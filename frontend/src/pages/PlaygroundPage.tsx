import { useEffect, useRef, useState } from 'react';
import {
  aiTestChat,
  aiTestReset,
  type AITestChatResponse,
} from '../api/aiTest';

interface Turn {
  role: 'user' | 'ai';
  text: string;
  meta?: AITestChatResponse;
  timestamp: number;
}

const DEFAULT_SUBSCRIBER_ID = 'attora_test';

export default function PlaygroundPage() {
  const [subscriberId, setSubscriberId] = useState(DEFAULT_SUBSCRIBER_ID);
  const [channel, setChannel] = useState('messenger');
  const [campaignId, setCampaignId] = useState('');
  const [attoraCampaignId, setAttoraCampaignId] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [error, setError] = useState('');
  const [expandedMeta, setExpandedMeta] = useState<Record<number, boolean>>({});

  const threadEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [turns]);

  async function handleSend() {
    const message = draft.trim();
    if (!message || sending) return;
    const subId = subscriberId.trim() || DEFAULT_SUBSCRIBER_ID;

    const userTurn: Turn = {
      role: 'user',
      text: message,
      timestamp: Date.now(),
    };
    setTurns((prev) => [...prev, userTurn]);
    setDraft('');
    setSending(true);
    setError('');

    const custom_fields: Record<string, unknown> = {};
    if (campaignId.trim()) custom_fields.campaign_id = campaignId.trim();
    if (attoraCampaignId.trim()) custom_fields.attora_campaign_id = attoraCampaignId.trim();

    try {
      const res = await aiTestChat({
        subscriber_id: subId,
        message,
        channel,
        custom_fields: Object.keys(custom_fields).length ? custom_fields : null,
      });
      setTurns((prev) => [
        ...prev,
        {
          role: 'ai',
          text: res.response_text,
          meta: res,
          timestamp: Date.now(),
        },
      ]);
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? ((err as { response?: { data?: { detail?: string } } }).response
              ?.data?.detail ?? null)
          : null;
      setError(detail ?? 'AI pipeline failed — check backend logs.');
    } finally {
      setSending(false);
    }
  }

  async function handleReset() {
    if (resetting) return;
    if (!confirm(`Wipe conversation history for "${subscriberId}"?`)) return;
    setResetting(true);
    setError('');
    try {
      await aiTestReset(subscriberId.trim() || DEFAULT_SUBSCRIBER_ID);
      setTurns([]);
      setExpandedMeta({});
    } catch {
      setError('Reset failed.');
    } finally {
      setResetting(false);
    }
  }

  function toggleMeta(index: number) {
    setExpandedMeta((prev) => ({ ...prev, [index]: !prev[index] }));
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col gap-4 pb-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">AI Playground</h1>
          <p className="mt-1 text-sm text-gray-500">
            Simulate a conversation with the AI without ManyChat. Exercises the
            full pipeline — product catalog, UTM injection, buyer-stage, fallbacks.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[320px_1fr]">
        {/* ── Test context sidebar ──────────────────────────────────── */}
        <div className="space-y-3 rounded-xl border border-gray-200 bg-white p-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-gray-600">
              Subscriber ID
            </label>
            <input
              type="text"
              value={subscriberId}
              onChange={(e) => setSubscriberId(e.target.value)}
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm"
              placeholder={DEFAULT_SUBSCRIBER_ID}
            />
            <p className="mt-1 text-[11px] text-gray-500">
              Auto-created if missing. Prefix <span className="font-mono">attora_test_</span>{' '}
              makes it easy to filter out of analytics.
            </p>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-gray-600">
              Channel
            </label>
            <select
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
              className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm"
            >
              <option value="messenger">messenger</option>
              <option value="instagram">instagram</option>
              <option value="whatsapp">whatsapp</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-gray-600">
              Attora campaign ID (organic)
            </label>
            <input
              type="text"
              value={attoraCampaignId}
              onChange={(e) => setAttoraCampaignId(e.target.value)}
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm font-mono text-xs"
              placeholder="c28c2864-c579-40c6-b81f-fcdaaabf5d1f"
            />
            <p className="mt-1 text-[11px] text-gray-500">
              Direct Attora campaign UUID — use this for organic campaigns (no Meta ID).
              Copy from the Campaigns page "Attora ID" column.
            </p>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-gray-600">
              Meta campaign ID (paid)
            </label>
            <input
              type="text"
              value={campaignId}
              onChange={(e) => setCampaignId(e.target.value)}
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm font-mono text-xs"
              placeholder="120245110890980659"
            />
            <p className="mt-1 text-[11px] text-gray-500">
              Meta campaign ID — for paid ads, looked up against registered Attora campaigns.
            </p>
          </div>

          <div className="border-t border-gray-100 pt-3">
            <button
              type="button"
              onClick={() => void handleReset()}
              disabled={resetting}
              className="w-full rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
            >
              {resetting ? 'Resetting…' : 'Reset conversation'}
            </button>
            <p className="mt-1 text-[11px] text-gray-500">
              Wipes messages + conversations, resets buyer stage. Subscriber row
              (+ campaign attribution) is kept.
            </p>
          </div>
        </div>

        {/* ── Chat thread ─────────────────────────────────────────── */}
        <div className="flex min-h-[500px] flex-col rounded-xl border border-gray-200 bg-white">
          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            {turns.length === 0 && (
              <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50 p-6 text-center text-sm text-gray-500">
                Send a message below to start. The AI runs through the same pipeline the
                ManyChat webhook does — including product catalog, UTM injection, buyer-stage
                classification.
              </div>
            )}

            {turns.map((turn, idx) => (
              <div
                key={idx}
                className={turn.role === 'user' ? 'flex justify-end' : 'flex justify-start'}
              >
                <div
                  className={
                    turn.role === 'user'
                      ? 'max-w-[80%] rounded-2xl rounded-br-sm bg-primary-600 px-4 py-2 text-sm text-white'
                      : 'max-w-[80%] space-y-2'
                  }
                >
                  {turn.role === 'ai' ? (
                    <>
                      <div className="rounded-2xl rounded-bl-sm bg-gray-100 px-4 py-2 text-sm text-gray-900 whitespace-pre-wrap">
                        {turn.text}
                      </div>
                      {turn.meta?.quick_replies && turn.meta.quick_replies.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {turn.meta.quick_replies.map((qr, i) => (
                            <span
                              key={i}
                              className="rounded-full border border-gray-300 bg-white px-2.5 py-0.5 text-xs text-gray-700"
                            >
                              {qr}
                            </span>
                          ))}
                        </div>
                      )}
                      {turn.meta && (
                        <div>
                          <button
                            type="button"
                            onClick={() => toggleMeta(idx)}
                            className="text-[11px] font-medium text-gray-500 hover:text-gray-700"
                          >
                            {expandedMeta[idx] ? '▼ Hide debug' : '▶ Show debug'}
                          </button>
                          {expandedMeta[idx] && (
                            <div className="mt-1 space-y-1 rounded-lg border border-gray-100 bg-gray-50 p-2 font-mono text-[11px] text-gray-700">
                              <div>
                                <span className="text-gray-500">stage:</span>{' '}
                                <span>{turn.meta.buyer_stage}</span>
                              </div>
                              {turn.meta.model_used && (
                                <div>
                                  <span className="text-gray-500">model:</span>{' '}
                                  <span>{turn.meta.model_used}</span>
                                </div>
                              )}
                              {turn.meta.response_time_ms != null && (
                                <div>
                                  <span className="text-gray-500">time:</span>{' '}
                                  <span>{turn.meta.response_time_ms}ms</span>
                                </div>
                              )}
                              {turn.meta.conversion_ready && (
                                <div className="text-green-700">
                                  conversion_ready=true (CAPI would fire)
                                </div>
                              )}
                              {turn.meta.needs_human_handoff && (
                                <div className="text-amber-700">
                                  handoff: {turn.meta.handoff_reason}
                                </div>
                              )}
                              {turn.meta.compliance_flags.length > 0 && (
                                <div className="text-red-700">
                                  flags: {turn.meta.compliance_flags.join(', ')}
                                </div>
                              )}
                              {turn.meta.attora_campaign_id && (
                                <div>
                                  <span className="text-gray-500">attora_campaign_id:</span>{' '}
                                  <span className="break-all">{turn.meta.attora_campaign_id}</span>
                                </div>
                              )}
                              {Object.entries(turn.meta.subscriber_tagged_urls).length > 0 && (
                                <div className="mt-1 border-t border-gray-200 pt-1">
                                  <div className="mb-1 text-gray-500">
                                    tagged URLs passed to prompt:
                                  </div>
                                  {Object.entries(turn.meta.subscriber_tagged_urls).map(
                                    ([key, url]) => (
                                      <div key={key} className="break-all">
                                        <span className="text-gray-500">{key}:</span>{' '}
                                        <span className="text-blue-700">{url}</span>
                                      </div>
                                    ),
                                  )}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="whitespace-pre-wrap">{turn.text}</div>
                  )}
                </div>
              </div>
            ))}

            {sending && (
              <div className="flex justify-start">
                <div className="rounded-2xl rounded-bl-sm bg-gray-100 px-4 py-2 text-sm text-gray-500">
                  <span className="inline-flex items-center gap-1">
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.3s]" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.15s]" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400" />
                  </span>
                </div>
              </div>
            )}

            <div ref={threadEndRef} />
          </div>

          {error && (
            <div className="border-t border-red-100 bg-red-50 px-4 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          <div className="flex items-end gap-2 border-t border-gray-100 p-3">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void handleSend();
                }
              }}
              placeholder="Type a message as the lead… (Enter to send, Shift+Enter for newline)"
              rows={2}
              className="flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-400 focus:outline-none focus:ring-1 focus:ring-primary-300"
              disabled={sending}
            />
            <button
              type="button"
              onClick={() => void handleSend()}
              disabled={sending || !draft.trim()}
              className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
