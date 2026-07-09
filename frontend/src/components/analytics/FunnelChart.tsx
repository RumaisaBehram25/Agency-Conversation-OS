import type { FunnelStep } from '../../types';
import { formatNumber } from '../../utils/formatters';

interface FunnelChartProps {
  steps: FunnelStep[];
  title?: string;
}

const stageColors: Record<string, string> = {
  conversations: 'bg-primary-500',
  qualified: 'bg-purple-500',
  converted: 'bg-green-600',
  awareness: 'bg-primary-400',
  consideration: 'bg-primary-600',
  intent: 'bg-yellow-500',
  purchase: 'bg-green-500',
};

export default function FunnelChart({ steps, title = 'Conversion Funnel' }: FunnelChartProps) {
  if (!steps || steps.length === 0) {
    return (
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-900 mb-4">{title}</h3>
        <p className="text-sm text-gray-400">No funnel data available</p>
      </div>
    );
  }

  const maxVolume = Math.max(...steps.map((s) => s.volume), 1);

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-900 mb-6">{title}</h3>
      <div className="space-y-3">
        {steps.map((step, idx) => {
          const widthPercent = Math.max((step.volume / maxVolume) * 100, 4);
          const barColor = stageColors[step.name?.toLowerCase()] || 'bg-gray-400';

          return (
            <div key={step.name}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-700 capitalize w-28">
                    {step.name}
                  </span>
                  <span className="text-sm text-gray-900 font-semibold">
                    {formatNumber(step.volume)}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {idx > 0 && step.drop_off_rate != null && (
                    <span className="text-xs text-red-500">
                      -{(step.drop_off_rate * 100).toFixed(1)}% drop
                    </span>
                  )}
                </div>
              </div>
              <div className="h-6 w-full rounded-full bg-gray-100">
                <div
                  className={`h-6 rounded-full ${barColor} transition-all duration-500`}
                  style={{ width: `${widthPercent}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
