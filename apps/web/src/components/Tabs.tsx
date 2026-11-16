import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";

/** Accessible tabs (WAI-ARIA tabs pattern): arrow keys, Home and End move between tabs. */
export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  label,
  labelOf,
  children,
  testId,
}: {
  tabs: readonly T[];
  value: T;
  onChange: (tab: T) => void;
  label: string;
  labelOf: (tab: T) => string;
  children: ReactNode;
  testId?: string;
}) {
  const base = useId();
  const refs = useRef<Partial<Record<T, HTMLButtonElement | null>>>({});
  const move = (i: number) => {
    const next = tabs[(i + tabs.length) % tabs.length];
    if (next === undefined) return;
    onChange(next);
    refs.current[next]?.focus();
  };
  const onKey = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    if (e.key === "ArrowRight") move(i + 1);
    else if (e.key === "ArrowLeft") move(i - 1);
    else if (e.key === "Home") move(0);
    else if (e.key === "End") move(tabs.length - 1);
    else return;
    e.preventDefault();
  };
  return (
    <div className="space-y-4" data-testid={testId}>
      <div
        role="tablist"
        aria-label={label}
        className="flex gap-1 rounded-xl border border-line bg-surface p-1"
      >
        {tabs.map((name, i) => (
          <button
            key={name}
            ref={(el) => {
              refs.current[name] = el;
            }}
            id={`${base}-tab-${name}`}
            type="button"
            role="tab"
            aria-selected={value === name}
            aria-controls={`${base}-panel-${name}`}
            tabIndex={value === name ? 0 : -1}
            onClick={() => onChange(name)}
            onKeyDown={(e) => onKey(e, i)}
            className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
              value === name ? "bg-accent text-accent-fg shadow-glow" : "text-fg hover:bg-surface-2"
            }`}
          >
            {labelOf(name)}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id={`${base}-panel-${value}`}
        aria-labelledby={`${base}-tab-${value}`}
        className="space-y-4"
      >
        {children}
      </div>
    </div>
  );
}
