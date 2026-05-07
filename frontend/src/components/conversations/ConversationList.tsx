import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Badge, { buyerStageBadgeColor, statusBadgeColor, channelBadgeColor } from '../ui/Badge';
import { truncate } from '../../utils/formatters';
import { formatTime } from '../../utils/formatTime';
import { deleteConversation } from '../../api/conversations';
import type { ConversationListItem } from '../../types';

interface ConversationListProps {
  conversations: ConversationListItem[];
  onDeleted?: () => void;
}

export default function ConversationList({ conversations, onDeleted }: ConversationListProps) {
  const navigate = useNavigate();
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function handleDelete(event: React.MouseEvent, conv: ConversationListItem) {
    event.stopPropagation();
    const who = conv.subscriber_name || 'this conversation';
    if (!confirm(`Delete conversation with ${who}? All messages will be removed. The subscriber will be kept.`))
      return;
    setDeletingId(conv.id);
    try {
      await deleteConversation(conv.id);
      onDeleted?.();
    } catch {
      alert('Failed to delete conversation.');
    } finally {
      setDeletingId(null);
    }
  }

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
            <th className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
              Actions
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
                    {(conv.subscriber_first_name?.charAt(0) || conv.subscriber_name?.charAt(0) || '?').toUpperCase()}
                  </div>
                  <div className="ml-3">
                    <p className="text-sm font-medium text-gray-900">
                      {[conv.subscriber_first_name, conv.subscriber_last_name].filter(Boolean).join(' ') || 'Unknown Subscriber'}
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
                {formatTime(conv.last_message_at || conv.created_at)}
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
              <td className="whitespace-nowrap px-6 py-4 text-right">
                <button
                  type="button"
                  onClick={(e) => void handleDelete(e, conv)}
                  disabled={deletingId === conv.id}
                  aria-label="Delete conversation"
                  title="Delete conversation + all messages"
                  className="rounded-md p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.75" stroke="currentColor" className="h-4 w-4">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                  </svg>
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
