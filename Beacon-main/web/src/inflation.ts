/* Cost-of-living data.

   Source: the World Bank indicator API (no key, `Access-Control-Allow-Origin: *`,
   so the browser calls it directly and no Beacon credential is involved).
   FP.CPI.TOTL is the consumer price index rebased to 2010 = 100.

   The network is not trusted to be there: every read goes through a timeout, a
   bounded retry, a localStorage cache, and finally a bundled snapshot of the same
   series. The page therefore always renders real numbers, and always says which
   of the three it is showing. */

export type Source = "live" | "cache" | "bundled";

export interface CpiPoint {
  year: number;
  /** Consumer price index, 2010 = 100. */
  index: number;
}

export interface CpiSeries {
  country: string;
  countryCode: string;
  points: CpiPoint[];
  source: Source;
  /** When these numbers were retrieved (not when the World Bank published them). */
  fetchedAt: string;
}

export interface Country {
  code: string;
  name: string;
  currency: string;
  /** Intl locale used to format that currency. */
  locale: string;
}

/* Countries offered in the picker. Currency/locale drive formatting only; the
   index itself is whatever the World Bank returns for that country. */
export const COUNTRIES: Country[] = [
  { code: "IND", name: "India", currency: "INR", locale: "en-IN" },
  { code: "USA", name: "United States", currency: "USD", locale: "en-US" },
  { code: "GBR", name: "United Kingdom", currency: "GBP", locale: "en-GB" },
  { code: "SGP", name: "Singapore", currency: "SGD", locale: "en-SG" },
  { code: "DEU", name: "Germany", currency: "EUR", locale: "de-DE" },
  { code: "JPN", name: "Japan", currency: "JPY", locale: "ja-JP" },
  { code: "AUS", name: "Australia", currency: "AUD", locale: "en-AU" },
  { code: "ZAF", name: "South Africa", currency: "ZAR", locale: "en-ZA" },
];

/* A real FP.CPI.TOTL series, retrieved from the World Bank API and kept here so
   the page works with no network at all. Refresh with:
   curl "https://api.worldbank.org/v2/country/IND/indicator/FP.CPI.TOTL?format=json&per_page=20&date=2011:2024" */
const BUNDLED: Record<string, CpiPoint[]> = {
  IND: [
    { year: 2011, index: 108.9118 }, { year: 2012, index: 119.2355 },
    { year: 2013, index: 131.1804 }, { year: 2014, index: 139.9244 },
    { year: 2015, index: 146.7905 }, { year: 2016, index: 154.054 },
    { year: 2017, index: 159.1812 }, { year: 2018, index: 165.4511 },
    { year: 2019, index: 171.6216 }, { year: 2020, index: 182.9888 },
    { year: 2021, index: 192.3787 }, { year: 2022, index: 205.2662 },
    { year: 2023, index: 216.862 }, { year: 2024, index: 227.6033 },
  ],
};

const API = "https://api.worldbank.org/v2";
const INDICATOR = "FP.CPI.TOTL";
const CACHE_PREFIX = "beacon.cpi.v1.";
const CACHE_TTL_MS = 12 * 60 * 60 * 1000;
const TIMEOUT_MS = 8000;

function cacheKey(code: string): string {
  return `${CACHE_PREFIX}${code}`;
}

function readCache(code: string): CpiSeries | null {
  try {
    const raw = localStorage.getItem(cacheKey(code));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CpiSeries & { storedAt?: number };
    if (!parsed?.points?.length) return null;
    if (parsed.storedAt && Date.now() - parsed.storedAt > CACHE_TTL_MS) return null;
    return { ...parsed, source: "cache" };
  } catch {
    // private mode, blocked storage, or a shape from an older build
    return null;
  }
}

function writeCache(series: CpiSeries): void {
  try {
    localStorage.setItem(cacheKey(series.countryCode), JSON.stringify({ ...series, storedAt: Date.now() }));
  } catch {
    /* storage unavailable or full: the page does not depend on it */
  }
}

function bundledFor(code: string): CpiSeries {
  const country = COUNTRIES.find((c) => c.code === code);
  return {
    country: country?.name ?? code,
    countryCode: code,
    points: BUNDLED[code] ?? BUNDLED.IND,
    source: "bundled",
    fetchedAt: new Date(0).toISOString(),
  };
}

/** True when the offline snapshot holds a genuine series for that country. */
export function hasBundled(code: string): boolean {
  return Object.prototype.hasOwnProperty.call(BUNDLED, code);
}

