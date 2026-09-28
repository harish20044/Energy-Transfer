/** Display formatters. Every number a user compares is rendered through one of these. */

const rupees = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const rupeesWhole = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
});

/** ₹5.40 — trade prices, which are always quoted to the paisa. */
export function inr(value: number): string {
  return rupees.format(value);
}

/** ₹86 — running totals, where paisa are noise. */
export function inrWhole(value: number): string {
  return rupeesWhole.format(value);
}

/** Instantaneous power. */
export function kw(value: number): string {
  return `${value.toFixed(2)} kW`;
}

/** Energy over an interval, in "units" — 1 unit = 1 kWh, the term every
 *  Indian electricity board bill and net-metering statement actually uses
 *  (always plural, even for a single unit — "1.00 units", exactly as an EB
 *  bill reads), so trading reads the way a real EB transaction would. Two
 *  decimals because a single 15-minute tick's energy is usually well under
 *  one whole unit; rounding to a whole number would make most ticks read as
 *  zero. */
export function kwh(value: number): string {
  return `${value.toFixed(2)} units`;
}

export function percent(value: number): string {
  return `${Math.round(value)}%`;
}

/** Per-unit voltage, the convention used for distribution-network limits. */
export function perUnit(value: number): string {
  return `${value.toFixed(3)} pu`;
}

/** Seconds remaining until the gate closes, as m:ss. */
export function countdown(totalSeconds: number): string {
  const safe = Math.max(0, totalSeconds);
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${String(minutes)}:${seconds.toString().padStart(2, '0')}`;
}

/** 14:45 — market ticks are always local wall-clock. */
export function clockTime(date: Date): string {
  return date.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

/** Signed change, for deltas that can go either way. */
export function signed(value: number, format: (n: number) => string): string {
  return value > 0 ? `+${format(value)}` : format(value);
}

/** The simulated clock's fractional hour-of-day (e.g. 13.25) as 13:15. */
export function simClock(hourOfDay: number): string {
  const totalMinutes = Math.round(hourOfDay * 60) % (24 * 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
}
