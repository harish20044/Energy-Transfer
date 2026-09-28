import { DoorClosed, User, Wind } from 'lucide-react';

import type { Family } from '@/api/family';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/cn';
import { percent } from '@/lib/format';

function memberLocation(member: Family['members'][number]): string {
  if (member.room === null) return 'With parents';
  return `Room ${String(member.room)}`;
}

export function FamilyPanel({ family }: { family: Family }) {
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
                  member.role === 'parent' ? 'bg-peer-50 text-peer-600' : 'bg-solar-50 text-solar-600',
                )}
              >
                <User className="size-4" aria-hidden="true" />
              </span>
              <div>
                <p className="text-sm font-semibold text-stone-900">
                  {member.role === 'parent' ? 'Parent' : 'Child'} · {member.age}y
                </p>
                <p className="text-xs text-stone-500">{memberLocation(member)}</p>
              </div>
            </div>
            <Badge tone={member.home_now ? 'battery' : 'neutral'}>
              {member.home_now ? 'Home' : 'Away'}
            </Badge>
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
                room.occupied ? 'border-battery-200 bg-battery-50/50' : 'border-stone-100 bg-stone-50',
              )}
            >
              {room.occupied ? (
                <Wind
                  className={cn('size-5', room.ac_intensity > 0.05 ? 'text-battery-600' : 'text-stone-400')}
                  aria-hidden="true"
                />
              ) : (
                <DoorClosed className="size-5 text-stone-300" aria-hidden="true" />
              )}
              <p className="text-xs font-semibold text-stone-700">Room {room.room}</p>
              <p className="text-[11px] text-stone-500">
                {room.occupied ? `AC ${percent(room.ac_intensity * 100)}` : 'Empty'}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
