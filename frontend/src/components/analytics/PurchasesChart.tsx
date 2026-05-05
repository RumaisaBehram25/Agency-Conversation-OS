import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { PurchasesDailyPoint } from '../../types';

interface PurchasesChartProps {
  purchasesOverTime: PurchasesDailyPoint[];
}

/** Hyros-synced purchase counts per calendar day (same scope as Cost per Purchase). */
export default function PurchasesChart({ purchasesOverTime }: PurchasesChartProps) {
  if (!purchasesOverTime.length) return null;

  const data = purchasesOverTime.map((row) => ({
    dateLabel: row.date,
    purchases: row.purchases,
  }));

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-900 mb-1">Hyros purchases over time</h3>
      <p className="text-xs text-gray-500 mb-4">
        Daily counts by Hyros sync timestamp; same date range and campaign scope as the tiles
        above.
      </p>
      <div className="h-56 w-full min-w-0">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
            <XAxis
              dataKey="dateLabel"
              tick={{ fontSize: 10 }}
              stroke="#9ca3af"
              interval="preserveStartEnd"
            />
            <YAxis
              allowDecimals={false}
              tick={{ fontSize: 10 }}
              stroke="#9ca3af"
              width={36}
            />
            <Tooltip
              contentStyle={{
                fontSize: 12,
                borderRadius: 8,
                border: '1px solid #e5e7eb',
              }}
              formatter={(value: number) => [`${value}`, 'Purchases']}
              labelFormatter={(label) => String(label)}
            />
            <Bar dataKey="purchases" name="Purchases" fill="#4f46e5" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
