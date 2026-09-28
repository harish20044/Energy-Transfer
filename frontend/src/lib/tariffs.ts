/** The tariff band every trade is bounded to — mirrors the backend's
 *  `Settings.feed_in_tariff` / `retail_tariff` defaults. Not fetched from an
 *  endpoint because there isn't one for static config; if these are ever
 *  changed from their defaults, this is the one place to update. */
export const FEED_IN_TARIFF = 3.0;
export const RETAIL_TARIFF = 8.0;
