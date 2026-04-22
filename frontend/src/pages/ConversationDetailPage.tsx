import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getConversation } from '../api/conversations';
import ConversationDetailView from '../components/conversations/ConversationDetail';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import Button from '../components/ui/Button';

export default function ConversationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const {
    data: conversation,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['conversation', id],
    queryFn: () => getConversation(id!),
    enabled: !!id,
  });

  if (isLoading && !conversation) {
    return <LoadingSpinner className="mt-20" size="lg" />;
  }

  if (isError || !conversation) {
    return (
      <div className="mt-20 text-center">
        <p className="text-red-600 mb-4">{isError ? 'Failed to load conversation' : 'Conversation not found'}</p>
        <Button variant="secondary" onClick={() => navigate('/conversations')}>
          Back to Conversations
        </Button>
      </div>
    );
  }

  return (
    <div>
      {/* Back button */}
      <button
        onClick={() => navigate('/conversations')}
        className="mb-4 flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 transition-colors"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
        </svg>
        Back to Conversations
      </button>

      <ConversationDetailView conversation={conversation} />
    </div>
  );
}
