import { LineChart, Line, ResponsiveContainer } from 'recharts';
import type { DailyTrend } from '../../types';

interface MetricCardProps {
  title: string;
  value: string;
  subtitle?: string;
  trend?: DailyTrend[];
  trendColor?: 'green' | 'yellow' | 'red' | 'blue';
  icon?: React.ReactNode;
  large?: boolean;
}

const trendColorMap = {
  green: '#22c55e',
  yellow: '#eab308',
  red: '#ef4444',
  blue: '#6366f1',
};

const bgColorMap = {
  green: 'bg-green-50 border-green-200',
  yellow: 'bg-yellow-50 border-yellow-200',
  red: 'bg-red-50 border-red-200',
  blue: 'bg-white border-gray-200',
};

export default function MetricCard({
  title,
  value,
  subtitle,
  trend,
  trendColor = 'blue',
  icon,
  large = false,
}: MetricCardProps) {
  const chartData = trend?.map((t) => ({ value: t.value })) || [];

  return (
    <div
      className={`rounded-xl border p-6 shadow-sm ${bgColorMap[trendColor]} ${
        large ? 'col-span-1' : ''
      }`}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-sm font-medium text-gray-500">{title}</p>
          <p
            className={`mt-1 font-bold text-gray-900 ${
              large ? 'text-3xl' : 'text-2xl'
            }`}
          >
            {value}
          </p>
          {subtitle && (
            <p className="mt-1 text-sm text-gray-500">{subtitle}</p>
          )}
        </div>
        {icon && (
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-white/80 text-gray-600">
            {icon}
          </div>
        )}
      </div>

      {chartData.length > 1 && (
        <div className="mt-4 h-12">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <Line
                type="monotone"
                dataKey="value"
                stroke={trendColorMap[trendColor]}
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
