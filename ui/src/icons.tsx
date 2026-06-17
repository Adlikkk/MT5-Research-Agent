// Tiny dependency-free icon set. Each icon is a 20x20 stroke glyph that inherits
// the current text color, so it themes automatically with the design tokens.

export type IconName =
  | "agent"
  | "dashboard"
  | "setup"
  | "research"
  | "params"
  | "optimizer"
  | "ealab"
  | "runs"
  | "leaderboard"
  | "reports"
  | "settings"
  | "chevron-left"
  | "chevron-right"
  | "panel-right"
  | "play"
  | "x"
  | "refresh"
  | "logs";

const PATHS: Record<IconName, JSX.Element> = {
  agent: (
    <>
      <path d="M10 2.5l1.6 4 4 1.5-4 1.5L10 13.5 8.4 9.5l-4-1.5 4-1.5z" />
      <path d="M15.5 12.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" />
    </>
  ),
  dashboard: (
    <>
      <rect x="2.5" y="2.5" width="6" height="6" rx="1" />
      <rect x="11.5" y="2.5" width="6" height="4" rx="1" />
      <rect x="2.5" y="11.5" width="6" height="6" rx="1" />
      <rect x="11.5" y="9.5" width="6" height="8" rx="1" />
    </>
  ),
  setup: (
    <>
      <path d="M3 6h9M15 6h2M3 14h2M8 14h9" />
      <circle cx="13.5" cy="6" r="2" />
      <circle cx="6.5" cy="14" r="2" />
    </>
  ),
  research: (
    <>
      <path d="M8 2.5h4M8.5 2.5v5L4 15a1.5 1.5 0 001.3 2.5h9.4A1.5 1.5 0 0016 15l-4.5-7.5v-5" />
      <path d="M6.5 12h7" />
    </>
  ),
  params: (
    <>
      <path d="M5 3v6M5 13v4M10 3v3M10 10v7M15 3v9M15 16v1" />
      <circle cx="5" cy="11" r="1.7" />
      <circle cx="10" cy="8" r="1.7" />
      <circle cx="15" cy="14" r="1.7" />
    </>
  ),
  optimizer: (
    <>
      <circle cx="10" cy="10" r="7" />
      <circle cx="10" cy="10" r="3.5" />
      <circle cx="10" cy="10" r="0.6" fill="currentColor" />
    </>
  ),
  ealab: (
    <>
      <path d="M7.5 2.5v4.5L4 14a2 2 0 001.8 3h8.4A2 2 0 0016 14l-3.5-7V2.5" />
      <path d="M6.5 2.5h7" />
      <path d="M5.5 12.5h9" />
    </>
  ),
  runs: (
    <>
      <path d="M7 4.5h10M7 10h10M7 15.5h10" />
      <circle cx="3.5" cy="4.5" r="1.2" fill="currentColor" stroke="none" />
      <circle cx="3.5" cy="10" r="1.2" fill="currentColor" stroke="none" />
      <circle cx="3.5" cy="15.5" r="1.2" fill="currentColor" stroke="none" />
    </>
  ),
  leaderboard: (
    <>
      <path d="M6 4h8v3a4 4 0 01-8 0V4z" />
      <path d="M6 5H4v1.5A2 2 0 006 8.5M14 5h2v1.5a2 2 0 01-2 2" />
      <path d="M10 11v3M7.5 17h5M8.5 17l.5-3h2l.5 3" />
    </>
  ),
  reports: (
    <>
      <path d="M5 2.5h6l4 4V17a.5.5 0 01-.5.5h-9A.5.5 0 015 17V3a.5.5 0 01.5-.5z" />
      <path d="M11 2.5V6.5h4" />
      <path d="M7.5 10.5h5M7.5 13.5h5" />
    </>
  ),
  settings: (
    <>
      <circle cx="10" cy="10" r="2.5" />
      <path d="M10 2.5v2.2M10 15.3v2.2M3.4 6.2l1.9 1.1M14.7 12.7l1.9 1.1M3.4 13.8l1.9-1.1M14.7 7.3l1.9-1.1" />
    </>
  ),
  "chevron-left": <path d="M12.5 5l-5 5 5 5" />,
  "chevron-right": <path d="M7.5 5l5 5-5 5" />,
  "panel-right": (
    <>
      <rect x="2.5" y="3.5" width="15" height="13" rx="1.5" />
      <path d="M12.5 3.5v13" />
    </>
  ),
  play: <path d="M6 4l9 6-9 6V4z" />,
  x: <path d="M5 5l10 10M15 5L5 15" />,
  refresh: (
    <>
      <path d="M16 6a7 7 0 10.8 6" />
      <path d="M16 2.5V6.5h-4" />
    </>
  ),
  logs: (
    <>
      <rect x="2.5" y="3.5" width="15" height="13" rx="1.5" />
      <path d="M5.5 7h9M5.5 10h9M5.5 13h6" />
    </>
  ),
};

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {PATHS[name]}
    </svg>
  );
}
