/**
 * Mock data standing in for the API until P1 wires the backend.
 *
 * Values are internally consistent on purpose — the flow diagram balances, the
 * order book actually crosses at the quoted clearing price, and the trade
 * rationales match the positions shown. A demo that contradicts itself teaches
 * the wrong thing about the product.
 */

import type {
  DaySummary,
  ForecastPoint,
  LivePower,
  MarketState,
  NetworkLine,
  NetworkNode,
  OrderLevel,
  PriceTick,
  Trade,
} from '@/types/energy';

export const MICROGRID_NAME = 'Kelambakkam Microgrid';
export const HOUSEHOLD_LABEL = 'House 17';

/** Solar in = load + battery + peers + grid. This balances exactly. */
export const livePower: LivePower = {
  solarKw: 3.24,
  loadKw: 1.08,
  batteryKw: 0.92,
  peerKw: 1.24,
  gridKw: 0,
  batterySoc: 78,
};

export const daySummary: DaySummary = {
  savedInr: 86.4,
  soldKwh: 12.4,
  boughtKwh: 2.1,
  selfSufficiency: 78,
  gridAvoidedKwh: 14.5,
};

export const marketState: MarketState = {
  tickNumber: 59,
  gateClosesInSeconds: 252,
  mechanism: 'Uniform-price double auction',
  clearingInr: 5.4,
  matchedKwh: 11.2,
  feedInTariff: 3.0,
  retailTariff: 8.0,
  participants: 42,
  curtailedKwh: 0.4,
};

/**
 * Six hours ahead in 15-minute steps, from 14:45.
 *
 * Generation follows a bell centred on 12:30; load ramps into the evening peak
 * at 20:30. The P10/P90 band widens with horizon, which is what an honest
 * probabilistic forecast does — certainty decays with distance.
 */
function buildForecast(): ForecastPoint[] {
  const startMinutes = 14 * 60 + 45;

  return Array.from({ length: 24 }, (_, index) => {
    const minutes = startMinutes + index * 15;
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;

    const solarBell = Math.exp(-((minutes - 750) ** 2) / (2 * 150 ** 2));
    const generation = minutes > 1125 ? 0 : Math.max(0, 4.8 * solarBell);

    const eveningPeak = Math.exp(-((minutes - 1230) ** 2) / (2 * 120 ** 2));
    const load = 0.85 + 1.6 * eveningPeak;

    // Uncertainty grows roughly 0.6% per interval out.
    const spread = 0.14 + index * 0.006;

    return {
      time: `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}`,
      genP10: Number((generation * (1 - spread)).toFixed(2)),
      genP50: Number(generation.toFixed(2)),
      genP90: Number((generation * (1 + spread)).toFixed(2)),
      loadP50: Number(load.toFixed(2)),
    };
  });
}

export const forecast: ForecastPoint[] = buildForecast();

/** Sell offers, ascending. Cumulative supply crosses demand at 11.2 kWh / ₹5.40. */
export const asks: OrderLevel[] = [
  { pricePerKwh: 3.1, kwh: 1.6, cumulativeKwh: 1.6, households: 2 },
  { pricePerKwh: 3.7, kwh: 2.2, cumulativeKwh: 3.8, households: 3 },
  { pricePerKwh: 4.3, kwh: 2.0, cumulativeKwh: 5.8, households: 2 },
  { pricePerKwh: 4.9, kwh: 2.8, cumulativeKwh: 8.6, households: 4 },
  { pricePerKwh: 5.4, kwh: 2.6, cumulativeKwh: 11.2, households: 3 },
  { pricePerKwh: 6.0, kwh: 1.5, cumulativeKwh: 12.7, households: 2 },
  { pricePerKwh: 6.6, kwh: 1.1, cumulativeKwh: 13.8, households: 1 },
];

/** Buy bids, descending. */
export const bids: OrderLevel[] = [
  { pricePerKwh: 7.8, kwh: 1.1, cumulativeKwh: 1.1, households: 1 },
  { pricePerKwh: 7.2, kwh: 1.7, cumulativeKwh: 2.8, households: 2 },
  { pricePerKwh: 6.6, kwh: 2.4, cumulativeKwh: 5.2, households: 3 },
  { pricePerKwh: 6.0, kwh: 2.7, cumulativeKwh: 7.9, households: 3 },
  { pricePerKwh: 5.4, kwh: 3.3, cumulativeKwh: 11.2, households: 4 },
  { pricePerKwh: 4.8, kwh: 1.5, cumulativeKwh: 12.7, households: 2 },
  { pricePerKwh: 4.2, kwh: 1.0, cumulativeKwh: 13.7, households: 1 },
];

