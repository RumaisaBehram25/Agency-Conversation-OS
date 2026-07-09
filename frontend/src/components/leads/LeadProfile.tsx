import { useNavigate } from 'react-router-dom';
import Badge, { buyerStageBadgeColor, channelBadgeColor, statusBadgeColor } from '../ui/Badge';
import { formatDate, formatDateTime } from '../../utils/formatters';
import { formatTime } from '../../utils/formatTime';
import type { SubscriberDetail } from '../../types';

interface LeadProfileProps {
  lead: SubscriberDetail;
}

/**
 * Guard against displaying ManyChat unreplaced template placeholders.
 * Returns fallback if value is a placeholder like {{first_name}}.
 */
function safeField(value: string | null | undefined, fallback = '—'): string {
  if (!value) return fallback;
  const trimmed = value.trim();
  if (trimmed.startsWith('{{') && trimmed.endsWith('}}')) {
    return fallback;
  }
  return trimmed;
}

function displayName(lead: SubscriberDetail): string {
  const firstName = safeField(lead.first_name, '');
  const lastName = safeField(lead.last_name, '');
  const parts = [firstName, lastName].filter(Boolean);
  return parts.length > 0 ? parts.join(' ') : 'Unknown';
}

function displayInitial(lead: SubscriberDetail): string {
  const firstName = safeField(lead.first_name, '');
  const lastName = safeField(lead.last_name, '');
  return firstName?.charAt(0)?.toUpperCase() || lastName?.charAt(0)?.toUpperCase() || '?';
}

function hyrosStatusLabel(lead: SubscriberDetail): string {
  if (lead.hyros_purchased) {
    return 'Purchased';
  }
  if (lead.hyros_synced_at) {
    return 'Lead matched';
  }
  return 'Unknown';
}

function UtmRow({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <dt className="text-xs text-gray-500">{label}</dt>
      <dd className="font-mono text-sm text-gray-800 break-all">{safeField(value, '—')}</dd>
    </div>
  );
}

