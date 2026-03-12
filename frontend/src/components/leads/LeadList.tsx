import { useNavigate } from 'react-router-dom';
import Badge, { buyerStageBadgeColor, channelBadgeColor } from '../ui/Badge';
import { formatDate } from '../../utils/formatters';
import type { SubscriberListItem } from '../../types';

interface LeadListProps {
  leads: SubscriberListItem[];
}

export default function LeadList({ leads }: LeadListProps) {
  const navigate = useNavigate();

  if (leads.length === 0) {
    return (
      <div className="py-12 text-center text-gray-400">
        No leads found
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
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
              Conversion
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Conversations
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
                    {lead.name?.charAt(0)?.toUpperCase() || '?'}
                  </div>
                  <div className="ml-3">
                    <p className="text-sm font-medium text-gray-900">
                      {lead.name || 'Unknown'}
                    </p>
                    <p className="text-xs text-gray-500 font-mono">
                      {lead.external_id}
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
                {formatDate(lead.first_contact_at)}
              </td>
              <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                {formatDate(lead.last_contact_at)}
              </td>
              <td className="whitespace-nowrap px-6 py-4">
                <Badge color={buyerStageBadgeColor(lead.buyer_stage)}>
                  {lead.buyer_stage}
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
                {lead.conversation_count}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