/** Cumulative supply and demand, for the crossing chart. */
export const supplyDemandCurve = (() => {
  const prices = [3.1, 3.7, 4.3, 4.9, 5.4, 6.0, 6.6, 7.2, 7.8];

  return prices.map((price) => {
    const supply = asks
      .filter((level) => level.pricePerKwh <= price)
      .reduce((total, level) => total + level.kwh, 0);
    const demand = bids
      .filter((level) => level.pricePerKwh >= price)
      .reduce((total, level) => total + level.kwh, 0);

    return {
      price,
      supply: Number(supply.toFixed(1)),
      demand: Number(demand.toFixed(1)),
    };
  });
})();

/** The last 24 cleared ticks — six hours of market history. */
export const priceHistory: PriceTick[] = [
  { time: '08:45', clearingInr: 4.2, volumeKwh: 3.1 },
  { time: '09:00', clearingInr: 4.35, volumeKwh: 4.0 },
  { time: '09:15', clearingInr: 4.5, volumeKwh: 5.2 },
  { time: '09:30', clearingInr: 4.4, volumeKwh: 6.1 },
  { time: '09:45', clearingInr: 4.2, volumeKwh: 7.4 },
  { time: '10:00', clearingInr: 4.05, volumeKwh: 8.6 },
  { time: '10:15', clearingInr: 3.9, volumeKwh: 9.9 },
  { time: '10:30', clearingInr: 3.75, volumeKwh: 11.2 },
  { time: '10:45', clearingInr: 3.6, volumeKwh: 12.8 },
  { time: '11:00', clearingInr: 3.45, volumeKwh: 14.1 },
  { time: '11:15', clearingInr: 3.4, volumeKwh: 15.0 },
  { time: '11:30', clearingInr: 3.35, volumeKwh: 15.6 },
  { time: '11:45', clearingInr: 3.4, volumeKwh: 15.9 },
  { time: '12:00', clearingInr: 3.5, volumeKwh: 15.4 },
  { time: '12:15', clearingInr: 3.7, volumeKwh: 14.6 },
  { time: '12:30', clearingInr: 3.95, volumeKwh: 13.8 },
  { time: '12:45', clearingInr: 4.2, volumeKwh: 13.1 },
  { time: '13:00', clearingInr: 4.45, volumeKwh: 12.6 },
  { time: '13:15', clearingInr: 4.6, volumeKwh: 12.2 },
  { time: '13:30', clearingInr: 4.8, volumeKwh: 11.9 },
  { time: '13:45', clearingInr: 5.0, volumeKwh: 11.6 },
  { time: '14:00', clearingInr: 5.15, volumeKwh: 11.5 },
  { time: '14:15', clearingInr: 5.3, volumeKwh: 11.3 },
  { time: '14:30', clearingInr: 5.4, volumeKwh: 11.2 },
];

export const recentTrades: Trade[] = [
  {
    id: 'TRD-4821',
    at: '14:30',
    counterparty: 'House 08',
    side: 'sell',
    kwh: 2.1,
    pricePerKwh: 5.4,
    totalInr: 11.34,
    rationale:
      'Sold because your battery was already at 78% and this evening’s demand is forecast low. At ₹5.40 you earned ₹2.40/kWh more than the feed-in tariff.',
    bindingConstraint: null,
  },
  {
    id: 'TRD-4818',
    at: '14:15',
    counterparty: 'House 23',
    side: 'sell',
    kwh: 1.8,
    pricePerKwh: 5.3,
    totalInr: 9.54,
    rationale:
      'Surplus generation exceeded the battery’s remaining charge acceptance, so the excess was offered to the market rather than curtailed.',
    bindingConstraint: null,
  },
  {
    id: 'TRD-4811',
    at: '14:00',
    counterparty: 'House 31',
    side: 'sell',
    kwh: 1.4,
    pricePerKwh: 5.15,
    totalInr: 7.21,
    rationale:
      'Partially filled — the feeder segment to bus 31 reached 91% loading, so the grid safety layer curtailed 0.4 kWh of this offer.',
    bindingConstraint: 'Line 7→8 thermal limit',
  },
  {
    id: 'TRD-4804',
    at: '13:45',
    counterparty: 'House 12',
    side: 'sell',
    kwh: 2.3,
    pricePerKwh: 5.0,
    totalInr: 11.5,
    rationale:
      'Generation was 0.9 kW above forecast P50, and the additional surplus cleared against a neighbour’s evening pre-charge demand.',
    bindingConstraint: null,
  },
  {
    id: 'TRD-4796',
    at: '07:15',
    counterparty: 'House 05',
    side: 'buy',
    kwh: 2.1,
    pricePerKwh: 4.1,
    totalInr: 8.61,
    rationale:
      'Bought before sunrise while your battery was at 21%. At ₹4.10 this was ₹3.90/kWh cheaper than importing from the utility.',
    bindingConstraint: null,
  },
];

