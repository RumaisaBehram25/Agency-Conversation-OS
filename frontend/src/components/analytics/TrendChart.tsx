import { useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  Brush,
  type TooltipProps,
} from 'recharts';
import type { DailyTrend } from '../../types';
import { formatCurrency } from '../../utils/formatters';

interface TrendChartProps {
  title: string;
  cpqcTrend: DailyTrend[];
  ccrTrend: DailyTrend[];
}

const SERIES: Record<string, { label: string; format: (v: number) => string; color: string }> = {
  cpqc: { label: 'CPQC', format: (v) => formatCurrency(v), color: '#818cf8' },
  cpqc_7d: { label: 'CPQC 7d Avg', format: (v) => formatCurrency(v), color: '#4f46e5' },
  ccr: { label: 'CCR', format: (v) => `${(v * 100).toFixed(2)}%`, color: '#86efac' },
  ccr_7d: { label: 'CCR 7d Avg', format: (v) => `${(v * 100).toFixed(2)}%`, color: '#22c55e' },
};

function CustomTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload || payload.length === 0) return null;
  const visible = payload.filter(
    (p) => p.value != null && Number.isFinite(p.value as number),
  );
  if (visible.length === 0) return null;
  return (
    <div className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs shadow-lg">
      <div className="font-semibold text-gray-900 mb-1">{label}</div>
      {visible.map((p) => {
        const meta = SERIES[(p.dataKey as string) ?? ''];
        const fmt = meta ? meta.format(p.value as number) : String(p.value);
        const lbl = meta ? meta.label : (p.name ?? p.dataKey);
        return (
          <div key={p.dataKey as string} className="flex items-center gap-2">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: (p.color as string) ?? meta?.color ?? '#9ca3af' }}
            />
            <span className="text-gray-600">{lbl}:</span>
            <span className="font-medium text-gray-900 tabular-nums">{fmt}</span>
          </div>
        );
      })}
    </div>
  );
}

// Rolling average that ignores nulls. If the window has no data points,
// the result is null too — so a stretch with no signal stays a gap on
// the chart instead of being interpolated to zero.
function computeRollingAvg(data: (number | null)[], window: number): (number | null)[] {
  return data.map((_, i) => {
    const start = Math.max(0, i - window + 1);
    const slice = data.slice(start, i + 1).filter((v): v is number => v != null);
    if (slice.length === 0) return null;
    return slice.reduce((a, b) => a + b, 0) / slice.length;
  });
}

export default function TrendChart({ title, cpqcTrend, ccrTrend }: TrendChartProps) {
  // Merge both trends by date. null values are preserved through the
  // pipeline so Recharts renders a gap rather than a zero baseline.
  const dateMap = new Map<
    string,
    { date: string; cpqc: number | null; ccr: number | null }
  >();

  cpqcTrend.forEach((t) => {
    dateMap.set(t.date, { date: t.date, cpqc: t.value, ccr: null });
  });
  ccrTrend.forEach((t) => {
    const existing = dateMap.get(t.date);
    if (existing) {
      existing.ccr = t.value;
    } else {
      dateMap.set(t.date, { date: t.date, cpqc: null, ccr: t.value });
    }
  });

  const sorted = Array.from(dateMap.values()).sort(
    (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
  );

  // 7-day rolling averages
  const cpqcValues = sorted.map((d) => d.cpqc);
  const ccrValues = sorted.map((d) => d.ccr);
  const cpqcRolling = computeRollingAvg(cpqcValues, 7);
  const ccrRolling = computeRollingAvg(ccrValues, 7);

  const chartData = sorted.map((d, i) => ({
    date: new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    cpqc: d.cpqc,
    ccr: d.ccr,
    cpqc_7d: cpqcRolling[i] != null ? Number(cpqcRolling[i]!.toFixed(2)) : null,
    ccr_7d: ccrRolling[i] != null ? Number(ccrRolling[i]!.toFixed(4)) : null,
  }));

  // Per-series visibility, toggled by clicking the legend.
  // Declared before the early-return so React's hooks order stays stable.
  const [hidden, setHidden] = useState<Record<string, boolean>>({});

  if (chartData.length === 0) {
    return (
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-900 mb-4">{title}</h3>
        <p className="text-sm text-gray-400">No trend data available</p>
      </div>
    );
  }

  const isHidden = (key: string) => hidden[key] === true;
  const toggle = (key: string) =>
    setHidden((prev) => ({ ...prev, [key]: !prev[key] }));

  // Format the percent ticks for the right axis
  const ccrTickFormatter = (v: number) => `${(v * 100).toFixed(0)}%`;
  const cpqcTickFormatter = (v: number) =>
    v >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v.toFixed(0)}`;

  return (
    <div className="card">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
        <p className="text-xs text-gray-400">
          Click a legend item to toggle • drag the brush to zoom
        </p>
      </div>
      <div className="h-96">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11 }}
              stroke="#9ca3af"
              minTickGap={20}
            />
            <YAxis
              yAxisId="left"
              tick={{ fontSize: 11 }}
              stroke="#9ca3af"
              tickFormatter={cpqcTickFormatter}
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
              tickFormatter={ccrTickFormatter}
              label={{
                value: 'CCR',
                angle: 90,
                position: 'insideRight',
                style: { fontSize: 11, fill: '#6b7280' },
              }}
            />
            <Tooltip
              content={<CustomTooltip />}
              cursor={{ stroke: '#9ca3af', strokeDasharray: '3 3' }}
            />
            <Legend
              wrapperStyle={{ fontSize: 12, cursor: 'pointer' }}
              onClick={(e) => {
                const key = (e?.dataKey as string) ?? '';
                if (key) toggle(key);
              }}
            />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="cpqc"
              stroke={SERIES.cpqc.color}
              strokeWidth={1}
              dot={false}
              activeDot={{ r: 5, strokeWidth: 0 }}
              opacity={0.45}
              name="CPQC Daily"
              hide={isHidden('cpqc')}
              connectNulls={false}
            />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="cpqc_7d"
              stroke={SERIES.cpqc_7d.color}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 5, strokeWidth: 0 }}
              name="CPQC 7d Avg"
              hide={isHidden('cpqc_7d')}
              connectNulls={false}
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="ccr"
              stroke={SERIES.ccr.color}
              strokeWidth={1}
              dot={false}
              activeDot={{ r: 5, strokeWidth: 0 }}
              opacity={0.45}
              name="CCR Daily"
              hide={isHidden('ccr')}
              connectNulls={false}
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="ccr_7d"
              stroke={SERIES.ccr_7d.color}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 5, strokeWidth: 0 }}
              name="CCR 7d Avg"
              hide={isHidden('ccr_7d')}
              connectNulls={false}
            />
            {chartData.length > 14 && (
              <Brush
                dataKey="date"
                height={22}
                stroke="#9ca3af"
                travellerWidth={8}
                startIndex={Math.max(0, chartData.length - 30)}
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
