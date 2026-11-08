import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-accent-fg shadow-glow hover:brightness-110",
  secondary: "border border-line bg-surface text-fg hover:bg-surface-2",
  danger: "bg-danger text-white hover:opacity-90 dark:text-black",
  ghost: "text-fg hover:bg-surface-2",
};

export function Button({
  variant = "secondary",
  className = "",
  type = "button",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type={type}
      className={`inline-flex min-h-9 items-center justify-center gap-1.5 rounded-lg px-3.5 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${VARIANTS[variant]} ${className}`}
      {...rest}
    />
  );
}

export type Tone = "ok" | "warn" | "danger" | "info" | "neutral";

const TONES: Record<Tone, { cls: string; icon: string }> = {
  ok: { cls: "bg-ok-soft text-ok-text", icon: "✓" },
  warn: { cls: "bg-warn-soft text-warn-text", icon: "!" },
  danger: { cls: "bg-danger-soft text-danger-text", icon: "✕" },
  info: { cls: "bg-info-soft text-info-text", icon: "i" },
  neutral: { cls: "bg-surface-2 text-fg", icon: "•" },
};

/** Colour is never the only signal: every badge has an icon and text (WCAG). */
export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  const t = TONES[tone];
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${t.cls}`}>
      <span aria-hidden="true">{t.icon}</span>
      {children}
    </span>
  );
}

const OK = /^(ok|pass|passed|cleared|supported|done|active|in sync|low|easy|high confidence|yes)\b/i;
const WARN = /^(warn|warning|medium|expires|needs source|drift|shortlisted|rising|paused|new)/i;
const DANGER = /^(fail|failed|high|hard|missing|unsupported|needs_reauth|critical|error|dismissed)/i;

/** Columns where "High" is good news (confidence, quality) rather than a risk. */
const HIGH_IS_GOOD = new Set(["confidence"]);

/** Pick a badge tone from a status-like value; `column` disambiguates High/Low. */
export function toneFor(value: string, column?: string): Tone {
  if (column && HIGH_IS_GOOD.has(column)) {
    if (/^high/i.test(value)) return "ok";
    if (/^low/i.test(value)) return "danger";
  }
  if (DANGER.test(value)) return "danger";
  if (WARN.test(value)) return "warn";
  if (OK.test(value)) return "ok";
  return "neutral";
}

export function Card({
  title,
  children,
  actions,
  className = "",
}: {
  title?: string;
  children: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`tf-card tf-rise rounded-xl border border-line bg-surface p-5 ${className}`}>
      {(title ?? actions) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="text-base font-semibold">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden="true" className={`animate-pulse rounded bg-surface-2 ${className}`} />;
}
