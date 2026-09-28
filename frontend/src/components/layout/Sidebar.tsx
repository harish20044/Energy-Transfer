import { CircleCheck, LogOut, Zap } from 'lucide-react';
import { NavLink } from 'react-router-dom';

import { useAuth } from '@/auth/useAuth';
import { NAV_GROUPS } from '@/components/layout/navigation';
import { cn } from '@/lib/cn';
import { ownMarketKw } from '@/lib/energy';
import { kw, percent } from '@/lib/format';
import { useLiveData } from '@/live/useLiveData';

const MICROGRID_NAME = '10-household microgrid';

/** First letter of each of up to two words, e.g. "Harish P" -> "HP". */
function initials(name: string): string {
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((part) => part.charAt(0).toUpperCase()).join('') || '?';
}

export function Sidebar() {
  const { user, logout } = useAuth();
  const { household, readings, trades, simulation } = useLiveData();

  const latest = readings[0];
  const exportingKw =
    latest !== undefined && simulation !== null
      ? Math.max(0, ownMarketKw(trades, household?.id ?? '', latest.tick_index, simulation.tick_minutes))
      : 0;
  const batterySocPct = latest !== undefined ? latest.battery_soc * 100 : 0;

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-stone-200 bg-white">
      <div className="flex items-center gap-3 px-5 py-5">
        <span className="flex size-9 items-center justify-center rounded-lg bg-stone-900">
          <Zap className="size-5 text-solar-500" strokeWidth={2.25} aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-bold tracking-tight text-stone-900">
            Energy&#8288;-&#8288;Transfer
          </p>
          <p className="truncate text-xs text-stone-500">{MICROGRID_NAME}</p>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-6 px-3 py-2">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="flex flex-col gap-1">
            <p className="px-3 pb-1 text-[11px] font-semibold tracking-wider text-stone-400 uppercase">
              {group.label}
            </p>
            {group.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end ?? false}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                    isActive
                      ? 'bg-stone-900 font-semibold text-white'
                      : 'font-medium text-stone-600 hover:bg-stone-100 hover:text-stone-900',
                  )
                }
              >
                <item.icon className="size-[18px] shrink-0" aria-hidden="true" />
                {item.label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      <div className="flex flex-col gap-3 border-t border-stone-200 p-4">
        <div className="rounded-lg bg-stone-50 p-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-stone-500">Exporting now</span>
            <span className="font-mono text-xs font-semibold text-peer-600 tnum">
              {kw(exportingKw)}
            </span>
          </div>
          <div className="mt-2 flex items-center justify-between">
            <span className="text-xs font-medium text-stone-500">Battery</span>
            <span className="font-mono text-xs font-semibold text-battery-600 tnum">
              {percent(batterySocPct)}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-peer-100 text-xs font-bold text-peer-700">
            {user !== null ? initials(user.display_name) : '?'}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-stone-900">
              {user?.display_name ?? 'Loading…'}
            </p>
            <p className="flex items-center gap-1 text-xs text-stone-500 capitalize">
              <CircleCheck className="size-3 shrink-0 text-battery-600" aria-hidden="true" />
              {user?.role ?? ''}
            </p>
          </div>
          <button
            type="button"
            onClick={logout}
            aria-label="Sign out"
            title="Sign out"
            className="flex size-8 shrink-0 items-center justify-center rounded-lg text-stone-400 transition-colors hover:bg-stone-100 hover:text-grid-600"
          >
            <LogOut className="size-4" aria-hidden="true" />
          </button>
        </div>
      </div>
    </aside>
  );
}
