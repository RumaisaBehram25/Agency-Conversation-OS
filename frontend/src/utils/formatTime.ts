/**
 * Relative display for last-activity timestamps (Leads & Conversations tables).
 * Today → "Today, {time}"; yesterday → "Yesterday, {time}"; older → date + time.
 */
export function formatTime(timestamp: string | number | Date | null | undefined): string {
  if (timestamp == null || timestamp === '') return '—';
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return '—';

  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfMsgDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const dayDiff = Math.round(
    (startOfToday.getTime() - startOfMsgDay.getTime()) / 86400000
  );

  const timeStr = date.toLocaleString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  });

  if (dayDiff === 0) {
    return `Today, ${timeStr}`;
  }
  if (dayDiff === 1) {
    return `Yesterday, ${timeStr}`;
  }

  const sameYear = date.getFullYear() === now.getFullYear();
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    ...(sameYear ? {} : { year: 'numeric' as const }),
    hour: 'numeric',
    minute: '2-digit',
  });
}
