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

/** Energy over an interval. */
export function kwh(value: number): string {
  return `${value.toFixed(1)} kWh`;
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
