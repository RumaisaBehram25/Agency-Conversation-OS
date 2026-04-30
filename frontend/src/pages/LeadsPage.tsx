import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { getSubscribers, type SubscriberFilters } from '../api/subscribers';
import LeadList from '../components/leads/LeadList';
import Select from '../components/ui/Select';
import DateRangePicker from '../components/ui/DateRangePicker';
import Pagination from '../components/ui/Pagination';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { daysAgoISO, todayISO } from '../utils/formatters';

const LS_KEY = 'attora_source_filter';

function readSourceFromStorage(): boolean {
  try {
    return localStorage.getItem(LS_KEY) === 'true';
  } catch {
    return false;
  }
}

function resolveIsTest(urlParam: string | null): boolean {
  if (urlParam === 'true') return true;
  if (urlParam === 'false') return false;
  return readSourceFromStorage();
}

const buyerStageOptions = [
  { value: '', label: 'All Stages' },
  { value: 'awareness', label: 'Awareness' },
  { value: 'interest', label: 'Interest' },
  { value: 'consideration', label: 'Consideration' },
  { value: 'intent', label: 'Intent' },
  { value: 'evaluation', label: 'Evaluation' },
  { value: 'purchase', label: 'Purchase' },
];

const channelOptions = [
  { value: '', label: 'All Channels' },
  { value: 'messenger', label: 'Messenger' },
  { value: 'instagram', label: 'Instagram' },
];

const conversionOptions = [
  { value: '', label: 'All' },
  { value: 'true', label: 'Converted' },
  { value: 'false', label: 'Not Converted' },
];

const hyrosOptions = [
  { value: '', label: 'All Hyros Status' },
  { value: 'purchased', label: 'Purchased' },
  { value: 'lead', label: 'Lead' },
  { value: 'unknown', label: 'Unknown' },
];

export default function LeadsPage() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState<SubscriberFilters & { is_converted_str?: string }>({
    buyer_stage: searchParams.get('buyer_stage') || '',
    channel: searchParams.get('channel') || '',
    date_from: searchParams.get('date_from') || daysAgoISO(90),
    date_to: searchParams.get('date_to') || todayISO(),
    page: Number(searchParams.get('page') || 1),
    page_size: Number(searchParams.get('page_size') || 20),
    is_converted_str: searchParams.get('is_converted') || '',
    hyros_status: searchParams.get('hyros_status') || '',
    is_test: resolveIsTest(searchParams.get('is_test')),
  });

  const apiFilters: SubscriberFilters = {
    ...filters,
    is_converted:
      filters.is_converted_str === 'true'
        ? true
        : filters.is_converted_str === 'false'
        ? false
        : undefined,
    hyros_status: filters.hyros_status || undefined,
  };

  const { data, isLoading, isError } = useQuery({
    queryKey: ['subscribers', apiFilters],
    queryFn: () => getSubscribers(apiFilters),
    placeholderData: (prev) => prev,
  });

  useEffect(() => {
    const params = new URLSearchParams();
    if (filters.buyer_stage) params.set('buyer_stage', filters.buyer_stage);
    if (filters.channel) params.set('channel', filters.channel);
    if (filters.date_from) params.set('date_from', filters.date_from);
    if (filters.date_to) params.set('date_to', filters.date_to);
    if (filters.is_converted_str) params.set('is_converted', filters.is_converted_str);
    if (filters.hyros_status) params.set('hyros_status', filters.hyros_status);
    params.set('is_test', String(filters.is_test));
    if (filters.page) params.set('page', String(filters.page));
    if (filters.page_size) params.set('page_size', String(filters.page_size));
    setSearchParams(params, { replace: true });

    try {
      localStorage.setItem(LS_KEY, String(filters.is_test));
    } catch {
      // ignore storage errors
    }
  }, [filters, setSearchParams]);

  const leads = data?.items ?? [];
  const total = data?.total ?? 0;

  function updateFilter(key: string, value: string | number | boolean) {
    setFilters((prev) => ({
      ...prev,
      [key]: value,
      ...(key !== 'page' ? { page: 1 } : {}),
    }));
  }

  function handleDeleted() {
    void queryClient.invalidateQueries({ queryKey: ['subscribers'] });
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Leads</h1>
        <p className="mt-1 text-sm text-gray-500">
          View and manage your subscriber leads
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
              onClick={() => updateFilter('is_test', false)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                !filters.is_test
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
          label="Buyer Stage"
          options={buyerStageOptions}
          value={filters.buyer_stage || ''}
          onChange={(e) => updateFilter('buyer_stage', e.target.value)}
          className="w-44"
        />
        <Select
          label="Channel"
          options={channelOptions}
          value={filters.channel || ''}
          onChange={(e) => updateFilter('channel', e.target.value)}
          className="w-40"
        />
        <Select
          label="Conversion"
          options={conversionOptions}
          value={filters.is_converted_str || ''}
          onChange={(e) => updateFilter('is_converted_str', e.target.value)}
          className="w-40"
        />
        <Select
          label="Hyros Status"
          options={hyrosOptions}
          value={filters.hyros_status || ''}
          onChange={(e) => updateFilter('hyros_status', e.target.value)}
          className="w-44"
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
      ) : isError ? (
        <div className="mt-12 text-center text-red-600">Failed to load leads</div>
      ) : (
        <>
          <LeadList leads={leads} onDeleted={handleDeleted} />
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
