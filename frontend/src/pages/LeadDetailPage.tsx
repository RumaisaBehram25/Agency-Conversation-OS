import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getSubscriber } from '../api/subscribers';
import LeadProfile from '../components/leads/LeadProfile';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import Button from '../components/ui/Button';

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

function getPageTitle(lead: { first_name?: string | null; last_name?: string | null }): string {
  const firstName = safeField(lead.first_name, "");
  const lastName = safeField(lead.last_name, "");
  const parts = [firstName, lastName].filter(Boolean);
  return parts.length > 0 ? parts.join(' ') : 'Unknown Subscriber';
}

export default function LeadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const {
    data: lead,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['subscriber', id],
    queryFn: () => getSubscriber(id!),
    enabled: !!id,
  });

  if (isLoading && !lead) {
    return <LoadingSpinner className="mt-20" size="lg" />;
  }

  if (isError || !lead) {
    return (
      <div className="mt-20 text-center">
        <p className="text-red-600 mb-4">{isError ? 'Failed to load lead details' : 'Lead not found'}</p>
        <Button variant="secondary" onClick={() => navigate('/leads')}>
          Back to Leads
        </Button>
      </div>
    );
  }

  return (
    <div>
      <button
        onClick={() => navigate('/leads')}
        className="mb-4 flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 transition-colors"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
        </svg>
        Back to Leads
      </button>

      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">{getPageTitle(lead)}</h1>
        <p className="mt-1 text-sm text-gray-500">Lead profile and conversation history</p>
      </div>

      <LeadProfile lead={lead} />
    </div>
  );
}
