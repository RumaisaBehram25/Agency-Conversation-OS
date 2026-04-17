import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { formatCurrency, formatNumber } from '../../utils/formatters';
import type { ROIResponse } from '../../types';

interface ROIWaterfallProps {
  roi: ROIResponse;
}

export default function ROIWaterfall({ roi }: ROIWaterfallProps) {
  const waterfallSteps = [
    { name: 'Ad Spend', value: roi.ad_spend, color: '#ef4444', displayValue: formatCurrency(roi.ad_spend) },
    { name: 'Conversations', value: roi.conversations_count, color: '#818cf8', displayValue: formatNumber(roi.conversations_count) },
    { name: 'Qualified', value: roi.qualified_count, color: '#a78bfa', displayValue: formatNumber(roi.qualified_count) },
    { name: 'Converted', value: roi.converted_count, color: '#22c55e', displayValue: formatNumber(roi.converted_count) },
    { name: 'Revenue', value: roi.revenue, color: '#16a34a', displayValue: formatCurrency(roi.revenue) },
  ];

  // Normalize to percentages for chart visualization
  const maxVal = Math.max(...waterfallSteps.map((s) => Math.abs(s.value)), 1);
  const chartData = waterfallSteps.map((step) => ({
    name: step.name,
    value: (Math.abs(step.value) / maxVal) * 100,
    color: step.color,
    displayValue: step.displayValue,
  }));

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-900 mb-2">ROI Waterfall</h3>
      <p className="text-xs text-gray-500 mb-6">
        Ad spend to revenue conversion pipeline
      </p>

      {/* Visual waterfall */}
      <div className="h-56 mb-6">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} stroke="#9ca3af" />
            <YAxis hide />
            <Tooltip
              formatter={(_value: number, _name: string, props: { payload?: { displayValue?: string } }) =>
                props.payload?.displayValue || ''
              }
              contentStyle={{
                fontSize: 12,
                borderRadius: 8,
                border: '1px solid #e5e7eb',
              }}
            />
            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
              {chartData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Metrics table */}
      <div className="grid grid-cols-2 gap-4 border-t border-gray-200 pt-4 sm:grid-cols-3 lg:grid-cols-5">
        <div>
          <p className="text-xs text-gray-500">Cost/Conversation</p>
          <p className="text-sm font-semibold text-gray-900">
            {roi.cost_per_conversation != null ? formatCurrency(roi.cost_per_conversation) : '—'}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Cost/Qualified</p>
          <p className="text-sm font-semibold text-gray-900">
            {roi.cost_per_qualified != null ? formatCurrency(roi.cost_per_qualified) : '—'}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">CPA</p>
          <p className="text-sm font-semibold text-gray-900">
            {roi.cpa != null ? formatCurrency(roi.cpa) : '—'}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">ROAS</p>
          <p className="text-sm font-semibold text-gray-900">
            {roi.roas != null ? `${roi.roas.toFixed(2)}x` : '—'}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Revenue</p>
          <p className="text-sm font-semibold text-green-700">
            {formatCurrency(roi.revenue ?? 0)}
          </p>
        </div>
      </div>

      {/* Before vs After */}
      {((roi.baseline_cpa ?? 0) > 0 || (roi.current_cpa ?? 0) > 0) && (
        <div className="mt-6 border-t border-gray-200 pt-4">
          <h4 className="text-xs font-semibold text-gray-700 uppercase tracking-wider mb-3">
            Before vs After Comparison
          </h4>
          <div className="overflow-hidden rounded-lg border border-gray-200">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Metric</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Baseline</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Current</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Change</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                <tr>
                  <td className="px-4 py-2 text-sm text-gray-700">CPA</td>
                  <td className="px-4 py-2 text-sm text-gray-900">{formatCurrency(roi.baseline_cpa)}</td>
                  <td className="px-4 py-2 text-sm text-gray-900">{formatCurrency(roi.current_cpa)}</td>
                  <td className="px-4 py-2 text-sm">
                    {roi.baseline_cpa > 0 ? (
                      <span
                        className={
                          roi.current_cpa < roi.baseline_cpa
                            ? 'text-green-600'
                            : 'text-red-600'
                        }
                      >
                        {roi.current_cpa < roi.baseline_cpa ? '-' : '+'}
                        {Math.abs(
                          ((roi.current_cpa - roi.baseline_cpa) / roi.baseline_cpa) * 100
                        ).toFixed(1)}
                        %
                      </span>
                    ) : (
                      <span className="text-gray-400">N/A</span>
                    )}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
