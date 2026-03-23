import type { CampaignHealth as CampaignHealthType } from '../../types';

interface CampaignHealthProps {
  campaigns: CampaignHealthType[];
}

function statusLight(status: string) {
  switch (status) {
    case 'healthy':
      return (
        <span className="flex h-3 w-3 rounded-full bg-green-500" title="Healthy">
          <span className="inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-50" />
        </span>
      );
    case 'warning':
      return (
        <span className="flex h-3 w-3 rounded-full bg-yellow-500" title="Warning" />
      );
    case 'critical':
      return (
        <span className="flex h-3 w-3 rounded-full bg-red-500" title="Critical">
          <span className="inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75" />
        </span>
      );
    default:
      return <span className="flex h-3 w-3 rounded-full bg-gray-300" />;
  }
}

function statusLabel(status: string) {
  const classes: Record<string, string> = {
    healthy: 'text-green-700 bg-green-50',
    warning: 'text-yellow-700 bg-yellow-50',
    critical: 'text-red-700 bg-red-50',
  };
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
        classes[status] || 'text-gray-700 bg-gray-50'
      }`}
    >
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

export default function CampaignHealth({ campaigns }: CampaignHealthProps) {
  if (!campaigns || campaigns.length === 0) {
    return (
      <div className="card">
        <h3 className="text-sm font-medium text-gray-500 mb-3">Campaign Health</h3>
        <p className="text-sm text-gray-400">No active campaigns</p>
      </div>
    );
  }

  return (
    <div className="card">
      <h3 className="text-sm font-medium text-gray-500 mb-4">Campaign Health</h3>
      <div className="space-y-3">
        {campaigns.map((campaign, idx) => (
          <div
            key={idx}
            className="flex items-center justify-between rounded-lg border border-gray-100 bg-gray-50 px-4 py-3"
          >
            <div className="flex items-center gap-3">
              {statusLight(campaign.status)}
              <div>
                <p className="text-sm font-medium text-gray-900">
                  {campaign.campaign_name}
                </p>
                <p className="text-xs text-gray-500">
                  {campaign.metric}: {typeof campaign.value === 'number' ? campaign.value.toFixed(2) : campaign.value}
                </p>
              </div>
            </div>
            {statusLabel(campaign.status)}
          </div>
        ))}
      </div>
    </div>
  );
}
