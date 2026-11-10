/** A labelled usage bar (role="meter"); colour is never the only signal: the numbers are shown too. */
export function Meter({
  label,
  value,
  max,
  testId,
}: {
  label: string;
  value: number;
  max: number | null;
  testId?: string;
}) {
  const pct = max && max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  const tone = pct >= 100 ? "bg-danger" : pct >= 90 ? "bg-warn-text" : "bg-accent";
  return (
    <div data-testid={testId} className="space-y-1">
      <div className="flex justify-between gap-2 text-xs">
        <span>{label}</span>
        <span className="tabular-nums text-muted">
          {value.toLocaleString()} / {max === null ? "—" : max.toLocaleString()}
        </span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max ?? 0}
        aria-valuenow={value}
        className="h-2 overflow-hidden rounded-full bg-surface-2"
      >
        <div className={`h-full ${tone} transition-all`} style={{ width: `${String(pct)}%` }} />
      </div>
    </div>
  );
}
