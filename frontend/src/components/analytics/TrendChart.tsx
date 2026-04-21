import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import type { DailyTrend } from '../../types';

interface TrendChartProps {
  title: string;
  cpqcTrend: DailyTrend[];
  ccrTrend: DailyTrend[];
}

function computeRollingAvg(data: number[], window: number): number[] {
  return data.map((_, i) => {
    const start = Math.max(0, i - window + 1);
    const slice = data.slice(start, i + 1);
    return slice.reduce((a, b) => a + b, 0) / slice.length;
  });
}

export default function TrendChart({ title, cpqcTrend, ccrTrend }: TrendChartProps) {
  // Merge both trends by date
  const dateMap = new Map<
    string,
    { date: string; cpqc: number; ccr: number; cpqc_avg?: number; ccr_avg?: number }
  >();

  cpqcTrend.forEach((t) => {
    dateMap.set(t.date, { date: t.date, cpqc: t.value, ccr: 0 });
  });
  ccrTrend.forEach((t) => {
    const existing = dateMap.get(t.date);
    if (existing) {
      existing.ccr = t.value;
    } else {
      dateMap.set(t.date, { date: t.date, cpqc: 0, ccr: t.value });
    }
  });

  const sorted = Array.from(dateMap.values()).sort(
    (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
  );

  // Compute 7-day rolling averages
  const cpqcValues = sorted.map((d) => d.cpqc);
  const ccrValues = sorted.map((d) => d.ccr);
  const cpqcRolling = computeRollingAvg(cpqcValues, 7);
  const ccrRolling = computeRollingAvg(ccrValues, 7);

  const chartData = sorted.map((d, i) => ({
    date: new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    cpqc: d.cpqc,
    ccr: d.ccr,
    cpqc_7d: Number(cpqcRolling[i].toFixed(2)),
    ccr_7d: Number(ccrRolling[i].toFixed(4)),
  }));

  if (chartData.length === 0) {
    return (
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-900 mb-4">{title}</h3>
        <p className="text-sm text-gray-400">No trend data available</p>
      </div>
    );
  }

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-900 mb-4">{title}</h3>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11 }}
              stroke="#9ca3af"
            />
            <YAxis
              yAxisId="left"
              tick={{ fontSize: 11 }}
              stroke="#9ca3af"
              label={{
                value: 'CPQC ($)',
                angle: -90,
                position: 'insideLeft',
                style: { fontSize: 11, fill: '#6b7280' },
              }}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              tick={{ fontSize: 11 }}
              stroke="#9ca3af"
              label={{
                value: 'CCR',
                angle: 90,
                position: 'insideRight',
                style: { fontSize: 11, fill: '#6b7280' },
              }}
            />
            <Tooltip
              contentStyle={{
                fontSize: 12,
                borderRadius: 8,
                border: '1px solid #e5e7eb',
              }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="cpqc"
              stroke="#818cf8"
              strokeWidth={1}
              dot={false}
              opacity={0.4}
              name="CPQC Daily"
            />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="cpqc_7d"
              stroke="#4f46e5"
              strokeWidth={2}
              dot={false}
              name="CPQC 7d Avg"
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="ccr"
              stroke="#86efac"
              strokeWidth={1}
              dot={false}
              opacity={0.4}
              name="CCR Daily"
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="ccr_7d"
              stroke="#22c55e"
              strokeWidth={2}
              dot={false}
              name="CCR 7d Avg"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
