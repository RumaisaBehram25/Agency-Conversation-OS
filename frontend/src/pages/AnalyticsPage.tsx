import { useEffect, useState, useCallback } from 'react';
import { getAnalytics, getROI, getAIPerformance, getExportUrl } from '../api/analytics';
import type { AnalyticsResponse, ROIResponse, AIPerformanceResponse } from '../types';
import AnalyticsMetricCards from '../components/analytics/MetricCards';
import FunnelChart from '../components/analytics/FunnelChart';
import TrendChart from '../components/analytics/TrendChart';
import ROIWaterfall from '../components/analytics/ROIWaterfall';
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

export default function AnalyticsPage() {
  const [dateFrom, setDateFrom] = useState(daysAgoISO(30));
  const [dateTo, setDateTo] = useState(todayISO());

  const [analytics, setAnalytics] = useState<AnalyticsResponse | null>(null);
  const [roi, setRoi] = useState<ROIResponse | null>(null);
  const [aiPerf, setAiPerf] = useState<AIPerformanceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [analyticsData, roiData, aiPerfData] = await Promise.all([
        getAnalytics({ date_from: dateFrom, date_to: dateTo }),
        getROI({ date_from: dateFrom, date_to: dateTo }),
        getAIPerformance({ date_from: dateFrom, date_to: dateTo }),
      ]);
      setAnalytics(analyticsData);
      setRoi(roiData);
      setAiPerf(aiPerfData);
    } catch {
      setError('Failed to load analytics data');
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo]);

  useEffect(() => {
    load();
  }, [load]);

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
      .catch(() => setError('Failed to export CSV'));
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
        <div className="flex items-center gap-3">
          <DateRangePicker
            dateFrom={dateFrom}
            dateTo={dateTo}
            onChange={(from, to) => {
              setDateFrom(from);
              setDateTo(to);
            }}
          />
          <Button variant="secondary" onClick={handleExport}>
            <svg className="mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
            </svg>
            Export CSV
          </Button>
        </div>
      </div>

      {loading ? (
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
            />
          )}

          {/* Summary Stats */}
          {analytics && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="card text-center">
                <p className="text-xs text-gray-500 uppercase tracking-wider">Total Conversations</p>
                <p className="mt-1 text-2xl font-bold text-gray-900">{analytics.total_conversations}</p>
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
        </div>
      )}
    </div>
  );
}
