import { BatteryCharging, House, Sun, Users, Zap } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { livePower } from '@/data/mock';
import { cn } from '@/lib/cn';
import { kw, percent } from '@/lib/format';

/**
 * Where this household's energy is going, right now.
 *
 * Node positions are percentages over a fixed-height box; the connecting lines
 * are one SVG stretched to the same box with `preserveAspectRatio="none"`, so
 * the endpoints stay glued to the nodes at any width. `non-scaling-stroke`
 * keeps the line weight uniform despite that stretch.
 */

interface FlowNodeProps {
  left: string;
  top: string;
  icon: LucideIcon;
  label: string;
  value: string;
  caption?: string;
  tone: 'solar' | 'battery' | 'peer' | 'grid' | 'home';
  size?: 'md' | 'lg';
  idle?: boolean;
}

const NODE_TONES: Record<FlowNodeProps['tone'], { ring: string; bg: string; icon: string }> = {
  solar: { ring: 'border-solar-200', bg: 'bg-solar-50', icon: 'text-solar-600' },
  battery: { ring: 'border-battery-200', bg: 'bg-battery-50', icon: 'text-battery-600' },
  peer: { ring: 'border-peer-200', bg: 'bg-peer-50', icon: 'text-peer-600' },
  grid: { ring: 'border-grid-200', bg: 'bg-grid-50', icon: 'text-grid-600' },
  home: { ring: 'border-stone-300', bg: 'bg-white', icon: 'text-stone-900' },
};

function FlowNode({
  left,
  top,
  icon: Icon,
  label,
  value,
  caption,
  tone,
  size = 'md',
  idle = false,
}: FlowNodeProps) {
  const tones = NODE_TONES[tone];

  return (
    <div
      className="absolute flex -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-2"
      style={{ left, top }}
    >
      <div
        className={cn(
          'flex items-center justify-center rounded-full border-2',
          size === 'lg' ? 'size-24' : 'size-16',
          idle ? 'border-stone-200 bg-stone-50' : cn(tones.ring, tones.bg),
        )}
      >
        <Icon
          className={cn(size === 'lg' ? 'size-9' : 'size-7', idle ? 'text-stone-400' : tones.icon)}
          strokeWidth={1.75}
          aria-hidden="true"
        />
      </div>
      <div className="text-center whitespace-nowrap">
        <p className="text-xs font-medium text-stone-500">{label}</p>
        <p
          className={cn(
            'font-mono text-sm font-bold tnum',
            idle ? 'text-stone-400' : 'text-stone-900',
          )}
        >
          {value}
        </p>
        {caption !== undefined && (
          <p className="text-[11px] font-medium text-stone-400">{caption}</p>
        )}
      </div>
    </div>
  );
}

interface FlowPathProps {
  d: string;
  color: string;
  active: boolean;
}

function FlowPath({ d, color, active }: FlowPathProps) {
  return (
    <>
      <path
        d={d}
        fill="none"
        strokeWidth={6}
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
        className="stroke-stone-200"
      />
      {active && (
        <path
          d={d}
          fill="none"
          strokeWidth={6}
          strokeLinecap="round"
          strokeDasharray="10 14"
          vectorEffect="non-scaling-stroke"
          className={cn('flow-dash', color)}
        />
      )}
    </>
  );
}

export function EnergyFlow() {
  const importingFromGrid = livePower.gridKw > 0;

  return (
    <div className="relative h-[380px] w-full">
      <svg
        viewBox="0 0 720 380"
        preserveAspectRatio="none"
        className="absolute inset-0 size-full"
        aria-hidden="true"
      >
        {/* Solar → home */}
        <FlowPath d="M360 78 V142" color="stroke-solar-500" active={livePower.solarKw > 0} />
        {/* Home → battery */}
        <FlowPath d="M312 190 H128" color="stroke-battery-500" active={livePower.batteryKw !== 0} />
        {/* Home → neighbours */}
        <FlowPath
          d="M407 179 Q500 152 593 135"
          color="stroke-peer-500"
          active={livePower.peerKw !== 0}
        />
        {/* Grid → home */}
        <FlowPath
          d="M593 259 Q500 232 406 204"
          color="stroke-grid-500"
          active={importingFromGrid}
        />
      </svg>

      <FlowNode
        left="50%"
        top="12%"
        icon={Sun}
        label="Solar"
        value={kw(livePower.solarKw)}
        tone="solar"
      />
      <FlowNode
        left="50%"
        top="50%"
        icon={House}
        label="Your home"
        value={kw(livePower.loadKw)}
        caption="consuming"
        tone="home"
        size="lg"
      />
      <FlowNode
        left="13.3%"
        top="50%"
        icon={BatteryCharging}
        label="Battery"
        value={kw(livePower.batteryKw)}
        caption={`charging · ${percent(livePower.batterySoc)}`}
        tone="battery"
      />
      <FlowNode
        left="86.7%"
        top="33.7%"
        icon={Users}
        label="Neighbours"
        value={kw(livePower.peerKw)}
        caption="selling to 3"
        tone="peer"
      />
      <FlowNode
        left="86.7%"
        top="70.5%"
        icon={Zap}
        label="Utility grid"
        value={kw(livePower.gridKw)}
        caption={importingFromGrid ? 'importing' : 'not needed'}
        tone="grid"
        idle={!importingFromGrid}
      />
    </div>
  );
}