export default function LeadProfile({ lead }: LeadProfileProps) {
  const navigate = useNavigate();

  const historyJson =
    lead.history != null
      ? JSON.stringify(lead.history, null, 2)
      : null;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      {/* Contact Info Card */}
      <div className="lg:col-span-1 space-y-6">
        <div className="card">
          <div className="flex items-center gap-4 mb-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary-100 text-xl font-bold text-primary-800">
              {displayInitial(lead)}
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">
                {displayName(lead)}
              </h2>
              <div className="flex items-center gap-2 mt-1">
                <Badge color={channelBadgeColor(lead.channel)}>{lead.channel}</Badge>
                {lead.is_converted ? (
                  <Badge color="green">Converted</Badge>
                ) : (
                  <Badge color="gray">Not converted</Badge>
                )}
              </div>
            </div>
          </div>

          <dl className="space-y-3">
            <div>
              <dt className="text-xs text-gray-500">ManyChat ID</dt>
              <dd className="text-sm font-mono text-gray-700">{lead.manychat_subscriber_id}</dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">First Contact</dt>
              <dd className="text-sm text-gray-700">{lead.first_message_at ? formatDate(lead.first_message_at) : '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">Last Contact (any message)</dt>
              <dd className="text-sm text-gray-700">{lead.last_message_at ? formatDateTime(lead.last_message_at) : '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">Last user reply (silence anchor)</dt>
              <dd className="text-sm text-gray-700">
                {lead.last_user_message_at ? formatDateTime(lead.last_user_message_at) : '—'}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">Total messages</dt>
              <dd className="text-sm text-gray-700">{lead.total_messages}</dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">Email</dt>
              <dd className={`text-sm ${lead.email ? 'text-gray-700' : 'text-gray-400 italic'}`}>
                {safeField(lead.email, 'No email')}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">Phone</dt>
              <dd className={`text-sm ${lead.phone ? 'text-gray-700' : 'text-gray-400 italic'}`}>
                {safeField(lead.phone, 'No phone')}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">attora_sub</dt>
              <dd className="text-sm font-mono text-gray-700">
                {lead.manychat_subscriber_id?.trim() ? lead.manychat_subscriber_id : '—'}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">attora_id</dt>
              <dd className="text-sm font-mono text-gray-700">
                {lead.id?.trim() ? lead.id : '—'}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">Attora campaign ID</dt>
              <dd className="text-sm font-mono text-gray-700 break-all">
                {lead.attora_campaign_id ?? '—'}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">Record created / updated</dt>
              <dd className="text-xs text-gray-600">
                {formatDateTime(lead.created_at)} / {formatDateTime(lead.updated_at)}
              </dd>
            </div>
          </dl>
        </div>

        <div className="card">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">Intake UTMs</h3>
          <dl className="space-y-2 text-sm">
            <UtmRow label="utm_source" value={lead.utm_source} />
            <UtmRow label="utm_medium" value={lead.utm_medium} />
            <UtmRow label="utm_campaign" value={lead.utm_campaign} />
            <UtmRow label="utm_content" value={lead.utm_content} />
          </dl>
        </div>

        <div className="card">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">Meta &amp; paid attribution</h3>
          <dl className="space-y-2 text-sm">
            <UtmRow label="ctwa_clid" value={lead.ctwa_clid} />
            <UtmRow label="ad_id" value={lead.ad_id} />
            <UtmRow label="post_id" value={lead.post_id} />
            <UtmRow label="ad_set_id" value={lead.ad_set_id} />
            <UtmRow label="campaign_id (Meta)" value={lead.campaign_id} />
          </dl>
        </div>

        <div className="card">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">Conversion (Attora)</h3>
          <dl className="space-y-2 text-sm">
            <div>
              <dt className="text-xs text-gray-500">Converted</dt>
              <dd className="text-gray-800">{lead.is_converted ? 'Yes' : 'No'}</dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">Conversion value</dt>
              <dd className="text-gray-800">
                {lead.conversion_value != null ? `$${lead.conversion_value.toFixed(2)}` : '—'}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">Converted at</dt>
              <dd className="text-gray-800">
                {lead.converted_at ? formatDateTime(lead.converted_at) : '—'}
              </dd>
            </div>
          </dl>
        </div>

        {/* Buyer Stage */}
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">Current Buyer Stage</h3>
          <Badge color={buyerStageBadgeColor(lead.buyer_stage)} className="text-sm px-3 py-1">
            {lead.buyer_stage}
          </Badge>
        </div>

        <div className="card">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">Hyros Attribution</h3>

          {lead.hyros_synced_at ? (
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="text-xs text-gray-500">Match status</dt>
                <dd className="mt-0.5 text-gray-700">{hyrosStatusLabel(lead)}</dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500">Purchase Status</dt>
                <dd className="mt-0.5">
                  {lead.hyros_purchased ? (
                    <span className="inline-flex items-center gap-1 font-medium text-green-700">
                      Purchased ✅
                    </span>
                  ) : (
                    <span className="text-gray-600">Not yet purchased</span>
                  )}
                </dd>
              </div>

              {lead.hyros_purchased && (
                <>
                  <div>
                    <dt className="text-xs text-gray-500">Product</dt>
                    <dd className="font-medium text-gray-900">{lead.hyros_product || '—'}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-gray-500">Purchase Date</dt>
                    <dd className="text-gray-700">{lead.hyros_purchase_date ? formatDate(lead.hyros_purchase_date) : '—'}</dd>
                  </div>
                </>
              )}

              <div>
                <dt className="text-xs text-gray-500">Hyros lead ID</dt>
                <dd className="font-mono text-xs text-gray-700 break-all">{lead.hyros_lead_id || '—'}</dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500">Hyros email (on lead)</dt>
                <dd className="text-gray-700 break-all">{lead.hyros_email || '—'}</dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500">Origin source</dt>
                <dd className="text-gray-900 font-medium break-all">{lead.hyros_origin_source || '—'}</dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500">Origin tag</dt>
                <dd className="text-gray-700 break-all">{lead.hyros_origin_tag || '—'}</dd>
              </div>

              <div>
                <dt className="text-xs text-gray-500">Creative</dt>
                <dd className="text-gray-700">{lead.hyros_creative_name || '—'}</dd>
              </div>

              <div>
                <dt className="text-xs text-gray-500">Traffic Source</dt>
                <dd className="text-gray-700 capitalize">{lead.hyros_traffic_source || '—'}</dd>
              </div>

              <div>
                <dt className="text-xs text-gray-500">Last Synced</dt>
                <dd className="text-xs text-gray-400">{formatDateTime(lead.hyros_synced_at)}</dd>
              </div>
            </dl>
          ) : (
            <div className="py-2">
              <p className="text-sm text-gray-500 italic">Not synced</p>
              <p className="mt-1 text-xs text-gray-400">Run Hyros sync to pull attribution data</p>
            </div>
          )}
        </div>

        {/* Interests */}
        {lead.interests && lead.interests.length > 0 && (
          <div className="card">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Interests</h3>
            <div className="flex flex-wrap gap-2">
              {lead.interests.map((interest, i) => (
                <Badge key={i} color="red">
                  {interest}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Objections */}
        {lead.objections_raised && lead.objections_raised.length > 0 && (
          <div className="card">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Objections</h3>
            <div className="flex flex-wrap gap-2">
              {lead.objections_raised.map((objection, i) => (
                <Badge key={i} color="yellow">
                  {objection}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Conversation Summary */}
        {lead.conversation_summary && (
          <div className="card">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">AI Summary</h3>
            <p className="text-sm text-gray-700">{lead.conversation_summary}</p>
          </div>
        )}

        {historyJson && (
          <div className="card">
            <details className="group">
              <summary className="cursor-pointer text-sm font-semibold text-gray-900">
                Session history (JSON)
              </summary>
              <pre className="mt-3 max-h-64 overflow-auto rounded-lg bg-gray-950 p-3 text-xs text-gray-100">
                {historyJson}
              </pre>
            </details>
          </div>
        )}
      </div>

      {/* Conversation History */}
      <div className="lg:col-span-2">
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">
            Conversation History ({lead.conversations?.length || 0} sessions)
          </h3>
          {!lead.conversations || lead.conversations.length === 0 ? (
            <p className="text-sm text-gray-400">No conversations yet</p>
          ) : (
            <div className="space-y-3">
              {lead.conversations.map((conv) => (
                <div
                  key={conv.id}
                  onClick={() => navigate(`/conversations/${conv.id}`)}
                  className="flex flex-col gap-2 rounded-lg border border-gray-100 bg-gray-50 px-4 py-3 cursor-pointer hover:bg-gray-100 transition-colors sm:flex-row sm:items-center sm:justify-between"
                >
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge color={statusBadgeColor(conv.status)}>{conv.status}</Badge>
                      <Badge color={channelBadgeColor(conv.channel)}>{conv.channel}</Badge>
                      <span className="text-xs text-gray-500">
                        Follow-ups sent: {conv.follow_up_attempts ?? 0}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-gray-500">
                      {conv.message_count} messages
                      {conv.last_follow_up_at && (
                        <> · Last follow-up {formatDateTime(conv.last_follow_up_at)}</>
                      )}
                    </p>
                    {conv.summary && (
                      <p className="mt-1 text-xs text-gray-600 line-clamp-2">{conv.summary}</p>
                    )}
                  </div>
                  <div className="text-left sm:text-right">
                    <p className="text-sm text-gray-700">
                      {formatTime(conv.last_activity_at || conv.started_at)}
                    </p>
                    <p className="text-xs text-gray-500">
                      Started {conv.started_at ? formatDateTime(conv.started_at) : '—'}
                    </p>
                    {conv.closed_at && (
                      <p className="text-xs text-gray-400">Closed {formatDateTime(conv.closed_at)}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
