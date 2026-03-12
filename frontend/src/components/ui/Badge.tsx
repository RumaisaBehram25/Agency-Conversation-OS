type BadgeColor =
  | 'gray'
  | 'blue'
  | 'green'
  | 'yellow'
  | 'red'
  | 'purple'
  | 'indigo'
  | 'pink';

interface BadgeProps {
  color?: BadgeColor;
  children: React.ReactNode;
  className?: string;
}

const colorClasses: Record<BadgeColor, string> = {
  gray: 'bg-gray-100 text-gray-700',
  blue: 'bg-blue-100 text-blue-700',
  green: 'bg-green-100 text-green-700',
  yellow: 'bg-yellow-100 text-yellow-800',
  red: 'bg-red-100 text-red-700',
  purple: 'bg-purple-100 text-purple-700',
  indigo: 'bg-indigo-100 text-indigo-700',
  pink: 'bg-pink-100 text-pink-700',
};

export default function Badge({
  color = 'gray',
  children,
  className = '',
}: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${colorClasses[color]} ${className}`}
    >
      {children}
    </span>
  );
}

// Helpers for common badge mappings
export function buyerStageBadgeColor(stage: string): BadgeColor {
  const map: Record<string, BadgeColor> = {
    awareness: 'blue',
    interest: 'indigo',
    consideration: 'purple',
    intent: 'yellow',
    evaluation: 'pink',
    purchase: 'green',
    converted: 'green',
  };
  return map[stage?.toLowerCase()] || 'gray';
}

export function statusBadgeColor(status: string): BadgeColor {
  const map: Record<string, BadgeColor> = {
    active: 'green',
    idle: 'yellow',
    closed: 'gray',
    escalated: 'red',
  };
  return map[status?.toLowerCase()] || 'gray';
}

export function channelBadgeColor(channel: string): BadgeColor {
  const map: Record<string, BadgeColor> = {
    messenger: 'blue',
    instagram: 'pink',
  };
  return map[channel?.toLowerCase()] || 'gray';
}
