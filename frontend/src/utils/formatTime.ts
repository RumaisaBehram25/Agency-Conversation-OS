/**
 * Relative display for last-activity timestamps (Leads & Conversations tables).
 * Today / Yesterday / older dates — no commas (avoids cluttered UI).
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
    return `Today ${timeStr}`;
  }
  if (dayDiff === 1) {
    return `Yesterday ${timeStr}`;
  }

  const sameYear = date.getFullYear() === now.getFullYear();
  const month = date.toLocaleString('en-US', { month: 'short' });
  const day = date.getDate();
  const datePart = sameYear ? `${month} ${day}` : `${month} ${day} ${date.getFullYear()}`;
  return `${datePart} ${timeStr}`;
}
