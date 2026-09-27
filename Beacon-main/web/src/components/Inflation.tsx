import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  COUNTRIES,
  adjust,
  cagr,
  formatMoney,
  latest,
  loadCpi,
  pointFor,
  purchasingPower,
  yoySeries,
  type CpiSeries,
  type Country,
} from "../inflation";
import { Icon } from "./Icon";

/* ------------------------------------------------------------------------
   Cost of living: what the same money still buys.

   Every number on this page is derived at runtime from a World Bank CPI
   series — nothing is hardcoded. The page states which source answered
   (live, cached, or the bundled snapshot) rather than pretending it is
   always live. Charts follow the house style used by Analytics.
   ------------------------------------------------------------------------ */

const H = 150;
const PAD = { l: 6, r: 6, t: 18, b: 22 };

function useWidth(): [React.RefObject<HTMLDivElement>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(600);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const read = () => setW(Math.max(200, Math.round(el.getBoundingClientRect().width)));
    read();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

function Frame({ title, meta, children }: { title: string; meta?: string; children: (w: number) => React.ReactNode }) {
  const [ref, w] = useWidth();
  return (
    <section className="chart">
      <header className="chart-h">
        <h3>{title}</h3>
        {meta ? <span className="meta">{meta}</span> : null}
      </header>
      <div ref={ref} className="chart-body">
        {children(w)}
      </div>
    </section>
  );
}

function Skeleton({ w }: { w: number }) {
  return (
    <div className="chart-skel" aria-busy="true" aria-label="loading">
      <svg viewBox={`0 0 ${w} ${H}`} aria-hidden="true">
        <line x1={PAD.l} x2={w - PAD.r} y1={H - PAD.b} y2={H - PAD.b} stroke="var(--line)" />
        {[46, 88, 62, 104, 70, 96, 54].map((h, i) => (
          <rect key={i} className="shimmer" x={PAD.l + 30 + i * 80} y={H - PAD.b - h} width={38} height={h} rx={2} />
        ))}
      </svg>
    </div>
  );
}

/** Index line: the level of prices over time. */
function IndexChart({ series, w }: { series: CpiSeries; w: number }) {
  const pts = series.points;
  const inner = w - PAD.l - PAD.r;
  const usable = H - PAD.t - PAD.b;
  const lo = Math.min(...pts.map((p) => p.index));
  const hi = Math.max(...pts.map((p) => p.index));
  const span = hi - lo || 1;
  const x = (i: number) => PAD.l + (inner * i) / Math.max(1, pts.length - 1);
  const y = (v: number) => PAD.t + usable - ((v - lo) / span) * usable;
  const line = pts.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.index).toFixed(1)}`).join(" ");
  const area = `${line} L${x(pts.length - 1).toFixed(1)},${(H - PAD.b).toFixed(1)} L${x(0).toFixed(1)},${(H - PAD.b).toFixed(1)} Z`;
  const every = pts.length > 10 ? Math.ceil(pts.length / 7) : 1;
  return (
    <svg
      className="plot"
      viewBox={`0 0 ${w} ${H}`}
      role="img"
      aria-label={`Consumer price index for ${series.country}, ${pts[0].year} to ${pts[pts.length - 1].year}`}
    >
      <line x1={PAD.l} x2={w - PAD.r} y1={H - PAD.b} y2={H - PAD.b} stroke="var(--line)" />
      <g className="text">
        <path className="area" d={area} />
        <path className="line" d={line} />
        <circle className="dot" cx={x(pts.length - 1)} cy={y(pts[pts.length - 1].index)} r={3.5} />
      </g>
      <g className="axis">
        {pts.map((p, i) => {
          const last = pts.length - 1;
          // drop a stepped label that would collide with the always-drawn final year
          const show = i === last || (i % every === 0 && last - i >= every * 0.75);
          if (!show) return null;
          return (
            <text key={p.year} x={x(i)} y={H - 6} textAnchor={i === 0 ? "start" : i === last ? "end" : "middle"}>
              {p.year}
            </text>
          );
        })}
      </g>
    </svg>
  );
}

/** Year-on-year rate: how fast prices moved each year. */
function RateChart({ series, w }: { series: CpiSeries; w: number }) {
  const rates = yoySeries(series);
  if (!rates.length) return <Skeleton w={w} />;
  const inner = w - PAD.l - PAD.r;
  const usable = H - PAD.t - PAD.b;
  const hi = Math.max(...rates.map((r) => Math.abs(r.rate)), 1);
  const slot = inner / rates.length;
  const bw = Math.min(40, Math.max(6, slot * 0.58));
  const zero = PAD.t + usable;
  const every = rates.length > 10 ? Math.ceil(rates.length / 7) : 1;
  return (
    <svg className="plot" viewBox={`0 0 ${w} ${H}`} role="img" aria-label={`Year on year inflation rate for ${series.country}`}>
      <line x1={PAD.l} x2={w - PAD.r} y1={zero} y2={zero} stroke="var(--line)" />
      {rates.map((r, i) => {
        const h = (Math.abs(r.rate) / hi) * usable;
        const cx = PAD.l + slot * i + (slot - bw) / 2;
        return (
          <g key={r.year} className={r.rate >= 6 ? "amber" : "neutral"}>
            <title>{`${r.year}: ${r.rate.toFixed(2)}%`}</title>
            <rect className="bar" x={cx} y={r.rate >= 0 ? zero - h : zero} width={bw} height={Math.max(1, h)} rx={2} />
          </g>
        );
      })}
      <g className="axis">
        {rates.map((r, i) =>
          i % every === 0 || i === rates.length - 1 ? (
            <text key={r.year} x={PAD.l + slot * i + slot / 2} y={H - 6} textAnchor="middle">
              {r.year}
            </text>
          ) : null,
        )}
      </g>
    </svg>
  );
}

function SourcePill({ series }: { series: CpiSeries }) {
  if (series.source === "live") return <span className="pill green">live · World Bank</span>;
  if (series.source === "cache") {
    const when = new Date(series.fetchedAt);
    const label = Number.isNaN(when.getTime()) ? "cached" : `cached ${when.toLocaleDateString()}`;
    return <span className="pill dim">{label}</span>;
  }
  return <span className="pill amber">offline · bundled snapshot</span>;
}

export function Inflation() {
  const [code, setCode] = useState<string>(() => {
    try {
      return localStorage.getItem("beacon.cpi.country") ?? "IND";
    } catch {
      return "IND";
    }
  });
  const [series, setSeries] = useState<CpiSeries | null>(null);
  const [loading, setLoading] = useState(true);
  const [amount, setAmount] = useState(25000);
  const [fromYear, setFromYear] = useState<number | null>(null);

  const country: Country = useMemo(() => COUNTRIES.find((c) => c.code === code) ?? COUNTRIES[0], [code]);

  const load = useCallback((target: string, signal: AbortSignal) => {
    setLoading(true);
    return loadCpi(target, signal)
      .then((s) => {
        if (signal.aborted) return;
        setSeries(s);
        // default the comparison to a decade back, clamped to the data we have
        setFromYear((prev) => {
          const years = s.points.map((p) => p.year);
          if (prev && years.includes(prev)) return prev;
          const newest = years[years.length - 1];
          return years.find((y) => y >= newest - 10) ?? years[0];
        });
      })
      .finally(() => {
        if (!signal.aborted) setLoading(false);
      });
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    void load(code, ctrl.signal);
    try {
      localStorage.setItem("beacon.cpi.country", code);
    } catch {
      /* storage blocked: the picker still works for this session */
    }
    return () => ctrl.abort();
  }, [code, load]);

  const newest = series ? latest(series) : null;
  const years = series?.points.map((p) => p.year) ?? [];
  const toYear = newest?.year ?? null;

  const rates = series ? yoySeries(series) : [];
  const lastRate = rates.length ? rates[rates.length - 1] : null;
  const power = series && fromYear && toYear ? purchasingPower(series, amount, fromYear, toYear) : null;
  const costNow = series && fromYear && toYear ? adjust(series, amount, fromYear, toYear) : null;
  const rate = series && fromYear && toYear ? cagr(series, fromYear, toYear) : null;
  const lost = power != null ? amount - power : null;
  const lostPct = power != null && amount > 0 ? ((amount - power) / amount) * 100 : null;

  return (
    <div className="stack analytics">
      <div className="page-h">
        <h1 className="display">
          What your money <em>still buys.</em>
        </h1>
        <p className="lede">
          Consumer price index from the World Bank, read live in your browser. Every figure below is computed from that series — pick
          a country, an amount and a year.
        </p>
      </div>

      <div className="row inflation-controls">
        <label className="faint small" htmlFor="cpi-country">
          country
        </label>
        <select id="cpi-country" className="input" value={code} onChange={(e) => setCode(e.target.value)}>
          {COUNTRIES.map((c) => (
            <option key={c.code} value={c.code}>
              {c.name}
            </option>
          ))}
        </select>

        <label className="faint small" htmlFor="cpi-amount">
          amount
        </label>
        <input
          id="cpi-amount"
          className="input"
          style={{ maxWidth: 140 }}
          type="number"
          min={0}
          step={100}
          value={amount}
          onChange={(e) => {
            const v = Number(e.target.value);
            setAmount(Number.isFinite(v) && v >= 0 ? v : 0);
          }}
        />

        <label className="faint small" htmlFor="cpi-year">
          fixed in
        </label>
        <select
          id="cpi-year"
          className="input"
          value={fromYear ?? ""}
          disabled={!years.length}
          onChange={(e) => setFromYear(Number(e.target.value))}
        >
          {years.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>

        {series ? <SourcePill series={series} /> : null}
      </div>

      {loading && !series ? (
        <div className="kpis">
          <div className="tile">
            <div className="n">–</div>
            <div className="l">reading the index…</div>
          </div>
        </div>
      ) : series && fromYear && toYear ? (
        <>
          <div className="kpis rise">
            <div className="tile">
              <div className="n">{formatMoney(power, country)}</div>
              <div className="l">
                what {formatMoney(amount, country)} from {fromYear} buys in {toYear}
              </div>
            </div>
            <div className="tile">
              <div className="n">{lostPct == null ? "–" : `${lostPct.toFixed(1)}%`}</div>
              <div className="l">purchasing power lost</div>
            </div>
            <div className="tile">
              <div className="n">{formatMoney(costNow, country)}</div>
              <div className="l">
                needed in {toYear} to match {fromYear}
              </div>
            </div>
            <div className="tile">
              <div className="n">{rate == null ? "–" : `${rate.toFixed(2)}%`}</div>
              <div className="l">average a year since {fromYear}</div>
            </div>
            <div className="tile">
              <div className="n">{lastRate ? `${lastRate.rate.toFixed(2)}%` : "–"}</div>
              <div className="l">{lastRate ? `inflation in ${lastRate.year}` : "latest rate"}</div>
            </div>
            <div className="tile moon">
              <div className="n">{newest ? newest.index.toFixed(1) : "–"}</div>
              <div className="l">index level ({newest?.year ?? "–"}, 2010 = 100)</div>
            </div>
          </div>

          <div className="banner">
            {lost != null && lostPct != null && lostPct > 0 ? (
              <>
                <Icon name="moon" /> {formatMoney(amount, country)} fixed in {fromYear} has about <b>{formatMoney(lost, country)}</b>{" "}
                less purchasing power in {toYear} — roughly <b>{lostPct.toFixed(1)}%</b>. To buy the same basket you would need{" "}
                {formatMoney(costNow, country)}.
              </>
            ) : (
              <>
                <Icon name="check" /> Prices in {country.name} are not higher in {toYear} than in {fromYear} on this index.
              </>
            )}
          </div>

          <div className="charts">
            <Frame title="Price level" meta={`${series.points[0].year}–${toYear} · 2010 = 100`}>
              {(w) => <IndexChart series={series} w={w} />}
            </Frame>
            <Frame title="Inflation, year on year" meta={rates.length ? `${rates.length} years` : undefined}>
              {(w) => <RateChart series={series} w={w} />}
            </Frame>
          </div>

          <details className="judge">
            <summary>How this is calculated</summary>
            <div className="stack small">
              <div>
                <b>Source.</b> World Bank indicator <span className="mono">FP.CPI.TOTL</span> for {series.country}, fetched in your
                browser. No key, no Beacon credential, nothing server-side.
              </div>
              <div>
                <b>Purchasing power.</b> amount × (index {fromYear} ÷ index {toYear}) ={" "}
                <span className="mono">
                  {amount} × ({pointFor(series, fromYear)?.index.toFixed(2)} ÷ {pointFor(series, toYear)?.index.toFixed(2)}) ={" "}
                  {power == null ? "–" : power.toFixed(2)}
                </span>
              </div>
              <div>
                <b>Average a year.</b> compound rate between the two index levels, not a mean of the yearly rates.
              </div>
              <div>
                <b>If the network fails.</b> the page falls back to a cached copy, then to a bundled snapshot of the same series, and
                the pill above says which one you are reading.
              </div>
            </div>
          </details>
        </>
      ) : (
        <div className="empty">
          <h3>No index available.</h3>
          <p>The World Bank has no consumer price series for {country.name} in this range. Pick another country.</p>
        </div>
      )}
    </div>
  );
}

export default Inflation;
