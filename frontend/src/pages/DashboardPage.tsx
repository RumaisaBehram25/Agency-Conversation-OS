import { useEffect, useState } from 'react';
import { getDashboard } from '../api/dashboard';
import type { DashboardResponse } from '../types';
import MetricCard from '../components/dashboard/MetricCard';
import CampaignHealth from '../components/dashboard/CampaignHealth';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { formatCurrency, formatPercent, formatNumber } from '../utils/formatters';

function getCPQCColor(cpqc: number): 'green' | 'yellow' | 'red' {
  if (cpqc <= 5) return 'green';
  if (cpqc <= 15) return 'yellow';
  return 'red';
}

function getCCRColor(ccr: number): 'green' | 'yellow' | 'red' {
  if (ccr >= 0.1) return 'green';
  if (ccr >= 0.05) return 'yellow';
  return 'red';
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    async function load() {
      try {
        const result = await getDashboard();
        setData(result);
      } catch {
        setError('Failed to load dashboard data');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return <LoadingSpinner className="mt-20" size="lg" />;
  }

  if (error) {
    return (
      <div className="mt-20 text-center">
        <p className="text-red-600">{error}</p>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="mt-1 text-sm text-gray-500">
          Overview of your Revenue Activation System performance
        </p>
      </div>

      {/* Primary Metrics: CPQC and CCR with sparklines */}
      <div className="mb-6 grid grid-cols-1 gap-6 md:grid-cols-2">
        <MetricCard
          title="Cost Per Qualified Conversation (CPQC)"
          value={formatCurrency(data.cpqc)}
          subtitle="7-day trend"
          trend={data.cpqc_trend}
          trendColor={getCPQCColor(data.cpqc)}
          large
          icon={
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
        />
        <MetricCard
          title="Conversation Conversion Rate (CCR)"
          value={formatPercent(data.ccr)}
          subtitle="7-day trend"
          trend={data.ccr_trend}
          trendColor={getCCRColor(data.ccr)}
          large
          icon={
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941" />
            </svg>
          }
        />
      </div>

      {/* Secondary metrics */}
      <div className="mb-6 grid grid-cols-1 gap-6 sm:grid-cols-3">
        <MetricCard
          title="Active Conversations"
          value={formatNumber(data.active_conversations_count)}
          icon={
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" />
            </svg>
          }
        />
        <MetricCard
          title="Today's Conversions"
          value={formatNumber(data.todays_conversions)}
          trendColor="green"
          icon={
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
        />
        <MetricCard
          title="Today's Revenue"
          value={formatCurrency(data.todays_revenue)}
          trendColor="green"
          icon={
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18.75a60.07 60.07 0 0115.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 013 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 00-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 01-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 003 15h-.75M15 10.5a3 3 0 11-6 0 3 3 0 016 0zm3 0h.008v.008H18V10.5zm-12 0h.008v.008H6V10.5z" />
            </svg>
          }
        />
      </div>

      {/* Campaign Health */}
      <CampaignHealth campaigns={data.campaign_health} />
    </div>
  );
}
