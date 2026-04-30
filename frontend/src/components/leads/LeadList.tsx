import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Badge, { buyerStageBadgeColor, channelBadgeColor } from '../ui/Badge';
import { formatDate } from '../../utils/formatters';
import { deleteSubscriber } from '../../api/subscribers';
import type { SubscriberListItem } from '../../types';

interface LeadListProps {
  leads: SubscriberListItem[];
  onDeleted?: () => void;
}

/**
 * Guard against displaying ManyChat unreplaced template placeholders.
 * Returns fallback if value is a placeholder like {{first_name}}.
 */
function safeField(value: string | null | undefined, fallback = "—"): string {
  if (!value) return fallback;
  const trimmed = value.trim();
  if (trimmed.startsWith("{{") && trimmed.endsWith("}}")) {
    return fallback;
  }
  return trimmed;
}

function displayName(lead: SubscriberListItem): string {
  const firstName = safeField(lead.first_name, "");
  const lastName = safeField(lead.last_name, "");
  const parts = [firstName, lastName].filter(Boolean);
  return parts.length > 0 ? parts.join(' ') : 'Unknown Subscriber';
}

function displayInitial(lead: SubscriberListItem): string {
  const firstName = safeField(lead.first_name, "");
  const lastName = safeField(lead.last_name, "");
  return firstName?.charAt(0)?.toUpperCase() || lastName?.charAt(0)?.toUpperCase() || '?';
}

function hyrosStatus(lead: SubscriberListItem): string {
  if (lead.hyros_purchased === true) {
    return 'Purchased ✅';
  }
  if (lead.hyros_synced_at) {
    return 'Lead 👤';
  }
  return 'Unknown —';
}

function hyrosStatusColor(lead: SubscriberListItem): 'green' | 'blue' | 'gray' {
  if (lead.hyros_purchased === true) {
    return 'green';
  }
  if (lead.hyros_synced_at) {
    return 'blue';
  }
  return 'gray';
}

export default function LeadList({ leads, onDeleted }: LeadListProps) {
  const navigate = useNavigate();
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function handleDelete(event: React.MouseEvent, lead: SubscriberListItem) {
    event.stopPropagation();
    const name = displayName(lead);
    if (!confirm(`Delete ${name}? This removes all their conversations, messages, and conversion history. This cannot be undone.`))
      return;
    setDeletingId(lead.id);
    try {
      await deleteSubscriber(lead.id);
      onDeleted?.();
    } catch {
      alert('Failed to delete lead.');
    } finally {
      setDeletingId(null);
    }
  }

  if (leads.length === 0) {
    return (
      <div className="py-12 text-center text-gray-400">
        No leads found
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Name
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Channel
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              First Contact
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Last Contact
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Buyer Stage
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Hyros Status
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Conversion
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Messages
            </th>
            <th className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {leads.map((lead) => (
            <tr
              key={lead.id}
              onClick={() => navigate(`/leads/${lead.id}`)}
              className="cursor-pointer transition-colors hover:bg-gray-50"
            >
              <td className="whitespace-nowrap px-6 py-4">
                <div className="flex items-center">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-100 text-sm font-medium text-primary-700">
                    {displayInitial(lead)}
                  </div>
                  <div className="ml-3">
                    <p className="text-sm font-medium text-gray-900">
                      {displayName(lead)}
                    </p>
                  </div>
                </div>
              </td>
              <td className="whitespace-nowrap px-6 py-4">
                <Badge color={channelBadgeColor(lead.channel)}>
                  {lead.channel}
                </Badge>
              </td>
              <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                {lead.first_message_at ? formatDate(lead.first_message_at) : '—'}
              </td>
              <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                {lead.last_message_at ? formatDate(lead.last_message_at) : '—'}
              </td>
              <td className="whitespace-nowrap px-6 py-4">
                <Badge color={buyerStageBadgeColor(lead.buyer_stage)}>
                  {lead.buyer_stage}
                </Badge>
              </td>
              <td className="whitespace-nowrap px-6 py-4">
                <Badge color={hyrosStatusColor(lead)}>
                  {hyrosStatus(lead)}
                </Badge>
              </td>
              <td className="whitespace-nowrap px-6 py-4">
                {lead.is_converted ? (
                  <Badge color="green">Converted</Badge>
                ) : (
                  <Badge color="gray">Not converted</Badge>
                )}
              </td>
              <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                {lead.total_messages}
              </td>
              <td className="whitespace-nowrap px-6 py-4 text-right">
                <button
                  type="button"
                  onClick={(e) => void handleDelete(e, lead)}
                  disabled={deletingId === lead.id}
                  aria-label="Delete lead"
                  title="Delete lead + all conversations"
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
