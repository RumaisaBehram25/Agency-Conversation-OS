import { useNavigate } from 'react-router-dom';
import Badge, { buyerStageBadgeColor, statusBadgeColor, channelBadgeColor } from '../ui/Badge';
import { formatRelativeTime, truncate } from '../../utils/formatters';
import type { ConversationListItem } from '../../types';

interface ConversationListProps {
  conversations: ConversationListItem[];
}

export default function ConversationList({ conversations }: ConversationListProps) {
  const navigate = useNavigate();

  if (conversations.length === 0) {
    return (
      <div className="py-12 text-center text-gray-400">
        No conversations found
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Subscriber
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Channel
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Last Message
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Time
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Buyer Stage
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Status
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {conversations.map((conv) => (
            <tr
              key={conv.id}
              onClick={() => navigate(`/conversations/${conv.id}`)}
              className="cursor-pointer transition-colors hover:bg-gray-50"
            >
              <td className="whitespace-nowrap px-6 py-4">
                <div className="flex items-center">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-100 text-sm font-medium text-primary-700">
                    {conv.subscriber_name?.charAt(0)?.toUpperCase() || '?'}
                  </div>
                  <div className="ml-3">
                    <p className="text-sm font-medium text-gray-900">
                      {conv.subscriber_name || 'Unknown'}
                    </p>
                    <p className="text-xs text-gray-500">
                      {conv.message_count} messages
                    </p>
                  </div>
                </div>
              </td>
              <td className="whitespace-nowrap px-6 py-4">
                <Badge color={channelBadgeColor(conv.channel)}>
                  {conv.channel}
                </Badge>
              </td>
              <td className="px-6 py-4">
                <p className="max-w-xs text-sm text-gray-600">
                  {truncate(conv.last_message_preview || '', 60)}
                </p>
              </td>
              <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                {formatRelativeTime(conv.last_message_at || conv.created_at)}
              </td>
              <td className="whitespace-nowrap px-6 py-4">
                <Badge color={buyerStageBadgeColor(conv.buyer_stage)}>
                  {conv.buyer_stage}
                </Badge>
              </td>
              <td className="whitespace-nowrap px-6 py-4">
                <Badge color={statusBadgeColor(conv.status)}>
                  {conv.status}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
