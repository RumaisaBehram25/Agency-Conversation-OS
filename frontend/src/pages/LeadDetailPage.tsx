import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getSubscriber } from '../api/subscribers';
import type { SubscriberDetail } from '../types';
import LeadProfile from '../components/leads/LeadProfile';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import Button from '../components/ui/Button';

export default function LeadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [lead, setLead] = useState<SubscriberDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    async function load() {
      if (!id) return;
      try {
        const result = await getSubscriber(id);
        setLead(result);
      } catch {
        setError('Failed to load lead details');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  if (loading) {
    return <LoadingSpinner className="mt-20" size="lg" />;
  }

  if (error || !lead) {
    return (
      <div className="mt-20 text-center">
        <p className="text-red-600 mb-4">{error || 'Lead not found'}</p>
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
        <h1 className="text-2xl font-bold text-gray-900">{[lead.first_name, lead.last_name].filter(Boolean).join(' ') || 'Unknown Lead'}</h1>
        <p className="mt-1 text-sm text-gray-500">Lead profile and conversation history</p>
      </div>

      <LeadProfile lead={lead} />
    </div>
  );
}
