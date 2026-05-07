import { formatCurrency, formatPercent } from '../../utils/formatters';

interface AnalyticsMetricCardsProps {
  cpqc: number | null;
  ccr: number | null;
  qualificationRate: number | null;
  hyrosConfirmedPurchases?: number;
  costPerPurchase?: number | null;
  costPerConversation?: number | null;
  purchasesSyncedInRange?: number;
  distinctSubscribersConversationsStarted?: number;
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
  qualificationRate,
  hyrosConfirmedPurchases = 0,
  costPerPurchase = null,
  costPerConversation = null,
  purchasesSyncedInRange = 0,
  distinctSubscribersConversationsStarted = 0,
}: AnalyticsMetricCardsProps) {
  const metrics: MetricItem[] = [
    {
      label: 'Hyros Confirmed Purchases',
      value: hyrosConfirmedPurchases.toLocaleString(),
      description: 'Purchases confirmed via Hyros attribution',
      color: 'border-blue-200 bg-blue-50',
    },
    {
      label: 'Cost per Purchase',
      value: costPerPurchase != null ? formatCurrency(costPerPurchase) : '—',
      description: `Ad spend ÷ Hyros-synced purchases (${purchasesSyncedInRange} in range); — if no spend or no purchases`,
      color:
        costPerPurchase != null
          ? costPerPurchase <= 50
            ? 'border-green-200 bg-green-50'
            : costPerPurchase <= 150
              ? 'border-yellow-200 bg-yellow-50'
              : 'border-red-200 bg-red-50'
          : 'border-gray-200 bg-gray-50',
    },
    {
      label: 'Cost per Conversation',
      value: costPerConversation != null ? formatCurrency(costPerConversation) : '—',
      description: `Ad spend ÷ subscribers with a conversation started (${distinctSubscribersConversationsStarted}); — if no spend or none started`,
      color:
        costPerConversation != null
          ? costPerConversation <= 5
            ? 'border-green-200 bg-green-50'
            : costPerConversation <= 15
              ? 'border-yellow-200 bg-yellow-50'
              : 'border-red-200 bg-red-50'
          : 'border-gray-200 bg-gray-50',
    },
    {
      label: 'CPQC',
      value: cpqc != null ? formatCurrency(cpqc) : '—',
      description: 'Cost Per Qualified Conversation',
      color: cpqc != null ? (cpqc <= 5 ? 'border-green-200 bg-green-50' : cpqc <= 15 ? 'border-yellow-200 bg-yellow-50' : 'border-red-200 bg-red-50') : 'border-gray-200 bg-gray-50',
    },
    {
      label: 'CCR',
      value: ccr != null ? formatPercent(ccr) : '—',
      description: 'Conversation Conversion Rate',
      color: ccr != null ? (ccr >= 0.1 ? 'border-green-200 bg-green-50' : ccr >= 0.05 ? 'border-yellow-200 bg-yellow-50' : 'border-red-200 bg-red-50') : 'border-gray-200 bg-gray-50',
    },
    {
      label: 'Qualification Rate',
      value: qualificationRate != null ? formatPercent(qualificationRate) : '—',
      description: 'Conversations reaching qualified stage',
      color: qualificationRate != null ? (qualificationRate >= 0.3 ? 'border-green-200 bg-green-50' : qualificationRate >= 0.15 ? 'border-yellow-200 bg-yellow-50' : 'border-red-200 bg-red-50') : 'border-gray-200 bg-gray-50',
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-3">
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
