import type { FunnelStep } from '../../types';
import { formatNumber } from '../../utils/formatters';

interface FunnelChartProps {
  steps: FunnelStep[];
}

const stageColors: Record<string, string> = {
  awareness: 'bg-blue-500',
  interest: 'bg-indigo-500',
  consideration: 'bg-purple-500',
  intent: 'bg-yellow-500',
  evaluation: 'bg-pink-500',
  purchase: 'bg-green-500',
  converted: 'bg-green-600',
};

export default function FunnelChart({ steps }: FunnelChartProps) {
  if (!steps || steps.length === 0) {
    return (
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-900 mb-4">Conversion Funnel</h3>
        <p className="text-sm text-gray-400">No funnel data available</p>
      </div>
    );
  }

  const maxCount = Math.max(...steps.map((s) => s.count), 1);

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-900 mb-6">Conversion Funnel</h3>
      <div className="space-y-3">
        {steps.map((step, idx) => {
          const widthPercent = Math.max((step.count / maxCount) * 100, 4);
          const dropOff =
            idx > 0 && steps[idx - 1].count > 0
              ? (((steps[idx - 1].count - step.count) / steps[idx - 1].count) * 100).toFixed(1)
              : null;
          const barColor = stageColors[step.stage?.toLowerCase()] || 'bg-gray-400';

          return (
            <div key={step.stage}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-700 capitalize w-28">
                    {step.stage}
                  </span>
                  <span className="text-sm text-gray-900 font-semibold">
                    {formatNumber(step.count)}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {dropOff !== null && (
                    <span className="text-xs text-red-500">
                      -{dropOff}% drop
                    </span>
                  )}
                  <span className="text-xs text-gray-500 w-12 text-right">
                    {step.percentage.toFixed(1)}%
                  </span>
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
