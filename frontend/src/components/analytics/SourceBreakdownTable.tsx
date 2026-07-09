import { useMemo, useState } from 'react';
import type { HyrosSourceBreakdownRow } from '../../types';
import { formatCurrency } from '../../utils/formatters';

type SortKey =
  | 'traffic_source'
  | 'purchases_count'
  | 'conversations_count'
  | 'ad_spend'
  | 'cost_per_purchase'
  | 'cost_per_conversation';

interface SourceBreakdownTableProps {
  rows: HyrosSourceBreakdownRow[];
}

function displaySource(t: string | null | undefined): string {
  if (t == null || t === '') return 'organic';
  return t;
}

function fmtMoney(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  return formatCurrency(v);
}

function fmtPctish(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  return formatCurrency(v);
}

export default function SourceBreakdownTable({ rows }: SourceBreakdownTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('purchases_count');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const maxPurchases = useMemo(
    () => (rows.length ? Math.max(...rows.map((r) => r.purchases_count), 0) : 0),
    [rows],
  );

  const sorted = useMemo(() => {
    const copy = [...rows];
    const mul = sortDir === 'asc' ? 1 : -1;
    copy.sort((a, b) => {
      const av = keyVal(a, sortKey);
      const bv = keyVal(b, sortKey);
      if (av === bv) return displaySource(a.traffic_source).localeCompare(displaySource(b.traffic_source));
      if (typeof av === 'string' && typeof bv === 'string') return mul * av.localeCompare(bv);
      const an = Number(av);
      const bn = Number(bv);
      if (Number.isFinite(an) && Number.isFinite(bn) && an !== bn) return mul * (an < bn ? -1 : 1);
      return 0;
    });
    return copy;
  }, [rows, sortKey, sortDir]);

  function keyVal(r: HyrosSourceBreakdownRow, k: SortKey): string | number | null {
    switch (k) {
      case 'traffic_source':
        return displaySource(r.traffic_source).toLowerCase();
      case 'purchases_count':
        return r.purchases_count;
      case 'conversations_count':
        return r.conversations_count;
      case 'ad_spend':
        return r.ad_spend ?? -1;
      case 'cost_per_purchase':
        return r.cost_per_purchase ?? -1;
      case 'cost_per_conversation':
        return r.cost_per_conversation ?? -1;
      default:
        return 0;
    }
  }

  function toggleSort(k: SortKey) {
    if (sortKey === k) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(k);
      setSortDir('desc');
    }
  }

  if (!rows.length) return null;

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-900 mb-1">Hyros traffic source breakdown</h3>
      <p className="text-xs text-gray-500 mb-4">
        Sources are Hyros traffic source strings only — leads without Hyros attribution are omitted.
        Purchases use Hyros sync dates; spend is Meta campaign spend in the same range, split by
        purchaser mix per campaign.
      </p>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left">
              {(
                [
                  ['traffic_source', 'Source'],
                  ['purchases_count', 'Purchases'],
                  ['conversations_count', 'Conversations'],
                  ['ad_spend', 'Ad spend'],
                  ['cost_per_purchase', 'CPP'],
                  ['cost_per_conversation', 'CPC'],
                ] as const
              ).map(([key, label]) => (
                <th key={key} className="pb-2 pr-3 font-medium text-gray-500 text-xs uppercase tracking-wider">
                  <button
                    type="button"
                    onClick={() => toggleSort(key)}
                    className="inline-flex items-center gap-1 hover:text-gray-800"
                  >
                    {label}
                    {sortKey === key ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, idx) => {
              const highlight = maxPurchases > 0 && row.purchases_count === maxPurchases;
              return (
                <tr
                  key={`${displaySource(row.traffic_source)}-${idx}`}
                  className={`border-b border-gray-50 ${highlight ? 'bg-primary-50/80' : ''}`}
                >
                  <td className="py-2 pr-3 font-medium text-gray-900">{displaySource(row.traffic_source)}</td>
                  <td className="py-2 pr-3 tabular-nums">{row.purchases_count}</td>
                  <td className="py-2 pr-3 tabular-nums">{row.conversations_count}</td>
                  <td className="py-2 pr-3 tabular-nums">{fmtMoney(row.ad_spend)}</td>
                  <td className="py-2 pr-3 tabular-nums">{fmtPctish(row.cost_per_purchase)}</td>
                  <td className="py-2 pr-3 tabular-nums">{fmtPctish(row.cost_per_conversation)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
