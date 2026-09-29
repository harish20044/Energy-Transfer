import { DoorClosed, Moon, User, Wind } from 'lucide-react';

import type { Family } from '@/api/family';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/cn';
import { kw } from '@/lib/format';

const ROLE_LABEL: Record<string, string> = {
  parent: 'Parent',
  child: 'Child',
  grandparent: 'Grandparent',
  guest: 'Guest',
};

const OCCUPATION_LABEL: Record<string, string> = {
  office: 'office',
  hybrid: 'hybrid (WFH some days)',
  'night-shift': 'night shift',
  homemaker: 'homemaker',
  retired: 'retired',
  college: 'college',
  school: 'school',
  preschool: 'preschool',
  infant: 'infant',
  visiting: 'visiting',
};

const APPLIANCE_LABEL: Record<string, string> = {
  cooling: 'ACs',
  fans: 'Fans',
  lighting: 'Lights',
  kitchen: 'Kitchen',
  refrigerator: 'Fridge',
  water: 'Pump / RO / geyser',
  laundry: 'Washer / iron',
  entertainment: 'TV / laptops',
  ev: 'EV charging',
  standby: 'Standby',
};

function memberLocation(member: Family['members'][number]): string {
  if (member.room === null) return member.role === 'guest' ? 'Hall' : 'Parents’ room';
  return `Room ${String(member.room)}`;
}

const STATUS_TONE = { home: 'battery', away: 'neutral', asleep: 'peer' } as const;
const STATUS_LABEL = { home: 'Home', away: 'Away', asleep: 'Asleep' } as const;

export function FamilyPanel({ family }: { family: Family }) {
  const appliances = Object.entries(family.appliance_kw)
    .filter(([, value]) => value > 0.005)
    .sort(([, a], [, b]) => b - a);
  const total = appliances.reduce((sum, [, v]) => sum + v, 0);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-2 text-xs text-stone-500">
        <Badge>{family.house.bedrooms} bedrooms</Badge>
        <Badge>{family.house.washrooms} washrooms</Badge>
        <Badge>{family.house.halls} hall + kitchen</Badge>
        <Badge tone="battery">{family.house.ac_units} ACs</Badge>
      </div>

      <ul className="flex flex-col gap-2">
        {family.members.map((member) => (
          <li
            key={member.index}
            className="flex items-center justify-between gap-3 rounded-lg border border-stone-100 px-3 py-2"
          >
            <div className="flex items-center gap-2.5">
              <span
                className={cn(
                  'flex size-8 shrink-0 items-center justify-center rounded-full',
                  member.role === 'child'
                    ? 'bg-solar-50 text-solar-600'
                    : 'bg-peer-50 text-peer-600',
                )}
              >
                {member.status === 'asleep' ? (
                  <Moon className="size-4" aria-hidden="true" />
                ) : (
                  <User className="size-4" aria-hidden="true" />
                )}
              </span>
              <div>
                <p className="text-sm font-semibold text-stone-900">
                  {ROLE_LABEL[member.role] ?? member.role} · {member.age}y
                </p>
                <p className="text-xs text-stone-500">
                  {OCCUPATION_LABEL[member.occupation] ?? member.occupation} ·{' '}
                  {memberLocation(member)}
                </p>
              </div>
            </div>
            <Badge tone={STATUS_TONE[member.status]}>{STATUS_LABEL[member.status]}</Badge>
          </li>
        ))}
      </ul>

      <div>
        <p className="mb-2 text-xs font-semibold tracking-wider text-stone-400 uppercase">
          Bedrooms right now
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {family.rooms.map((room) => (
            <div
              key={room.room}
              className={cn(
                'flex flex-col items-center gap-1 rounded-lg border p-3 text-center',
                room.occupied
                  ? 'border-battery-200 bg-battery-50/50'
                  : 'border-stone-100 bg-stone-50',
              )}
            >
              {room.occupied ? (
                <Wind
                  className={cn('size-5', room.ac_on ? 'text-battery-600' : 'text-stone-400')}
                  aria-hidden="true"
                />
              ) : (
                <DoorClosed className="size-5 text-stone-300" aria-hidden="true" />
              )}
              <p className="text-xs font-semibold text-stone-700">Room {room.room}</p>
              <p className="text-[11px] text-stone-500">
                {room.ac_on ? `AC ${kw(room.ac_kw)}` : room.occupied ? 'Fan only' : 'Empty'}
              </p>
            </div>
          ))}
        </div>
      </div>

      {appliances.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-semibold tracking-wider text-stone-400 uppercase">
            Drawing now · {kw(total)}
          </p>
          <ul className="flex flex-col gap-1.5">
            {appliances.map(([name, value]) => (
              <li key={name} className="flex items-center gap-2 text-xs">
                <span className="w-32 shrink-0 text-stone-600">
                  {APPLIANCE_LABEL[name] ?? name}
                </span>
                <span className="h-2 flex-1 overflow-hidden rounded-full bg-stone-100">
                  <span
                    className="block h-full rounded-full bg-peer-500"
                    style={{ width: `${String(Math.max(2, (value / total) * 100))}%` }}
                  />
                </span>
                <span className="w-16 shrink-0 text-right font-mono text-stone-700 tnum">
                  {kw(value)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
