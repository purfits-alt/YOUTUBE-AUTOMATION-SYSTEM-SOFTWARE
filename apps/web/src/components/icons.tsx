import type { SVGProps } from "react";

/** Small inline icon set (stroke icons, 24×24, currentColor). Decorative: always aria-hidden. */
const PATHS = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  discover: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zm10 17-4.35-4.35",
  channels: "M3 7h18v12H3zM8 3l4 4 4-4",
  create: "M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z",
  publish: "M12 16V4m0 0-5 5m5-5 5 5M4 20h16",
  grow: "M3 17l6-6 4 4 8-8m0 0h-6m6 0v6",
  library: "M4 4h6v16H4zM14 4l6 1.5-3.5 14.5-6-1.5z",
  control: "M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0M14 4v4M8 10v4M16 16v4",
  search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zm10 17-4.35-4.35",
  bell: "M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9m4.3 13a2 2 0 0 0 3.4 0",
  stop: "M7 7h10v10H7z",
  sun: "M12 4V2m0 20v-2m8-8h2M2 12h2m13.66-5.66 1.41-1.41M4.93 19.07l1.41-1.41m0-11.32L4.93 4.93m14.14 14.14-1.41-1.41M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10z",
  check: "M5 12.5 10 17 19 7",
  alert: "M12 9v4m0 4h.01M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  clock: "M12 7v5l3 2m6-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0z",
  film: "M4 4h16v16H4zM8 4v16M16 4v16M4 9h4M16 9h4M4 15h4M16 15h4",
  users:
    "M16 19v-1a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v1m18 0v-1a4 4 0 0 0-3-3.87M15 3.13a4 4 0 0 1 0 7.75M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z",
  gauge: "M12 14l4-4M3.5 18a9 9 0 1 1 17 0",
  spark: "M12 3v4m0 10v4M3 12h4m10 0h4M5.6 5.6l2.8 2.8m7.2 7.2 2.8 2.8m0-12.8-2.8 2.8M8.4 15.6l-2.8 2.8",
  arrowUp: "M12 19V5m0 0-6 6m6-6 6 6",
  arrowDown: "M12 5v14m0 0-6-6m6 6 6-6",
  menu: "M4 6h16M4 12h16M4 18h16",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, className = "size-4", ...rest }: { name: IconName } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
      {...rest}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}

/** TubeForge logo mark: a play triangle inside an anvil-like rounded square. */
export function LogoMark({ className = "size-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" focusable="false" className={className}>
      <defs>
        <linearGradient id="tf-logo" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ff5f6d" />
          <stop offset="1" stopColor="#7c5cff" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="30" height="30" rx="9" fill="url(#tf-logo)" />
      <path d="M13 10.5v11l9-5.5z" fill="#fff" />
    </svg>
  );
}
