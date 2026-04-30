import { useEffect, useState, useCallback, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getAnalytics, getROI, getAIPerformance, getExportUrl } from '../api/analytics';
import { getConversations } from '../api/conversations';
import { getCampaigns, listAdCampaigns } from '../api/campaigns';
import { syncMetaNow, getMetaSyncStatus } from '../api/settings';
import type { AdCampaign, CampaignSourceType, CampaignSummary } from '../types';
import AnalyticsMetricCards from '../components/analytics/MetricCards';
import FunnelChart from '../components/analytics/FunnelChart';
import TrendChart from '../components/analytics/TrendChart';
import ROIWaterfall from '../components/analytics/ROIWaterfall';
import BreakdownCharts from '../components/analytics/BreakdownCharts';
import CampaignDrillDown from '../components/analytics/CampaignDrillDown';
import DateRangePicker from '../components/ui/DateRangePicker';
import Button from '../components/ui/Button';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { daysAgoISO, todayISO, formatPercentRaw, formatDuration, formatCurrency } from '../utils/formatters';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

type SourceFilter = 'all' | CampaignSourceType;

export default function AnalyticsPage() {
  const queryClient = useQueryClient();
  const [dateFrom, setDateFrom] = useState(daysAgoISO(30));
  const [dateTo, setDateTo] = useState(todayISO());
  // Two-part selector: source-type filter chips + a campaign dropdown.
  // For paid we key by meta_campaign_id (string); for organic we key by
  // attora_campaign_id (UUID). selectedCampaign is the value from the dropdown
  // and selectedCampaignSource tells us how to interpret it.
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all');
  const [selectedCampaign, setSelectedCampaign] = useState<string>('');
  const [selectedCampaignSource, setSelectedCampaignSource] =
    useState<CampaignSourceType>('paid');
  const [syncing, setSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<string | null>(null);
  const [syncProgress, setSyncProgress] = useState(0);
  const syncTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const syncIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const dateRange = { date_from: dateFrom, date_to: dateTo };

  // Sync window matches the visible "from" date so the user sees the data
  // they just synced. Clamped to [1, 90] to satisfy the backend Meta cap.
  const syncDaysBack = (() => {
    const fromMs = new Date(dateFrom).getTime();
    if (Number.isNaN(fromMs)) return 30;
    const days = Math.ceil((Date.now() - fromMs) / 86_400_000);
    return Math.min(90, Math.max(1, days));
  })();
  const SYNC_ETA_MS = Math.min(240_000, Math.max(30_000, syncDaysBack * 2_000));

  const { data: campaigns = [] } = useQuery<CampaignSummary[]>({
    queryKey: ['campaigns-for-analytics', dateRange],
    queryFn: () => getCampaigns(dateRange),
  });

  const { data: organicCampaigns = [] } = useQuery<AdCampaign[]>({
    queryKey: ['ad-campaigns-organic'],
    queryFn: () => listAdCampaigns({ source_type: 'organic', is_active: true }),
  });

  // Build the campaign-scope query params:
  //   • specific paid campaign  → campaign_id (meta_campaign_id string)
  //   • specific organic campaign → attora_campaign_id (UUID)
  //   • source-type chip only (no specific campaign) → source_type aggregate
  //   • neither → no scoping (org-wide)
  const campaignScope: {
    campaign_id?: string;
    attora_campaign_id?: string;
    source_type?: 'paid' | 'organic';
  } = selectedCampaign
    ? selectedCampaignSource === 'organic'
      ? { attora_campaign_id: selectedCampaign }
      : { campaign_id: selectedCampaign }
    : sourceFilter !== 'all'
      ? { source_type: sourceFilter }
      : {};

  const analyticsQuery = useQuery({
    queryKey: [
      'analytics',
      dateRange,
      selectedCampaign,
      selectedCampaignSource,
      sourceFilter,
    ],
    queryFn: () =>
      getAnalytics({
        ...dateRange,
        ...campaignScope,
      }),
  });
  const roiQuery = useQuery({
    queryKey: [
      'roi',
      dateRange,
      selectedCampaign,
      selectedCampaignSource,
      sourceFilter,
    ],
    queryFn: () =>
      getROI({
        ...dateRange,
        ...campaignScope,
      }),
  });
  const aiPerfQuery = useQuery({
    queryKey: ['ai-performance', dateRange],
    queryFn: () => getAIPerformance(dateRange),
  });
  const conversationsQuery = useQuery({
    queryKey: ['conversations-count', dateRange],
    queryFn: () => getConversations({ ...dateRange, page: 1, page_size: 1 }),
  });

  const analytics = analyticsQuery.data ?? null;
  const roi = roiQuery.data ?? null;
  const aiPerf = aiPerfQuery.data ?? null;
  const conversationsTotal = conversationsQuery.data?.total ?? null;
  const loading =
    analyticsQuery.isLoading || roiQuery.isLoading || aiPerfQuery.isLoading || conversationsQuery.isLoading;
  const isFirstLoad =
    loading && (!analytics || !roi || !aiPerf);
  const error =
    analyticsQuery.isError || roiQuery.isError || aiPerfQuery.isError || conversationsQuery.isError
      ? 'Failed to load analytics data'
      : '';

  const load = useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: ['analytics', dateRange, selectedCampaign, selectedCampaignSource, sourceFilter],
      }),
      queryClient.invalidateQueries({
        queryKey: ['roi', dateRange, selectedCampaign, selectedCampaignSource, sourceFilter],
      }),
      queryClient.invalidateQueries({ queryKey: ['ai-performance', dateRange] }),
      queryClient.invalidateQueries({ queryKey: ['conversations-count', dateRange] }),
      queryClient.invalidateQueries({ queryKey: ['campaigns-for-analytics', dateRange] }),
      queryClient.invalidateQueries({ queryKey: ['ad-campaigns-organic'] }),
    ]);
  }, [queryClient, dateRange, selectedCampaign, selectedCampaignSource, sourceFilter]);

  useEffect(() => {
    return () => {
      if (syncTimeoutRef.current) clearTimeout(syncTimeoutRef.current);
      if (syncIntervalRef.current) clearInterval(syncIntervalRef.current);
    };
  }, []);

  async function handleSyncNow() {
    if (syncing) return;
    setSyncing(true);
    setSyncStatus('Syncing Meta data…');
    setSyncProgress(0);

    // Tick a fake progress bar against the estimated duration. Capped at 95%
    // so the user sees a final jump once the poll picks up the real result.
    const startedAt = Date.now();
    if (syncIntervalRef.current) clearInterval(syncIntervalRef.current);
    syncIntervalRef.current = setInterval(() => {
      const elapsed = Date.now() - startedAt;
      const pct = Math.min(95, Math.round((elapsed / SYNC_ETA_MS) * 100));
      setSyncProgress(pct);
    }, 500);

    // Hard ceiling so a stuck sync doesn't pin the UI forever. Backend can
    // run longer than this — the user can refresh to see the final result.
    const POLL_MAX_MS = 20 * 60 * 1000;
    const POLL_INTERVAL_MS = 3000;

    try {
      const kick = await syncMetaNow(syncDaysBack, true);
      setSyncStatus(kick.message);

      const pollStartedAt = Date.now();
      while (true) {
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
        let st;
        try {
          st = await getMetaSyncStatus();
        } catch {
          // Transient network blip — keep polling, the sync may still be running.
          continue;
        }
        if (st && st.in_progress === false && st.summary) {
          if (syncIntervalRef.current) {
            clearInterval(syncIntervalRef.current);
            syncIntervalRef.current = null;
          }
          setSyncProgress(100);
          setSyncStatus(st.message ?? 'Meta sync complete.');
          load();

          const errs = st.summary?.errors ?? null;
          const dwellMs = errs && errs.length > 0 ? 8000 : 4000;
          if (syncTimeoutRef.current) clearTimeout(syncTimeoutRef.current);
          syncTimeoutRef.current = setTimeout(() => {
            setSyncing(false);
            setSyncStatus(null);
            setSyncProgress(0);
          }, dwellMs);
          return;
        }
        if (Date.now() - pollStartedAt > POLL_MAX_MS) {
          if (syncIntervalRef.current) {
            clearInterval(syncIntervalRef.current);
            syncIntervalRef.current = null;
          }
          setSyncing(false);
          setSyncProgress(0);
          setSyncStatus(
            'Sync is taking longer than expected. It may still finish on the backend — refresh in a few minutes to see the latest data.'
          );
          return;
        }
      }
    } catch (err: unknown) {
      if (syncIntervalRef.current) {
        clearInterval(syncIntervalRef.current);
        syncIntervalRef.current = null;
      }
      setSyncing(false);
      setSyncProgress(0);

      // Surface as much detail as we can find. `detail` is FastAPI's standard
      // error shape, but a 5xx, proxy timeout, or unhandled exception lands us
      // somewhere else — fall back through every channel before the generic.
      let msg = 'Failed to run Meta sync. Check Settings → Meta credentials.';
      if (typeof err === 'object' && err !== null) {
        const e = err as {
          response?: { status?: number; statusText?: string; data?: unknown };
          message?: string;
          code?: string;
        };
        const status = e.response?.status;
        const statusText = e.response?.statusText;
        const data = e.response?.data;
        let body: string | null = null;
        if (typeof data === 'string') {
          body = data;
        } else if (data && typeof data === 'object') {
          const d = data as { detail?: unknown; message?: unknown };
          if (typeof d.detail === 'string') body = d.detail;
          else if (typeof d.message === 'string') body = d.message;
          else body = JSON.stringify(d);
        }
        if (status) {
          msg = `Meta sync failed (HTTP ${status}${statusText ? ` ${statusText}` : ''})${body ? `: ${body}` : ''}`;
        } else if (e.code === 'ECONNABORTED' || (e.message && e.message.toLowerCase().includes('timeout'))) {
          msg = 'Meta sync request timed out before the server replied. The sync may still be running on the backend — try refreshing in a minute.';
        } else if (e.message) {
          msg = `Meta sync failed: ${e.message}`;
        }
      }
      setSyncStatus(msg);
    }
  }

  function handleExport() {
    const token = localStorage.getItem('access_token');
    const url = getExportUrl({ date_from: dateFrom, date_to: dateTo });
    // Open in new tab with auth header via fetch + blob
    fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => res.blob())
      .then((blob) => {
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = `attora-analytics-${dateFrom}-to-${dateTo}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(blobUrl);
      })
      .catch(() => alert('Failed to export CSV'));
  }

  // Prepare AI performance fallback trend data for chart
  const fallbackTrendData = aiPerf?.fallback_trend?.map((t) => ({
    date: new Date(t.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    fallback_rate: t.value,
  })) || [];

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>
          <p className="mt-1 text-sm text-gray-500">
            Performance metrics, funnel analysis, and ROI reporting
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div
            role="radiogroup"
            aria-label="Campaign source filter"
            className="inline-flex overflow-hidden rounded-md border border-gray-300 bg-white text-xs font-medium"
          >
            {(['all', 'paid', 'organic'] as const).map((opt) => {
              const active = sourceFilter === opt;
              return (
                <button
                  key={opt}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => {
                    setSourceFilter(opt);
                    // Clear the campaign selection when the filter no longer
                    // contains it — avoids stale scoped queries.
                    if (
                      selectedCampaign &&
                      ((opt === 'paid' && selectedCampaignSource === 'organic') ||
                        (opt === 'organic' && selectedCampaignSource === 'paid'))
                    ) {
                      setSelectedCampaign('');
                    }
                  }}
                  className={
                    active
                      ? opt === 'organic'
                        ? 'bg-emerald-600 px-3 py-1.5 text-white'
                        : opt === 'paid'
                          ? 'bg-blue-600 px-3 py-1.5 text-white'
                          : 'bg-gray-900 px-3 py-1.5 text-white'
                      : 'bg-white px-3 py-1.5 text-gray-700 hover:bg-gray-50'
                  }
                >
                  {opt === 'all' ? 'All' : opt === 'paid' ? 'Paid' : 'Organic'}
                </button>
              );
            })}
          </div>
          {(() => {
            const paidOptions = campaigns.map((c) => {
              const name = c.meta_campaign_name || 'Unnamed';
              const status = c.status
                ? ` (${c.status.charAt(0).toUpperCase() + c.status.slice(1)})`
                : '';
              return {
                value: c.meta_campaign_id,
                label: `${name}${status}`,
                source: 'paid' as CampaignSourceType,
              };
            });
            const organicOptions = organicCampaigns.map((c) => ({
              value: c.id,
              label: `${c.name}${c.keyword ? ` [${c.keyword}]` : ''}`,
              source: 'organic' as CampaignSourceType,
            }));
            const filteredOptions =
              sourceFilter === 'paid'
                ? paidOptions
                : sourceFilter === 'organic'
                  ? organicOptions
                  : [...paidOptions, ...organicOptions];

            return (
              <select
                value={selectedCampaign}
                onChange={(e) => {
                  const v = e.target.value;
                  setSelectedCampaign(v);
                  if (!v) return;
                  const match = filteredOptions.find((o) => o.value === v);
                  if (match) setSelectedCampaignSource(match.source);
                }}
                className="w-64 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-300"
              >
                <option value="">All Campaigns</option>
                {sourceFilter !== 'organic' && paidOptions.length > 0 && (
                  <optgroup label="Paid">
                    {paidOptions.map((o) => (
                      <option key={`paid-${o.value}`} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </optgroup>
                )}
                {sourceFilter !== 'paid' && organicOptions.length > 0 && (
                  <optgroup label="Organic">
                    {organicOptions.map((o) => (
                      <option key={`organic-${o.value}`} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
            );
          })()}
          <DateRangePicker
            dateFrom={dateFrom}
            dateTo={dateTo}
            onChange={(from, to) => {
              setDateFrom(from);
              setDateTo(to);
            }}
          />
          <Button
            variant="primary"
            onClick={handleSyncNow}
            loading={syncing}
            disabled={syncing}
          >
            {!syncing && (
              <svg className="mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
              </svg>
            )}
            {syncing ? 'Syncing Meta…' : 'Sync Meta Data'}
          </Button>
          <Button variant="secondary" onClick={handleExport}>
            <svg className="mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
            </svg>
            Export CSV
          </Button>
        </div>
      </div>

      {syncStatus && (
        <div className="mb-4 rounded-lg border border-primary-200 bg-primary-50 px-4 py-3 text-sm text-primary-800">
          <div className="flex items-center justify-between gap-4">
            <span>{syncStatus}</span>
            {syncing && (
              <span className="text-xs font-medium text-primary-700 tabular-nums">
                {syncProgress}%
              </span>
            )}
          </div>
          {syncing && (
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-primary-100">
              <div
                className="h-full rounded-full bg-primary-600 transition-all duration-500 ease-linear"
                style={{ width: `${syncProgress}%` }}
              />
            </div>
          )}
        </div>
      )}

      {isFirstLoad ? (
        <LoadingSpinner className="mt-12" size="lg" />
      ) : error ? (
        <div className="mt-12 text-center text-red-600">{error}</div>
      ) : (
        <div className="space-y-6">
          {/* Metric Cards */}
          {analytics && (
            <AnalyticsMetricCards
              cpqc={analytics.cpqc}
              ccr={analytics.ccr}
              avgResponseTimeMs={analytics.avg_response_time_ms}
              qualificationRate={analytics.qualification_rate}
              hyrosConfirmedPurchases={analytics.hyros_confirmed_purchases}
              cpqcIncludesOrganic={!!selectedCampaign}
            />
          )}

          {/* Summary Stats */}
          {analytics && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="card text-center">
                <p className="text-xs text-gray-500 uppercase tracking-wider">Total Conversations</p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {conversationsTotal ?? analytics.total_conversations}
                </p>
                <Link
                  to={`/conversations?date_from=${encodeURIComponent(dateFrom)}&date_to=${encodeURIComponent(dateTo)}`}
                  className="mt-2 inline-block text-xs font-medium text-primary-700 hover:text-primary-800"
                >
                  View conversations
                </Link>
              </div>
              <div className="card text-center">
                <p className="text-xs text-gray-500 uppercase tracking-wider">Total Conversions</p>
                <p className="mt-1 text-2xl font-bold text-green-700">{analytics.total_conversions}</p>
              </div>
              <div className="card text-center">
                <p className="text-xs text-gray-500 uppercase tracking-wider">Total Revenue</p>
                <p className="mt-1 text-2xl font-bold text-green-700">{formatCurrency(analytics.total_revenue)}</p>
              </div>
            </div>
          )}

          {/* Funnel */}
          {analytics && <FunnelChart steps={analytics.funnel} />}

          {/* Trend Charts */}
          {analytics && (
            <TrendChart
              title="CPQC & CCR Daily Trends (with 7-day rolling average)"
              cpqcTrend={analytics.cpqc_trend}
              ccrTrend={analytics.ccr_trend}
            />
          )}

          {/* ROI Waterfall */}
          {roi && <ROIWaterfall roi={roi} />}

          {/* AI Performance */}
          {aiPerf && (
            <div className="card">
              <h3 className="text-sm font-semibold text-gray-900 mb-4">AI Performance</h3>
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-4 mb-6">
                <div>
                  <p className="text-xs text-gray-500">Fallback Rate</p>
                  <p className="text-xl font-bold text-gray-900">
                    {aiPerf.fallback_rate != null ? formatPercentRaw(aiPerf.fallback_rate * 100) : '—'}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Avg Response Time</p>
                  <p className="text-xl font-bold text-gray-900">
                    {aiPerf.avg_response_time_ms != null ? formatDuration(aiPerf.avg_response_time_ms) : '—'}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Total AI Tokens</p>
                  <p className="text-xl font-bold text-gray-900">
                    {(aiPerf.total_ai_tokens ?? 0).toLocaleString()}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Total AI Cost</p>
                  <p className="text-xl font-bold text-gray-900">
                    {formatCurrency(aiPerf.total_ai_cost ?? 0)}
                  </p>
                </div>
              </div>

              {/* Fallback rate trend */}
              {fallbackTrendData.length > 0 && (
                <div>
                  <h4 className="text-xs font-medium text-gray-500 mb-3">
                    Fallback Rate Trend
                  </h4>
                  <div className="h-48">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={fallbackTrendData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                        <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#9ca3af" />
                        <YAxis tick={{ fontSize: 11 }} stroke="#9ca3af" />
                        <Tooltip
                          contentStyle={{
                            fontSize: 12,
                            borderRadius: 8,
                            border: '1px solid #e5e7eb',
                          }}
                        />
                        <Line
                          type="monotone"
                          dataKey="fallback_rate"
                          stroke="#f59e0b"
                          strokeWidth={2}
                          dot={false}
                          name="Fallback Rate"
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Demographic & Platform Breakdowns — only meaningful for paid campaigns
              (organic posts have no Meta ad-set/ad rows to break down). */}
          {selectedCampaign && selectedCampaignSource === 'paid' && (
            <BreakdownCharts
              campaignId={selectedCampaign}
              dateFrom={dateFrom}
              dateTo={dateTo}
            />
          )}

          {/* Campaign Drill-Down: ad sets and ads — paid only. */}
          {selectedCampaign && selectedCampaignSource === 'paid' && (() => {
            const matchedCampaign = campaigns.find(
              (c) => c.meta_campaign_id === selectedCampaign
            );
            return matchedCampaign ? (
              <CampaignDrillDown
                campaignId={selectedCampaign}
                dateFrom={dateFrom}
                dateTo={dateTo}
                campaign={matchedCampaign}
              />
            ) : null;
          })()}
        </div>
      )}
    </div>
  );
}
