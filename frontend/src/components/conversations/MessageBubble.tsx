import Badge, { buyerStageBadgeColor } from '../ui/Badge';
import { formatTime } from '../../utils/formatTime';
import type { ConversationMessage } from '../../types';

interface MessageBubbleProps {
  message: ConversationMessage;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.sender === 'user';
  const isHuman = message.sender === 'human';
  const isSystem = message.sender === 'system';

  if (isSystem) {
    return (
      <div className="flex justify-center my-2">
        <div className="rounded-full bg-gray-100 px-4 py-1.5 text-xs text-gray-500">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`max-w-[70%] ${
          isUser
            ? 'rounded-2xl rounded-br-md bg-primary-600 text-white'
            : 'rounded-2xl rounded-bl-md bg-white border border-gray-200 text-gray-900'
        }`}
      >
        {/* Header */}
        <div
          className={`flex items-center gap-2 px-4 pt-3 pb-1 ${
            isUser ? 'text-primary-200' : 'text-gray-400'
          }`}
        >
          <span className="text-xs font-medium">
            {isUser ? 'User' : isHuman ? 'Human Agent' : 'AI Assistant'}
          </span>
          <span className="text-xs">{formatTime(message.created_at)}</span>
        </div>

        {/* Message content */}
        <div className="px-4 pb-2">
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        </div>

        {/* Metadata footer */}
        <div className="flex flex-wrap items-center gap-2 px-4 pb-3">
          {message.buyer_stage_at_time && (
            <Badge color={buyerStageBadgeColor(message.buyer_stage_at_time)}>
              {message.buyer_stage_at_time}
            </Badge>
          )}
          {message.compliance_flags?.map((flag, i) => (
            <Badge key={i} color="red">
              {flag}
            </Badge>
          ))}
          {message.intent_signals?.map((sig, i) => (
            <Badge key={i} color="gray">{sig}</Badge>
          ))}
        </div>
      </div>
    </div>
  );
}
