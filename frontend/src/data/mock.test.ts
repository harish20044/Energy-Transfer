import { describe, expect, it } from 'vitest';

import {
  asks,
  bids,
  forecast,
  livePower,
  marketState,
  networkLines,
  networkNodes,
  priceHistory,
} from '@/data/mock';

/**
 * The mock data stands in for the API, so it has to obey the same rules the real
 * system does. A demo that violates its own invariants teaches the wrong thing
 * about the product — and these are the invariants P1's property tests will
 * enforce on the backend for real.
 */

describe('energy balance', () => {
  it('conserves power at the household', () => {
    const consumed = livePower.loadKw + livePower.batteryKw + livePower.peerKw + livePower.gridKw;

    expect(consumed).toBeCloseTo(livePower.solarKw, 2);
  });
});

describe('order book', () => {
  it('crosses at the advertised clearing price and volume', () => {
    const marginalAsk = asks.find((level) => level.cumulativeKwh === marketState.matchedKwh);
    const marginalBid = bids.find((level) => level.cumulativeKwh === marketState.matchedKwh);

    expect(marginalAsk?.pricePerKwh).toBe(marketState.clearingInr);
    expect(marginalBid?.pricePerKwh).toBe(marketState.clearingInr);
  });

  it('lists asks ascending and bids descending', () => {
    const askPrices = asks.map((level) => level.pricePerKwh);
    const bidPrices = bids.map((level) => level.pricePerKwh);

    expect(askPrices).toEqual([...askPrices].sort((a, b) => a - b));
    expect(bidPrices).toEqual([...bidPrices].sort((a, b) => b - a));
  });

  it('accumulates volume monotonically', () => {
    for (const book of [asks, bids]) {
      let running = 0;
      for (const level of book) {
        running += level.kwh;
        expect(level.cumulativeKwh).toBeCloseTo(running, 5);
      }
    }
  });
});

describe('individual rationality', () => {
  it('keeps every cleared price inside the tariff band', () => {
    // Outside this band, one side would be better off dealing with the utility,
    // which is exactly what objective O6 forbids.
    for (const tick of priceHistory) {
      expect(tick.clearingInr).toBeGreaterThanOrEqual(marketState.feedInTariff);
      expect(tick.clearingInr).toBeLessThanOrEqual(marketState.retailTariff);
    }
  });

  it('leaves a spread that a trade can sit inside', () => {
    expect(marketState.feedInTariff).toBeLessThan(marketState.retailTariff);
  });
});

describe('forecast', () => {
  it('keeps the quantiles ordered', () => {
    for (const point of forecast) {
      expect(point.genP10).toBeLessThanOrEqual(point.genP50);
      expect(point.genP50).toBeLessThanOrEqual(point.genP90);
    }
  });

  it('widens the interval as the horizon grows', () => {
    const withGeneration = forecast.filter((point) => point.genP50 > 0.5);
    const first = withGeneration.at(0);
    const last = withGeneration.at(-1);

    expect(first).toBeDefined();
    expect(last).toBeDefined();

    const relativeSpread = (p: { genP10: number; genP50: number; genP90: number }) =>
      (p.genP90 - p.genP10) / p.genP50;

    expect(relativeSpread(last as (typeof forecast)[number])).toBeGreaterThan(
      relativeSpread(first as (typeof forecast)[number]),
    );
  });

  it('never predicts negative generation', () => {
    for (const point of forecast) {
      expect(point.genP10).toBeGreaterThanOrEqual(0);
    }
  });
});

describe('network', () => {
  it('connects only nodes that exist', () => {
    const ids = new Set(networkNodes.map((node) => node.id));

    for (const line of networkLines) {
      expect(ids).toContain(line.from);
      expect(ids).toContain(line.to);
    }
  });

  it('holds every bus inside the statutory voltage band', () => {
    for (const node of networkNodes) {
      expect(node.voltagePu).toBeGreaterThanOrEqual(0.95);
      expect(node.voltagePu).toBeLessThanOrEqual(1.05);
    }
  });

  it('flags a line as warning only when it is actually near its limit', () => {
    for (const line of networkLines) {
      if (line.status === 'warning') expect(line.loadingPct).toBeGreaterThan(85);
      if (line.status === 'ok') expect(line.loadingPct).toBeLessThanOrEqual(85);
    }
  });
});
