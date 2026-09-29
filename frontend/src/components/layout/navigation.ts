import {
  Activity,
  ArrowLeftRight,
  CalendarPlus,
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
      { to: '/session', label: 'Plan session', icon: CalendarPlus },
      { to: '/market', label: 'Market', icon: Activity },
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
    subtitle: 'Your household’s forecast, trades and money this session',
  },
  '/session': {
    title: 'Plan a session',
    subtitle: 'Pick when, the weather and the what-ifs — then let the agents trade',
  },
  '/market': {
    title: 'Market',
    subtitle: 'One auction per hour — households and the EB',
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
