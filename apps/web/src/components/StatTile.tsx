import { useCountUp } from "../lib/motion";
import { Sparkline } from "./charts";
import { Icon, type IconName } from "./icons";

/** Animate the numeric part of a value like "17%" or "1,240"; leave other text as is. */
function AnimatedValue({ value }: { value: string }) {
  const match = /^([^\d-]*)(-?[\d,]+(?:\.\d+)?)(.*)$/.exec(value);
  const target = match ? Number((match[2] ?? "0").replace(/,/g, "")) : NaN;
  const decimals = match?.[2]?.includes(".") ? (match[2].split(".")[1]?.length ?? 0) : 0;
  const n = useCountUp(Number.isFinite(target) ? target : 0);
  if (!match || !Number.isFinite(target)) return <>{value}</>;
  const shown = n.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return (
    <>
      <span aria-hidden="true">
        {match[1]}
        {shown}
        {match[3]}
      </span>
      <span className="sr-only">{value}</span>
    </>
  );
}

export function StatTile({
  label,
  value,
  hint,
  delta,
  deltaGood,
  trend,
  icon = "spark",
}: {
  label: string;
  value: string;
  hint?: string | undefined;
  delta?: string | undefined;
  deltaGood?: boolean | undefined;
  trend?: readonly number[] | undefined;
  icon?: IconName;
}) {
  return (
    <div className="tf-card tf-lift relative min-w-48 flex-1 overflow-hidden rounded-xl border border-line bg-surface p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium tracking-wide text-muted uppercase">{label}</p>
        <span className="grid size-8 place-items-center rounded-lg bg-accent-soft text-accent">
          <Icon name={icon} />
        </span>
      </div>
      <p className="mt-2 text-3xl font-semibold tracking-tight tabular-nums">
        <AnimatedValue value={value} />
      </p>
      <div className="mt-1 flex items-end justify-between gap-2">
        <div className="text-xs">
          {delta && (
            <span
              className={`me-1.5 inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 font-semibold ${
                deltaGood === false ? "bg-danger-soft text-danger-text" : "bg-ok-soft text-ok-text"
              }`}
            >
              <Icon name={delta.startsWith("-") ? "arrowDown" : "arrowUp"} className="size-3" />
              {delta}
            </span>
          )}
          {hint && <span className="text-muted">{hint}</span>}
        </div>
        {trend && <Sparkline values={trend} className="h-8 w-24 shrink-0 text-accent" />}
      </div>
    </div>
  );
}
