import { useId } from "react";

function scale(values: readonly number[], w: number, h: number, pad = 2): [number, number][] {
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const step = values.length > 1 ? (w - pad * 2) / (values.length - 1) : 0;
  return values.map((v, i) => [pad + i * step, h - pad - ((v - min) / span) * (h - pad * 2)]);
}

function linePath(points: [number, number][]): string {
  return points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
}

/** Tiny trend line for KPI tiles (decorative; the number next to it carries the meaning). */
export function Sparkline({
  values,
  className = "h-8 w-24",
}: {
  values: readonly number[];
  className?: string;
}) {
  const id = useId();
  if (values.length < 2) return null;
  const pts = scale(values, 96, 32);
  const d = linePath(pts);
  const last = pts[pts.length - 1] ?? [0, 0];
  return (
    <svg viewBox="0 0 96 32" className={className} aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="currentColor" stopOpacity="0.28" />
          <stop offset="1" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${d} L${last[0].toFixed(1)},32 L2,32 Z`} fill={`url(#${id})`} />
      <path
        d={d}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        className="tf-draw"
        pathLength={1}
      />
      <circle cx={last[0]} cy={last[1]} r="2.5" fill="currentColor" />
    </svg>
  );
}

/** Area chart with axis labels and an accessible data table fallback. */
export function AreaChart({
  data,
  label,
}: {
  data: readonly { date: string; views: number }[];
  label: string;
}) {
  const id = useId();
  const W = 640;
  const H = 200;
  const values = data.map((d) => d.views);
  const max = Math.max(...values, 1);
  const pts = scale(values, W, H, 8);
  const d = linePath(pts);
  const first = pts[0] ?? [0, 0];
  const last = pts[pts.length - 1] ?? [0, 0];
  const gridLines = [0.25, 0.5, 0.75];
  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${String(W)} ${String(H)}`}
        className="h-52 w-full text-accent"
        role="img"
        aria-labelledby={`${id}-t`}
      >
        <title id={`${id}-t`}>{label}</title>
        <defs>
          <linearGradient id={`${id}-fill`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="currentColor" stopOpacity="0.35" />
            <stop offset="1" stopColor="currentColor" stopOpacity="0" />
          </linearGradient>
          <linearGradient id={`${id}-stroke`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#ff5f6d" />
            <stop offset="1" stopColor="currentColor" />
          </linearGradient>
        </defs>
        {gridLines.map((g) => (
          <line key={g} x1="0" x2={W} y1={H * g} y2={H * g} stroke="var(--tf-border)" strokeDasharray="4 6" />
        ))}
        <path
          d={`${d} L${last[0].toFixed(1)},${String(H)} L${first[0].toFixed(1)},${String(H)} Z`}
          fill={`url(#${id}-fill)`}
          className="tf-fade"
        />
        <path
          d={d}
          fill="none"
          stroke={`url(#${id}-stroke)`}
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="tf-draw"
          pathLength={1}
        />
        {pts.map(([x, y], i) => (
          <circle
            key={data[i]?.date ?? i}
            cx={x}
            cy={y}
            r={i === pts.length - 1 ? 5 : 2.5}
            fill="currentColor"
            className="tf-fade"
          />
        ))}
      </svg>
      <figcaption className="mt-1 flex justify-between text-xs text-muted">
        <span>{data[0]?.date}</span>
        <span>max {max.toLocaleString("en-US")}</span>
        <span>{data[data.length - 1]?.date}</span>
      </figcaption>
      <table className="sr-only">
        <caption>{label}</caption>
        <tbody>
          {data.map((p) => (
            <tr key={p.date}>
              <th scope="row">{p.date}</th>
              <td>{p.views}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

/** Radial gauge (0–100 %) used for quota and free-tier usage. */
export function Ring({ value, label, sublabel }: { value: number; label: string; sublabel: string }) {
  const r = 34;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, value));
  const tone = pct >= 80 ? "text-danger" : pct >= 60 ? "text-warn-text" : "text-accent";
  return (
    <div className="flex items-center gap-3">
      <svg
        viewBox="0 0 80 80"
        className={`size-20 -rotate-90 ${tone}`}
        role="img"
        aria-label={`${label}: ${String(pct)}%`}
      >
        <circle cx="40" cy="40" r={r} fill="none" stroke="var(--tf-surface-2)" strokeWidth="8" />
        <circle
          cx="40"
          cy="40"
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={`${String((pct / 100) * c)} ${String(c)}`}
          className="tf-ring"
        />
      </svg>
      <div>
        <p className="text-2xl font-semibold tabular-nums">{pct}%</p>
        <p className="text-sm font-medium">{label}</p>
        <p className="text-xs text-muted">{sublabel}</p>
      </div>
    </div>
  );
}
