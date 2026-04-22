import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getSubscribers, type SubscriberFilters } from '../api/subscribers';
import LeadList from '../components/leads/LeadList';
import Select from '../components/ui/Select';
import DateRangePicker from '../components/ui/DateRangePicker';
import Pagination from '../components/ui/Pagination';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { daysAgoISO, todayISO } from '../utils/formatters';

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

export default function LeadsPage() {
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<SubscriberFilters & { is_converted_str?: string }>({
    buyer_stage: '',
    channel: '',
    date_from: daysAgoISO(90),
    date_to: todayISO(),
    page: 1,
    page_size: 20,
    is_converted_str: '',
  });

  const apiFilters: SubscriberFilters = {
    ...filters,
    is_converted:
      filters.is_converted_str === 'true'
        ? true
        : filters.is_converted_str === 'false'
        ? false
        : undefined,
  };

  const { data, isLoading, isError } = useQuery({
    queryKey: ['subscribers', apiFilters],
    queryFn: () => getSubscribers(apiFilters),
    placeholderData: (prev) => prev, // show previous data while next page loads
  });

  const leads = data?.items ?? [];
  const total = data?.total ?? 0;

  function updateFilter(key: string, value: string | number) {
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
