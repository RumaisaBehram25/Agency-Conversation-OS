/**
 * Relative display for last-activity timestamps (Leads & Conversations tables).
 */
export function formatTime(timestamp: string | number | Date | null | undefined): string {
  if (timestamp == null || timestamp === '') return '—';
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return '—';
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - date.getTime()) / 86400000);
  const isToday = date.toDateString() === now.toDateString();
  const isThisWeek = diffDays < 7;

  if (isToday) {
    return date.toLocaleString('en-US', { hour: 'numeric', minute: '2-digit' });
  }
  if (isThisWeek) {
    return date.toLocaleString('en-US', { weekday: 'short', hour: 'numeric', minute: '2-digit' });
  }
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}