/** Twelve households on a radial feeder. Coordinates are laid out for the
 *  topology view; bus 1 is the substation transformer. */
export const networkNodes: NetworkNode[] = [
  {
    id: 'sub',
    label: 'Substation',
    bus: 1,
    role: 'consumer',
    netKw: -2.4,
    voltagePu: 1.0,
    status: 'ok',
    x: 60,
    y: 200,
  },
  {
    id: 'h02',
    label: 'House 02',
    bus: 2,
    role: 'prosumer',
    netKw: 1.8,
    voltagePu: 1.021,
    status: 'ok',
    x: 200,
    y: 96,
  },
  {
    id: 'h05',
    label: 'House 05',
    bus: 3,
    role: 'consumer',
    netKw: -1.2,
    voltagePu: 0.994,
    status: 'ok',
    x: 200,
    y: 200,
  },
  {
    id: 'h08',
    label: 'House 08',
    bus: 4,
    role: 'consumer',
    netKw: -2.2,
    voltagePu: 0.988,
    status: 'ok',
    x: 200,
    y: 304,
  },
  {
    id: 'h12',
    label: 'House 12',
    bus: 5,
    role: 'prosumer',
    netKw: 2.6,
    voltagePu: 1.034,
    status: 'ok',
    x: 340,
    y: 60,
  },
  {
    id: 'h17',
    label: 'House 17',
    bus: 6,
    role: 'prosumer',
    netKw: 1.24,
    voltagePu: 1.028,
    status: 'ok',
    x: 340,
    y: 164,
  },
  {
    id: 'h23',
    label: 'House 23',
    bus: 7,
    role: 'consumer',
    netKw: -1.6,
    voltagePu: 0.981,
    status: 'warning',
    x: 340,
    y: 268,
  },
  {
    id: 'h27',
    label: 'House 27',
    bus: 8,
    role: 'prosumer',
    netKw: 0.9,
    voltagePu: 1.019,
    status: 'ok',
    x: 340,
    y: 360,
  },
  {
    id: 'h31',
    label: 'House 31',
    bus: 9,
    role: 'consumer',
    netKw: -0.8,
    voltagePu: 0.979,
    status: 'warning',
    x: 480,
    y: 268,
  },
  {
    id: 'h34',
    label: 'House 34',
    bus: 10,
    role: 'prosumer',
    netKw: 3.1,
    voltagePu: 1.043,
    status: 'ok',
    x: 480,
    y: 108,
  },
  {
    id: 'h38',
    label: 'House 38',
    bus: 11,
    role: 'consumer',
    netKw: -1.1,
    voltagePu: 0.992,
    status: 'ok',
    x: 480,
    y: 200,
  },
  {
    id: 'h41',
    label: 'House 41',
    bus: 12,
    role: 'prosumer',
    netKw: 1.5,
    voltagePu: 1.031,
    status: 'ok',
    x: 480,
    y: 360,
  },
];

export const networkLines: NetworkLine[] = [
  { from: 'sub', to: 'h02', loadingPct: 42, status: 'ok' },
  { from: 'sub', to: 'h05', loadingPct: 58, status: 'ok' },
  { from: 'sub', to: 'h08', loadingPct: 64, status: 'ok' },
  { from: 'h02', to: 'h12', loadingPct: 37, status: 'ok' },
  { from: 'h05', to: 'h17', loadingPct: 51, status: 'ok' },
  { from: 'h08', to: 'h23', loadingPct: 91, status: 'warning' },
  { from: 'h08', to: 'h27', loadingPct: 46, status: 'ok' },
  { from: 'h23', to: 'h31', loadingPct: 73, status: 'ok' },
  { from: 'h12', to: 'h34', loadingPct: 33, status: 'ok' },
  { from: 'h17', to: 'h38', loadingPct: 29, status: 'ok' },
  { from: 'h27', to: 'h41', loadingPct: 40, status: 'ok' },
];

export const transformerLoadingPct = 68;
