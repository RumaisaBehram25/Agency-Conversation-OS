import { useEffect, useRef } from 'react';
import Badge, { buyerStageBadgeColor, statusBadgeColor, channelBadgeColor } from '../ui/Badge';
import MessageBubble from './MessageBubble';
import { formatDateTime } from '../../utils/formatters';
import type { ConversationDetail as ConversationDetailType } from '../../types';

interface ConversationDetailProps {
  conversation: ConversationDetailType;
}

export default function ConversationDetailView({ conversation }: ConversationDetailProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversation.messages]);

  return (
    <div className="flex gap-6 h-[calc(100vh-12rem)]">
      {/* Chat timeline */}
      <div className="flex-1 flex flex-col rounded-xl border border-gray-200 bg-gray-50 shadow-sm">
        {/* Chat header */}
        <div className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4 rounded-t-xl">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-100 text-sm font-bold text-primary-700">
              {conversation.subscriber_name?.charAt(0)?.toUpperCase() || '?'}
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-900">
                {conversation.subscriber_name || 'Unknown Subscriber'}
              </h3>
              <div className="flex items-center gap-2 mt-0.5">
                <Badge color={channelBadgeColor(conversation.channel)}>
                  {conversation.channel}
                </Badge>
                <Badge color={statusBadgeColor(conversation.status)}>
                  {conversation.status}
                </Badge>
              </div>
            </div>
          </div>
          <div className="text-right">
            <Badge color={buyerStageBadgeColor(conversation.buyer_stage)}>
              {conversation.buyer_stage}
            </Badge>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {conversation.messages.length === 0 ? (
            <div className="flex h-full items-center justify-center text-gray-400">
              No messages in this conversation
            </div>
          ) : (
            <>
              {conversation.messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
              ))}
              <div ref={messagesEndRef} />
            </>
          )}
        </div>
      </div>

      {/* Sidebar info panel */}
      <div className="w-80 flex-shrink-0 space-y-4 overflow-y-auto">
        {/* Subscriber Info */}
        <div className="card">
          <h4 className="text-sm font-semibold text-gray-900 mb-3">Subscriber Info</h4>
          <dl className="space-y-2">
            <div>
              <dt className="text-xs text-gray-500">Name</dt>
              <dd className="text-sm font-medium text-gray-900">
                {conversation.subscriber_name || 'Unknown'}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">Channel</dt>
              <dd className="text-sm">
                <Badge color={channelBadgeColor(conversation.subscriber_channel || conversation.channel)}>
                  {conversation.subscriber_channel || conversation.channel}
                </Badge>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">Subscriber ID</dt>
              <dd className="text-sm text-gray-700 font-mono">{conversation.subscriber_id}</dd>
            </div>
          </dl>
        </div>

        {/* Conversation Stats */}
        <div className="card">
          <h4 className="text-sm font-semibold text-gray-900 mb-3">Conversation</h4>
          <dl className="space-y-2">
            <div>
              <dt className="text-xs text-gray-500">Started</dt>
              <dd className="text-sm text-gray-700">
                {formatDateTime(conversation.created_at)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">Last Updated</dt>
              <dd className="text-sm text-gray-700">
                {formatDateTime(conversation.updated_at)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">Messages</dt>
              <dd className="text-sm font-medium text-gray-900">
                {conversation.messages.length}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">Buyer Stage</dt>
              <dd>
                <Badge color={buyerStageBadgeColor(conversation.buyer_stage)}>
                  {conversation.buyer_stage}
                </Badge>
              </dd>
            </div>
          </dl>
        </div>

        {/* Products Discussed */}
        {conversation.products_discussed && conversation.products_discussed.length > 0 && (
          <div className="card">
            <h4 className="text-sm font-semibold text-gray-900 mb-3">Products Discussed</h4>
            <ul className="space-y-1">
              {conversation.products_discussed.map((product, i) => (
                <li
                  key={i}
                  className="flex items-center gap-2 text-sm text-gray-700"
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-primary-400" />
                  {product}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