/** Parse the World Bank envelope: [meta, rows], where a row may carry a null value. */
export function parseResponse(json: unknown, code: string): CpiSeries | null {
  if (!Array.isArray(json) || json.length < 2 || !Array.isArray(json[1])) return null;
  const rows = json[1] as Array<{ date?: string; value?: number | null; country?: { value?: string } }>;
  const points: CpiPoint[] = [];
  for (const r of rows) {
    const year = Number(r?.date);
    const index = r?.value;
    if (!Number.isFinite(year) || typeof index !== "number" || !Number.isFinite(index) || index <= 0) continue;
    points.push({ year, index });
  }
  if (points.length < 2) return null;
  points.sort((a, b) => a.year - b.year);
  const name = rows.find((r) => r?.country?.value)?.country?.value;
  return {
    country: name ?? COUNTRIES.find((c) => c.code === code)?.name ?? code,
    countryCode: code,
    points,
    source: "live",
    fetchedAt: new Date().toISOString(),
  };
}

async function fetchOnce(code: string, signal: AbortSignal): Promise<CpiSeries | null> {
  const url = `${API}/country/${encodeURIComponent(code)}/indicator/${INDICATOR}?format=json&per_page=60&date=2004:2035`;
  const resp = await fetch(url, { signal, headers: { Accept: "application/json" } });
  if (!resp.ok) throw new Error(`world bank responded ${resp.status}`);
  return parseResponse(await resp.json(), code);
}

/** One attempt with a hard timeout, honouring an outer abort (route change/unmount). */
async function withTimeout(code: string, outer?: AbortSignal): Promise<CpiSeries | null> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  const relay = () => ctrl.abort();
  outer?.addEventListener("abort", relay);
  try {
    return await fetchOnce(code, ctrl.signal);
  } finally {
    clearTimeout(timer);
    outer?.removeEventListener("abort", relay);
  }
}

/**
 * Live CPI for a country, degrading in order: network -> cache -> bundled.
 * Never rejects for an expected failure; the returned `source` says what happened.
 */
export async function loadCpi(code: string, outer?: AbortSignal): Promise<CpiSeries> {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    if (outer?.aborted) break;
    try {
      const live = await withTimeout(code, outer);
      if (live) {
        writeCache(live);
        return live;
      }
    } catch {
      // offline, CORS, DNS, timeout, or malformed JSON: fall through
    }
    if (attempt === 0 && !outer?.aborted) await new Promise((r) => setTimeout(r, 600));
  }
  return readCache(code) ?? bundledFor(code);
}

/* ---------- derived measures (pure, unit-testable) ---------- */

export function pointFor(series: CpiSeries, year: number): CpiPoint | null {
  return series.points.find((p) => p.year === year) ?? null;
}

export function latest(series: CpiSeries): CpiPoint | null {
  return series.points.length ? series.points[series.points.length - 1] : null;
}

/** Year-on-year inflation rate (%) for each year that has a predecessor. */
export function yoySeries(series: CpiSeries): Array<{ year: number; rate: number }> {
  const out: Array<{ year: number; rate: number }> = [];
  for (let i = 1; i < series.points.length; i += 1) {
    const prev = series.points[i - 1];
    const cur = series.points[i];
    if (prev.index > 0) out.push({ year: cur.year, rate: ((cur.index - prev.index) / prev.index) * 100 });
  }
  return out;
}

/**
 * What `amount` of `fromYear` money costs in `toYear` money.
 * Null when either year is missing from the series.
 */
export function adjust(series: CpiSeries, amount: number, fromYear: number, toYear: number): number | null {
  const a = pointFor(series, fromYear);
  const b = pointFor(series, toYear);
  if (!a || !b || a.index <= 0) return null;
  return (amount * b.index) / a.index;
}

/**
 * Purchasing power in `toYear` of an amount fixed in `fromYear`: the same
 * nominal money, expressed as what it can still buy.
 */
export function purchasingPower(series: CpiSeries, amount: number, fromYear: number, toYear: number): number | null {
  const a = pointFor(series, fromYear);
  const b = pointFor(series, toYear);
  if (!a || !b || b.index <= 0) return null;
  return (amount * a.index) / b.index;
}

/** Compound annual inflation between two years, in percent. */
export function cagr(series: CpiSeries, fromYear: number, toYear: number): number | null {
  const a = pointFor(series, fromYear);
  const b = pointFor(series, toYear);
  const span = toYear - fromYear;
  if (!a || !b || span <= 0 || a.index <= 0) return null;
  return ((b.index / a.index) ** (1 / span) - 1) * 100;
}

export function formatMoney(v: number | null, country: Country, maximumFractionDigits = 0): string {
  if (v == null || !Number.isFinite(v)) return "–";
  try {
    return new Intl.NumberFormat(country.locale, {
      style: "currency",
      currency: country.currency,
      maximumFractionDigits,
    }).format(v);
  } catch {
    // an exotic locale/currency pair the runtime rejects
    return `${Math.round(v)}`;
  }
}
