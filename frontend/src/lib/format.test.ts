import { describe, expect, it } from 'vitest';

import { countdown, inr, inrWhole, kw, kwh, percent, perUnit, signed } from '@/lib/format';

describe('currency', () => {
  it('quotes trade prices to the paisa', () => {
    expect(inr(5.4)).toContain('5.40');
  });

  it('drops paisa from running totals', () => {
    expect(inrWhole(86.4)).toContain('86');
    expect(inrWhole(86.4)).not.toContain('.40');
  });
});

describe('energy units', () => {
  it('formats instantaneous power', () => {
    expect(kw(3.241)).toBe('3.24 kW');
  });

  it('formats energy over an interval', () => {
    expect(kwh(12.44)).toBe('12.4 kWh');
  });

  it('rounds percentages to whole numbers', () => {
    expect(percent(78.4)).toBe('78%');
  });

  it('formats per-unit voltage to three decimals', () => {
    expect(perUnit(1.0281)).toBe('1.028 pu');
  });
});

describe('countdown', () => {
  it('renders minutes and zero-padded seconds', () => {
    expect(countdown(252)).toBe('4:12');
    expect(countdown(65)).toBe('1:05');
  });

  it('never renders a negative clock', () => {
    expect(countdown(-30)).toBe('0:00');
  });
});

describe('signed', () => {
  it('prefixes a positive value', () => {
    expect(signed(2.1, kwh)).toBe('+2.1 kWh');
  });

  it('leaves a negative value to its own sign', () => {
    expect(signed(-2.1, kwh)).toBe('-2.1 kWh');
  });
});
