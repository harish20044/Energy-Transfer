import {
  Activity,
  ArrowLeftRight,
  LayoutDashboard,
  Settings,
  Waypoints,
  type LucideIcon,
} from 'lucide-react';

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Exact-match only, so "/" does not stay active on every child route. */
  end?: boolean;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Microgrid',
    items: [
      { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
      { to: '/market', label: 'Live market', icon: Activity },
      { to: '/network', label: 'Grid network', icon: Waypoints },
    ],
  },
  {
    label: 'Account',
    items: [
      { to: '/trades', label: 'Trades', icon: ArrowLeftRight },
      { to: '/settings', label: 'Settings', icon: Settings },
    ],
  },
];

interface PageMeta {
  title: string;
  subtitle: string;
}

export const PAGE_META: Record<string, PageMeta> = {
  '/': {
    title: 'Dashboard',
    subtitle: 'Your household’s energy, right now',
  },
  '/market': {
    title: 'Live market',
    subtitle: 'Double auction clearing every 15 minutes',
  },
  '/network': {
    title: 'Grid network',
    subtitle: 'Feeder topology and constraint headroom',
  },
  '/trades': {
    title: 'Trades',
    subtitle: 'Every settled trade, with the reason behind it',
  },
  '/settings': {
    title: 'Settings',
    subtitle: 'Battery policy and trading preferences',
  },
};
