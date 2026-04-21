interface DateRangePickerProps {
  dateFrom: string;
  dateTo: string;
  onChange: (dateFrom: string, dateTo: string) => void;
  className?: string;
}

const presets = [
  { label: '7d', days: 7 },
  { label: '14d', days: 14 },
  { label: '30d', days: 30 },
  { label: '90d', days: 90 },
];

function daysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().split('T')[0];
}

function today(): string {
  return new Date().toISOString().split('T')[0];
}

export default function DateRangePicker({
  dateFrom,
  dateTo,
  onChange,
  className = '',
}: DateRangePickerProps) {
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div className="flex items-center gap-1 rounded-lg border border-gray-300 bg-white px-1 py-1">
        {presets.map((preset) => (
          <button
            key={preset.label}
            onClick={() => onChange(daysAgo(preset.days), today())}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
              dateFrom === daysAgo(preset.days) && dateTo === today()
                ? 'bg-primary-600 text-white'
                : 'text-gray-600 hover:bg-gray-100'
            }`}
          >
            {preset.label}
          </button>
        ))}
      </div>
      <input
        type="date"
        value={dateFrom}
        onChange={(e) => onChange(e.target.value, dateTo)}
        className="input-field w-36 text-sm"
      />
      <span className="text-gray-400 text-sm">to</span>
      <input
        type="date"
        value={dateTo}
        onChange={(e) => onChange(dateFrom, e.target.value)}
        className="input-field w-36 text-sm"
      />
    </div>
  );
}
