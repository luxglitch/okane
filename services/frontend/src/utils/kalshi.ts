const SERIES_LABELS: Record<string, string> = {
  KXBTCD: "BTC",
  KXBTC:  "BTC",
  KXETH:  "ETH",
  KXETHD: "ETH",
  KXDOGE: "DOGE",
};

const MONTH_MAP: Record<string, string> = {
  JAN:"Jan",FEB:"Feb",MAR:"Mar",APR:"Apr",MAY:"May",JUN:"Jun",
  JUL:"Jul",AUG:"Aug",SEP:"Sep",OCT:"Oct",NOV:"Nov",DEC:"Dec",
};

/**
 * Returns a plain-English description of a Kalshi bet.
 * e.g. KXBTCD-26MAR1617-T74749.99, side=yes → "BTC > $74,750  Mar 16 17:xx UTC"
 */
export function betDescription(marketTicker: string, side: "yes" | "no"): string {
  // Extract parts: KXBTCD-26MAR1617-T74749.99
  const parts = marketTicker.split("-");
  if (parts.length < 3) return marketTicker;

  const series = parts[0].toUpperCase();
  const asset = SERIES_LABELS[series] ?? series;

  // Parse threshold from last segment (T74749.99 or B0.172)
  const lastPart = parts[parts.length - 1];
  const threshMatch = lastPart.match(/^[TB]([\d.]+)$/i);
  if (!threshMatch) return marketTicker;
  const threshold = parseFloat(threshMatch[1]);
  const threshStr = threshold >= 1
    ? `$${threshold.toLocaleString("en-US", { maximumFractionDigits: 0 })}`
    : `$${threshold.toFixed(4).replace(/0+$/, "")}`;

  // Parse date/hour from middle segment, e.g. 26MAR1617 = day=16, month=MAR, hour=17
  const datePart = parts[1]; // e.g. "26MAR1617"
  const dateMatch = datePart.match(/^(\d{2})([A-Z]{3})(\d{2})(\d{2})$/i);
  let whenStr = "";
  if (dateMatch) {
    const [, , mon, day, hour] = dateMatch;
    const monLabel = MONTH_MAP[mon.toUpperCase()] ?? mon;
    whenStr = ` · ${monLabel} ${parseInt(day)} ${hour}:xx UTC`;
  }

  const dir = side === "yes" ? ">" : "<";
  return `${asset} ${dir} ${threshStr}${whenStr}`;
}

const SERIES_SLUGS: Record<string, string> = {
  KXBTCD: "bitcoin-price-abovebelow",
  KXETH:  "ethereum-price-abovebelow",
  KXETHD: "ethereum-price-abovebelow",
  KXDOGE: "dogecoin-price-abovebelow",
};

export function kalshiUrl(marketTicker: string): string {
  // e.g. KXBTCD-26MAR1617-T74749.99 → event=KXBTCD-26MAR1617, series=KXBTCD
  const eventTicker = marketTicker.replace(/-T[\d.]+$/i, "");
  const series = eventTicker.split("-")[0].toUpperCase();
  const slug = SERIES_SLUGS[series];
  if (slug) {
    return `https://kalshi.com/markets/${series.toLowerCase()}/${slug}/${eventTicker.toLowerCase()}`;
  }
  return `https://kalshi.com/markets/${series.toLowerCase()}`;
}
