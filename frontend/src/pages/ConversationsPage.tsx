import { useEffect, useState, useCallback } from 'react';
import { AxiosError } from 'axios';
import { getConversations, type ConversationFilters } from '../api/conversations';
import type { ConversationListItem } from '../types';
import ConversationList from '../components/conversations/ConversationList';
import Select from '../components/ui/Select';
import DateRangePicker from '../components/ui/DateRangePicker';
import Pagination from '../components/ui/Pagination';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { daysAgoISO, todayISO } from '../utils/formatters';

const statusOptions = [
  { value: '', label: 'All Statuses' },
  { value: 'active', label: 'Active' },
  { value: 'idle', label: 'Idle' },
  { value: 'closed', label: 'Closed' },
  { value: 'escalated', label: 'Escalated' },
];

const channelOptions = [
  { value: '', label: 'All Channels' },
  { value: 'messenger', label: 'Messenger' },
  { value: 'instagram', label: 'Instagram' },
];

export default function ConversationsPage() {
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [filters, setFilters] = useState<ConversationFilters>({
    status: '',
    channel: '',
    date_from: daysAgoISO(30),
    date_to: todayISO(),
    page: 1,
    page_size: 20,
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await getConversations(filters);
      setConversations(result.items);
      setTotal(result.total);
    } catch (err) {
      if (err instanceof AxiosError) {
        const detail = err.response?.data?.detail;
        const status = err.response?.status;
        setError(
          `Failed to load conversations (${status ?? 'network'}): ${
            typeof detail === 'string' ? detail : err.message
          }`
        );
      } else {
        setError('Failed to load conversations');
      }
      console.error('getConversations failed:', err);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    load();
  }, [load]);

  function updateFilter(key: keyof ConversationFilters, value: string | number) {
    setFilters((prev) => ({
      ...prev,
      [key]: value,
      ...(key !== 'page' ? { page: 1 } : {}), // Reset page on filter change
    }));
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Conversations</h1>
        <p className="mt-1 text-sm text-gray-500">
          Monitor AI-powered conversations with your subscribers
        </p>
      </div>

      {/* Filters */}
      <div className="mb-6 flex flex-wrap items-end gap-4">
        <Select
          label="Status"
          options={statusOptions}
          value={filters.status || ''}
          onChange={(e) => updateFilter('status', e.target.value)}
          className="w-40"
        />
        <Select
          label="Channel"
          options={channelOptions}
          value={filters.channel || ''}
          onChange={(e) => updateFilter('channel', e.target.value)}
          className="w-40"
        />
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Date Range</label>
          <DateRangePicker
            dateFrom={filters.date_from || ''}
            dateTo={filters.date_to || ''}
            onChange={(from, to) =>
              setFilters((prev) => ({ ...prev, date_from: from, date_to: to, page: 1 }))
            }
          />
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <LoadingSpinner className="mt-12" />
      ) : error ? (
        <div className="mt-12 text-center text-red-600">{error}</div>
      ) : (
        <>
          <ConversationList conversations={conversations} />
          <Pagination
            page={filters.page || 1}
            pageSize={filters.page_size || 20}
            total={total}
            onPageChange={(page) => updateFilter('page', page)}
          />
        </>
      )}
    </div>
  );
}
