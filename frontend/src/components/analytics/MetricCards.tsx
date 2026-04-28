import { formatCurrency, formatPercent, formatDuration } from '../../utils/formatters';

interface AnalyticsMetricCardsProps {
  cpqc: number | null;
  ccr: number | null;
  avgResponseTimeMs: number | null;
  qualificationRate: number | null;
  hyrosConfirmedPurchases?: number;
  cpqcIncludesOrganic?: boolean;
}

interface MetricItem {
  label: string;
  value: string;
  description: string;
  color: string;
}

export default function AnalyticsMetricCards({
  cpqc,
  ccr,
  avgResponseTimeMs,
  qualificationRate,
  hyrosConfirmedPurchases = 0,
  cpqcIncludesOrganic = false,
}: AnalyticsMetricCardsProps) {
  const metrics: MetricItem[] = [
    {
      label: 'Hyros Confirmed Purchases',
      value: hyrosConfirmedPurchases.toLocaleString(),
      description: 'Purchases confirmed via Hyros attribution',
      color: 'border-blue-200 bg-blue-50',
    },
    {
      label: 'CPQC',
      value: cpqc != null ? formatCurrency(cpqc) : '—',
      description: cpqcIncludesOrganic
        ? 'Cost Per Qualified Conversation (incl. organic at $0)'
        : 'Cost Per Qualified Conversation',
      color: cpqc != null ? (cpqc <= 5 ? 'border-green-200 bg-green-50' : cpqc <= 15 ? 'border-yellow-200 bg-yellow-50' : 'border-red-200 bg-red-50') : 'border-gray-200 bg-gray-50',
    },
    {
      label: 'CCR',
      value: ccr != null ? formatPercent(ccr) : '—',
      description: 'Conversation Conversion Rate',
      color: ccr != null ? (ccr >= 0.1 ? 'border-green-200 bg-green-50' : ccr >= 0.05 ? 'border-yellow-200 bg-yellow-50' : 'border-red-200 bg-red-50') : 'border-gray-200 bg-gray-50',
    },
    {
      label: 'Avg Response Time',
      value: avgResponseTimeMs != null ? formatDuration(avgResponseTimeMs) : '—',
      description: 'Average AI response latency',
      color: avgResponseTimeMs != null ? (avgResponseTimeMs <= 5000 ? 'border-green-200 bg-green-50' : avgResponseTimeMs <= 8000 ? 'border-yellow-200 bg-yellow-50' : 'border-red-200 bg-red-50') : 'border-gray-200 bg-gray-50',
    },
    {
      label: 'Qualification Rate',
      value: qualificationRate != null ? formatPercent(qualificationRate) : '—',
      description: 'Conversations reaching qualified stage',
      color: qualificationRate != null ? (qualificationRate >= 0.3 ? 'border-green-200 bg-green-50' : qualificationRate >= 0.15 ? 'border-yellow-200 bg-yellow-50' : 'border-red-200 bg-red-50') : 'border-gray-200 bg-gray-50',
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {metrics.map((metric) => (
        <div
          key={metric.label}
          className={`rounded-xl border p-5 shadow-sm ${metric.color}`}
        >
          <p className="text-xs font-medium uppercase tracking-wider text-gray-500">
            {metric.label}
          </p>
          <p className="mt-2 text-2xl font-bold text-gray-900">{metric.value}</p>
          <p className="mt-1 text-xs text-gray-500">{metric.description}</p>
        </div>
      ))}
    </div>
  );
}
