import { useEffect, useState } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  LabelList,
} from 'recharts';
import { getCampaignBreakdowns } from '../../api/campaigns';
import type { BreakdownItem } from '../../types';
import LoadingSpinner from '../ui/LoadingSpinner';
import { formatCurrency } from '../../utils/formatters';

interface BreakdownChartsProps {
  campaignId: string;
  dateFrom: string;
  dateTo: string;
}

/** Replace underscores with spaces and capitalize each word. */
function formatLabel(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Determine bar color for age/gender breakdowns. */
function getGenderColor(key: string): string {
  const lower = key.toLowerCase();
  if (lower.includes('male') && !lower.includes('female')) return '#3b82f6'; // blue
  if (lower.includes('female')) return '#ec4899'; // pink
  return '#9ca3af'; // gray for unknown
}

/** Distinct colors for platform breakdowns. */
const PLATFORM_COLORS: Record<string, string> = {
  instagram: '#a855f7',
  facebook: '#3b82f6',
  messenger: '#06b6d4',
  audience_network: '#f59e0b',
  whatsapp: '#22c55e',
};

function getPlatformColor(key: string): string {
  const lower = key.toLowerCase();
  for (const [platform, color] of Object.entries(PLATFORM_COLORS)) {
    if (lower.includes(platform)) return color;
  }
  return '#6b7280'; // fallback gray
}

export default function BreakdownCharts({ campaignId, dateFrom, dateTo }: BreakdownChartsProps) {
  const [ageGenderData, setAgeGenderData] = useState<BreakdownItem[]>([]);
  const [platformData, setPlatformData] = useState<BreakdownItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    Promise.all([
      getCampaignBreakdowns(campaignId, 'age_gender', { date_from: dateFrom, date_to: dateTo }),
      getCampaignBreakdowns(campaignId, 'platform', { date_from: dateFrom, date_to: dateTo }),
    ])
      .then(([ageGender, platform]) => {
        if (cancelled) return;
        // Sort by spend DESC
        setAgeGenderData([...ageGender].sort((a, b) => b.spend - a.spend));
        setPlatformData([...platform].sort((a, b) => b.spend - a.spend));
      })
      .catch(() => {
        if (cancelled) return;
        setAgeGenderData([]);
        setPlatformData([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [campaignId, dateFrom, dateTo]);

  if (loading) {
    return <LoadingSpinner className="mt-8" size="lg" />;
  }

  const hasAgeGender = ageGenderData.length > 0;
  const hasPlatform = platformData.length > 0;

  if (!hasAgeGender && !hasPlatform) {
    return (
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-900 mb-4">Demographic & Platform Breakdown</h3>
        <p className="text-sm text-gray-400">No breakdown data available</p>
      </div>
    );
  }

  const ageGenderChartData = ageGenderData.map((item) => ({
    ...item,
    label: formatLabel(item.breakdown_key),
  }));

  const platformChartData = platformData.map((item) => ({
    ...item,
    label: formatLabel(item.breakdown_key),
  }));

  const chartHeight = (items: unknown[]) => Math.max(items.length * 40, 200);

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      {/* Age/Gender Chart */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-900 mb-4">Age & Gender Breakdown</h3>
        {hasAgeGender ? (
          <div style={{ height: chartHeight(ageGenderChartData) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={ageGenderChartData} layout="vertical" margin={{ left: 20, right: 60 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis
                  type="number"
                  tick={{ fontSize: 11 }}
                  stroke="#9ca3af"
                  tickFormatter={(v: number) => formatCurrency(v)}
                />
                <YAxis
                  type="category"
                  dataKey="label"
                  tick={{ fontSize: 11 }}
                  stroke="#9ca3af"
                  width={100}
                />
                <Tooltip
                  contentStyle={{
                    fontSize: 12,
                    borderRadius: 8,
                    border: '1px solid #e5e7eb',
                  }}
                  formatter={(value: number) => formatCurrency(value)}
                  labelFormatter={(label: string) => label}
                />
                <Bar dataKey="spend" name="Spend" radius={[0, 4, 4, 0]}>
                  {ageGenderChartData.map((entry) => (
                    <Cell key={entry.breakdown_key} fill={getGenderColor(entry.breakdown_key)} />
                  ))}
                  <LabelList
                    dataKey="leads"
                    position="right"
                    formatter={(v: number) => `${v} leads`}
                    style={{ fontSize: 10, fill: '#6b7280' }}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="text-sm text-gray-400">No breakdown data available</p>
        )}
      </div>

      {/* Platform Chart */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-900 mb-4">Platform Breakdown</h3>
        {hasPlatform ? (
          <div style={{ height: chartHeight(platformChartData) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={platformChartData} layout="vertical" margin={{ left: 20, right: 60 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis
                  type="number"
                  tick={{ fontSize: 11 }}
                  stroke="#9ca3af"
                  tickFormatter={(v: number) => formatCurrency(v)}
                />
                <YAxis
                  type="category"
                  dataKey="label"
                  tick={{ fontSize: 11 }}
                  stroke="#9ca3af"
                  width={120}
                />
                <Tooltip
                  contentStyle={{
                    fontSize: 12,
                    borderRadius: 8,
                    border: '1px solid #e5e7eb',
                  }}
                  formatter={(value: number) => formatCurrency(value)}
                  labelFormatter={(label: string) => label}
                />
                <Bar dataKey="spend" name="Spend" radius={[0, 4, 4, 0]}>
                  {platformChartData.map((entry) => (
                    <Cell key={entry.breakdown_key} fill={getPlatformColor(entry.breakdown_key)} />
                  ))}
                  <LabelList
                    dataKey="leads"
                    position="right"
                    formatter={(v: number) => `${v} leads`}
                    style={{ fontSize: 10, fill: '#6b7280' }}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="text-sm text-gray-400">No breakdown data available</p>
        )}
      </div>
    </div>
  );
}
