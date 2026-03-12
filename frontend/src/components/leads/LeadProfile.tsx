import { useNavigate } from 'react-router-dom';
import Badge, { buyerStageBadgeColor, channelBadgeColor, statusBadgeColor } from '../ui/Badge';
import { formatDate, formatDateTime } from '../../utils/formatters';
import type { SubscriberDetail } from '../../types';

interface LeadProfileProps {
  lead: SubscriberDetail;
}

export default function LeadProfile({ lead }: LeadProfileProps) {
  const navigate = useNavigate();

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      {/* Contact Info Card */}
      <div className="lg:col-span-1 space-y-6">
        <div className="card">
          <div className="flex items-center gap-4 mb-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary-100 text-xl font-bold text-primary-700">
              {lead.name?.charAt(0)?.toUpperCase() || '?'}
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">
                {lead.name || 'Unknown'}
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
              <dt className="text-xs text-gray-500">External ID</dt>
              <dd className="text-sm font-mono text-gray-700">{lead.external_id}</dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">First Contact</dt>
              <dd className="text-sm text-gray-700">{formatDate(lead.first_contact_at)}</dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">Last Contact</dt>
              <dd className="text-sm text-gray-700">{formatDate(lead.last_contact_at)}</dd>
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

        {/* Interests */}
        {lead.interests && lead.interests.length > 0 && (
          <div className="card">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Interests</h3>
            <div className="flex flex-wrap gap-2">
              {lead.interests.map((interest, i) => (
                <Badge key={i} color="blue">{interest}</Badge>
              ))}
            </div>
          </div>
        )}

        {/* Objections */}
        {lead.objections && lead.objections.length > 0 && (
          <div className="card">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Objections</h3>
            <div className="flex flex-wrap gap-2">
              {lead.objections.map((objection, i) => (
                <Badge key={i} color="yellow">{objection}</Badge>
              ))}
            </div>
          </div>
        )}

        {/* Custom Fields */}
        {lead.custom_fields && Object.keys(lead.custom_fields).length > 0 && (
          <div className="card">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Custom Fields</h3>
            <dl className="space-y-2">
              {Object.entries(lead.custom_fields).map(([key, value]) => (
                <div key={key}>
                  <dt className="text-xs text-gray-500">{key}</dt>
                  <dd className="text-sm text-gray-700">{value}</dd>
                </div>
              ))}
            </dl>
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
                  className="flex items-center justify-between rounded-lg border border-gray-100 bg-gray-50 px-4 py-3 cursor-pointer hover:bg-gray-100 transition-colors"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <Badge color={statusBadgeColor(conv.status)}>{conv.status}</Badge>
                      <Badge color={buyerStageBadgeColor(conv.buyer_stage)}>
                        {conv.buyer_stage}
                      </Badge>
                    </div>
                    <p className="mt-1 text-xs text-gray-500">
                      {conv.message_count} messages
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm text-gray-700">
                      {formatDateTime(conv.created_at)}
                    </p>
                    <p className="text-xs text-gray-500">
                      Last: {formatDateTime(conv.last_message_at)}
                    </p>
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
