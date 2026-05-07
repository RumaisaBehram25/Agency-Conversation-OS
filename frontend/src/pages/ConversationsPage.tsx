import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { useSearchParams } from 'react-router-dom';
import { getConversations, type ConversationFilters } from '../api/conversations';
import ConversationList from '../components/conversations/ConversationList';
import Select from '../components/ui/Select';
import DateRangePicker from '../components/ui/DateRangePicker';
import Pagination from '../components/ui/Pagination';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { daysAgoISO, todayISO } from '../utils/formatters';

const LS_KEY = 'attora_source_filter';

function readSourceFromStorage(): boolean | undefined {
  try {
    const value = localStorage.getItem(LS_KEY);
    if (value === 'true') return true;
    if (value === 'false') return false;
    return undefined;
  } catch {
    return undefined;
  }
}

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

function resolveSourceType(urlParam: string | null): 'paid' | 'organic' | undefined {
  if (urlParam === 'paid' || urlParam === 'organic') return urlParam;
  return undefined;
}

function resolveIsTest(urlParam: string | null): boolean | undefined {
  if (urlParam === 'true') return true;
  if (urlParam === 'false') return false;
  return readSourceFromStorage();
}

export default function ConversationsPage() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState<ConversationFilters>({
    status: searchParams.get('status') || '',
    channel: searchParams.get('channel') || '',
    date_from: searchParams.get('date_from') || daysAgoISO(30),
    date_to: searchParams.get('date_to') || todayISO(),
    is_test: resolveIsTest(searchParams.get('is_test')),
    source_type: resolveSourceType(searchParams.get('source_type')),
    keywords: searchParams.get('keywords') || undefined,
    campaign_id: searchParams.get('campaign_id') || undefined,
    attora_campaign_id: searchParams.get('attora_campaign_id') || undefined,
    page: Number(searchParams.get('page') || 1),
    page_size: Number(searchParams.get('page_size') || 20),
  });

  const { data, isLoading, error } = useQuery({
    queryKey: ['conversations', filters],
    queryFn: () => getConversations(filters),
    placeholderData: (prev) => prev,
  });

  useEffect(() => {
    const params = new URLSearchParams();
    if (filters.status) params.set('status', filters.status);
    if (filters.channel) params.set('channel', filters.channel);
    if (filters.date_from) params.set('date_from', filters.date_from);
    if (filters.date_to) params.set('date_to', filters.date_to);
    if (filters.is_test !== undefined) {
      params.set('is_test', String(filters.is_test));
    }
    if (filters.source_type) params.set('source_type', filters.source_type);
    if (filters.keywords) params.set('keywords', filters.keywords);
    if (filters.campaign_id) params.set('campaign_id', filters.campaign_id);
    if (filters.attora_campaign_id) params.set('attora_campaign_id', filters.attora_campaign_id);
    if (filters.page) params.set('page', String(filters.page));
    if (filters.page_size) params.set('page_size', String(filters.page_size));
    setSearchParams(params, { replace: true });

    try {
      if (filters.is_test === undefined) {
        localStorage.removeItem(LS_KEY);
      } else {
        localStorage.setItem(LS_KEY, String(filters.is_test));
      }
    } catch {
      // ignore storage errors
    }
  }, [filters, setSearchParams]);

  const conversations = data?.items ?? [];
  const total = data?.total ?? 0;

  function updateFilter(
    key: keyof ConversationFilters,
    value: string | number | boolean | undefined
  ) {
    setFilters((prev) => ({
      ...prev,
      [key]: value,
      ...(key !== 'page' ? { page: 1 } : {}),
    }));
  }

  function handleDeleted() {
    void queryClient.invalidateQueries({ queryKey: ['conversations'] });
  }

  const errorMessage = (() => {
    if (!error) return null;
    if (error instanceof AxiosError) {
      const detail = error.response?.data?.detail;
      const status = error.response?.status;
      return `Failed to load conversations (${status ?? 'network'}): ${
        typeof detail === 'string' ? detail : error.message
      }`;
    }
    return 'Failed to load conversations';
  })();

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
        {/* Source toggle — first in bar, matches input height */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Source</label>
          <div className="flex rounded-lg border border-gray-200 bg-gray-100 p-1">
            <button
              type="button"
              onClick={() => updateFilter('is_test', undefined)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                filters.is_test === undefined
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              All
            </button>
            <button
              type="button"
              onClick={() => updateFilter('is_test', false)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                filters.is_test === false
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              Real Clients
            </button>
            <button
              type="button"
              onClick={() => updateFilter('is_test', true)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                filters.is_test
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              Playground
            </button>
          </div>
        </div>

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
      {isLoading && !data ? (
        <LoadingSpinner className="mt-12" />
      ) : errorMessage ? (
        <div className="mt-12 text-center text-red-600">{errorMessage}</div>
      ) : (
        <>
          <ConversationList conversations={conversations} onDeleted={handleDeleted} />
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
