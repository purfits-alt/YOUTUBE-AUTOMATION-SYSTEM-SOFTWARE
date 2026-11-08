import type { Overview, PageData, Row, Shell } from "../lib/api/client";
import { PAGES } from "../pages/registry";
import type { ColumnKey, PageDef } from "../pages/types";
import en from "../i18n/en.json";

/** Sample values per column (Phase 2 mock data — clearly fictional). */
const SAMPLES: Partial<Record<ColumnKey, readonly (string | number | boolean)[]>> = {
  time: ["09:12", "08:47", "Yesterday 22:05", "Yesterday 18:30"],
  actor: ["Owner", "A07 Scriptwriter", "A21 Copyright auditor", "System"],
  action: ["approved script", "drafted script v3", "passed audit", "backup completed"],
  entity: ["Why octopuses dream", "Ocean myths #4", "Render r-88", "Backup 2026-11-08"],
  name: ["Calm Science", "Urdu Kahaniyan", "Budget Kitchen", "Space Explained Simply"],
  language: ["en", "ur", "en", "es"],
  opportunity: [78, 71, 64, 59],
  inauthenticRisk: ["Low", "Low", "Medium", "High"],
  difficulty: ["Easy", "Medium", "Medium", "Hard"],
  confidence: ["High", "Medium", "Medium", "Low"],
  status: ["New", "Shortlisted", "Done", "Dismissed"],
  state: ["ACTIVE", "SCRIPTING", "RENDERING", "PAUSED"],
  mode: ["MANUAL", "SEMI", "MANUAL", "AUTO"],
  privateOnly: [true, true, false, true],
  tokenStatus: ["OK (6 days)", "Expires in 20 h", "OK", "NEEDS_REAUTH"],
  inProgress: [3, 1, 0, 2],
  lastUpload: ["2026-11-06", "2026-11-02", "—", "2026-10-28"],
  step: [1, 2, 3, 4],
  title: [
    "Why octopuses dream",
    "The quiet maths of bridges",
    "5 meals under 300 rupees",
    "How far is the edge?",
  ],
  criterion: ["Search interest", "Competition", "Evergreen share", "Production fit"],
  source: ["wikipedia.org", "trends (permitted)", "owner note", "openalex.org"],
  snippet: [
    "Interest steady for 24 months",
    "Few dedicated channels in Urdu",
    "70% evergreen topics",
    "Fits 8 GB RAM pipeline",
  ],
  fetchedAt: ["2026-11-07", "2026-11-07", "2026-11-06", "2026-11-05"],
  topic: ["Deep-sea sleep research", "Bridge failures explained", "Winter soups", "Dark matter maps"],
  strength: ["Rising", "Stable", "Rising", "Fading"],
  detected: ["2026-11-07", "2026-11-06", "2026-11-05", "2026-11-01"],
  expires: ["2026-11-21", "2026-11-20", "2026-11-19", "2026-11-15"],
  kind: ["Channel", "Video", "Channel", "Video"],
  query: ["@example-science", "youtu.be/example1", "@example-kitchen", "youtu.be/example2"],
  fetched: ["2026-11-07 10:02", "2026-11-06 21:40", "2026-11-05 08:15", "2026-11-04 17:30"],
  format: ["Long", "Short", "Long", "Short"],
  pillar: ["Ocean life", "Engineering", "Cooking", "Space"],
  similarity: ["12%", "8%", "31%", "64%"],
  calendarDate: ["2026-11-12", "2026-11-14", "—", "2026-11-19"],
  date: ["2026-11-10", "2026-11-12", "2026-11-14", "2026-11-17"],
  channel: ["Calm Science", "Urdu Kahaniyan", "Calm Science", "Budget Kitchen"],
  claim: [
    "Octopuses change colour while asleep",
    "Sleep stages were seen in 2023",
    "All octopuses dream",
    "REM exists in fish",
  ],
  verdict: ["Supported", "Supported", "Unsupported", "Needs source"],
  sources: [2, 3, 0, 1],
  explanation: [
    "Two peer-reviewed studies",
    "Nature 2023",
    "Over-generalisation — reworded",
    "Owner to add source",
  ],
  scene: [1, 2, 3, 4],
  narration: [
    "Every night, in the dark…",
    "Scientists filmed…",
    "But is it dreaming?",
    "Here is what we know.",
  ],
  visual: ["Kinetic title", "Owner B-roll", "CC0 photo", "Chart: sleep cycles"],
  duration: ["0:12", "0:25", "0:18", "0:31"],
  track: ["Video", "Narration", "Music", "Captions"],
  clip: ["Scene 1", "Take 2", "Calm piano (CC0)", "en.vtt"],
  start: ["0:00", "0:12", "0:37", "0:55"],
  asset: ["octopus-night.jpg", "chart-sleep.svg", "owner-clip-03.mp4", "title-card.png"],
  origin: ["CC0", "Procedural", "Owner", "Procedural"],
  rightsStatus: ["Cleared", "Cleared", "Cleared", "Missing"],
  text: ["Every night, in the dark…", "Scientists filmed…", "But is it dreaming?", "Here is what we know."],
  voiceSource: ["Own voice", "Own voice", "Own-voice clone", "Kokoro TTS"],
  take: [2, 1, 1, 1],
  variant: ["A", "B", "C", "D"],
  checks: ["Passed", "Passed", "Text too small", "Passed"],
  chapterTitle: ["Intro", "What sleep looks like", "Dreaming?", "What we know"],
  method: ["Script alignment", "faster-whisper", "Manual", "Script alignment"],
  reviewed: [true, false, false, true],
  syncStatus: ["In sync", "Drift 0.4 s", "In sync", "In sync"],
  project: ["Why octopuses dream", "Ocean myths #4", "Bridge maths", "Winter soups"],
  progress: ["100%", "62%", "15%", "0%"],
  eta: ["—", "6 min", "38 min", "Night window"],
  started: ["08:01", "09:10", "09:31", "—"],
  qc: ["Passed", "—", "—", "—"],
  privacy: ["private", "private", "private", "private"],
  publishAt: ["2026-11-12 18:00", "2026-11-14 17:30", "2026-11-19 18:00", "—"],
  videoId: ["(test) abc123", "—", "—", "—"],
  type: ["Script", "Upload", "Thumbnail", "Mode change"],
  subject: [
    "Why octopuses dream — script v3",
    "Ocean myths #4 — private upload",
    "Bridge maths — variant B",
    "Calm Science → SEMI",
  ],
  requested: ["09:12", "08:40", "Yesterday", "2 days ago"],
  age: ["1 h", "2 h", "18 h", "2 d"],
  published: ["2026-11-06", "2026-11-02", "2026-10-28", "2026-10-21"],
  views: [1240, 860, 2310, 540],
  engagedViews: [980, 610, 1880, 400],
  watchTime: [41.2, 22.5, 96.0, 12.8],
  avd: ["3:58", "2:41", "4:12", "1:55"],
  ctr: ["5.1%", "4.2%", "6.3%", "3.0%"],
  suggestion: ["Hook in first 10 s", "Upload at 18:00 PKT", "Shorter intro", "More chapters"],
  evidence: [
    "AVD drop at 0:14 on 3 videos",
    "Audience active 17–20 PKT",
    "Intro 42 s vs median 18 s",
    "Long videos without chapters",
  ],
  preview: ["🖼", "🎞", "🎵", "🖼"],
  licence: ["CC0", "Own", "CC-BY 4.0", "—"],
  size: ["1.2 MB", "84 MB", "3.4 MB", "0.4 MB"],
  created: ["2026-11-07", "2026-11-06", "2026-11-05", "2026-11-04"],
  provider: ["Gemini (free)", "Groq (free)", "YouTube Data API", "Ollama (local)"],
  capability: ["LLM", "LLM", "YouTube", "LLM"],
  tier: ["Free", "Free", "Free", "Local"],
  used: ["412 req", "88 req", "1,650 units", "—"],
  limit: ["1,500 req/day", "1,000 req/day", "10,000 units/day", "—"],
  resets: ["05:00", "05:00", "12:00", "—"],
  notification: [
    "Script ready for approval",
    "Upload finished (private)",
    "Token expires in 20 h",
    "Backup completed",
  ],
  severity: ["Info", "Info", "Warning", "Info"],
  received: ["09:12", "08:41", "07:00", "03:04"],
  read: [false, false, true, true],
  agent: ["A07 Scriptwriter", "A09 Fact-checker", "A14 Thumbnail", "A21 Copyright auditor"],
  tokens: [5120, 3870, 0, 1290],
  quality: [86, 91, 78, 95],
  auditType: ["Copyright", "Policy", "Quality", "Originality"],
  result: ["Pass", "Pass", "Warn", "Pass"],
  score: [96, 92, 74, 88],
  critical: [0, 0, 0, 0],
  details: ["—", "ip 127.0.0.1", "v3", "—"],
  setting: ["Timezone", "Night render window", "Backup time", "Disk budget"],
  value: ["Asia/Karachi", "01:00–07:00", "03:00 PKT", "60 GB"],
  updated: ["2026-11-08", "2026-11-08", "2026-11-08", "2026-11-08"],
  multiple: ["6.2×", "3.4×", "2.1×", "2.0×"],
  variation: ["Part 2 / sequel", "Short from long", "New angle", "Updated version"],
  angle: ["What happened next", "The 45-second version", "Seen by a marine biologist", "New 2026 research"],
  reason: [
    "Pattern of your 6.2× outlier",
    "Rising: deep-sea research",
    "Your winner, new angle",
    "Evergreen in your pillar",
  ],
};

function rowsFor(page: PageDef, count = 4): Row[] {
  return Array.from({ length: count }, (_, i) => {
    const row: Row = { id: `${page.id}-${String(i + 1)}` };
    for (const col of page.columns) {
      const values = SAMPLES[col];
      row[col] = values ? (values[i % values.length] ?? null) : "—";
    }
    return row;
  });
}

const PROJECT = {
  id: "p-101",
  title: "Why octopuses dream",
  channel: "Calm Science",
  format: "Long (8–10 min)",
  state: "SCRIPTING",
  states: ["IDEA", "RESEARCH", "SCRIPTING", "STORYBOARD", "ASSEMBLY", "RENDER", "AUDIT", "UPLOAD"],
  guards: ["Fact-check has 1 unsupported claim", "Owner value-add field is empty"],
};

export function pageData(page: PageDef, empty: boolean): PageData {
  const pageText = en.pages[page.id];
  const stats = empty
    ? []
    : page.id === "trending"
      ? [
          {
            key: "outliers",
            label: "Outliers this month",
            value: "4",
            delta: "+2",
            delta_good: true,
            trend: [0, 1, 1, 2, 2, 3, 4],
          },
          { key: "best", label: "Best multiple", value: "6.2×", hint: "Why octopuses dream" },
          {
            key: "median",
            label: "Your median views (7 days)",
            value: "200",
            trend: [150, 160, 170, 180, 185, 195, 200],
          },
        ]
      : [
          {
            key: "total",
            label: "Items",
            value: "4",
            delta: "+2",
            delta_good: true,
            trend: [1, 2, 2, 3, 2, 3, 4],
          },
          {
            key: "attention",
            label: "Need attention",
            value: "1",
            hint: pageText.title,
            trend: [3, 2, 2, 1, 2, 1, 1],
          },
          {
            key: "done",
            label: "Done this week",
            value: "7",
            delta: "+40%",
            delta_good: true,
            trend: [2, 3, 3, 4, 5, 6, 7],
          },
        ];
  return {
    stats,
    rows: empty ? [] : rowsFor(page),
    next_cursor: null,
    ...(page.projectScoped ? { project: PROJECT } : {}),
  };
}

/** Page 32 › Replicate / Milk: own winners and their variation ideas (US-4.6). */
export function replicateData(empty: boolean): PageData {
  if (empty) return { stats: [], rows: [], next_cursor: null };
  const columns = ["title", "variation", "angle", "similarity", "state"] as const;
  const titles = [
    "Why octopuses dream",
    "Why octopuses dream",
    "The quiet maths of bridges",
    "Why octopuses dream",
  ];
  const similarity = ["38%", "52%", "41%", "61%"];
  const states = ["SUGGESTED", "SHORTLISTED", "SUGGESTED", "APPROVED"];
  return {
    stats: [
      { key: "winners", label: "Winners to replicate", value: "2", hint: "≥ 2× your median" },
      { key: "variations", label: "Variation ideas", value: "4", delta: "+3", delta_good: true },
    ],
    rows: titles.map((title, i) => {
      const row: Row = { id: `rep-${String(i + 1)}`, title };
      for (const col of columns.slice(1)) {
        const sample = col === "similarity" ? similarity : col === "state" ? states : SAMPLES[col];
        row[col] = sample?.[i % sample.length] ?? "—";
      }
      return row;
    }),
    next_cursor: null,
  };
}

export function overviewData(empty: boolean): Overview {
  if (empty)
    return { kpis: [], pipeline: [], approvals: [], alerts: [], schedule: [], activity: [], views_14d: [] };
  const overview = PAGES[0];
  if (!overview) throw new Error("registry empty");
  return {
    kpis: [
      {
        key: "channels",
        label: en.overview.kpiChannels,
        value: "2",
        delta: "+1",
        delta_good: true,
        trend: [1, 1, 1, 1, 2, 2, 2],
      },
      {
        key: "projects",
        label: en.overview.kpiProjects,
        value: "5",
        delta: "+2",
        delta_good: true,
        trend: [2, 3, 3, 4, 3, 4, 5],
      },
      {
        key: "approvals",
        label: en.overview.kpiApprovals,
        value: "3",
        hint: "oldest 2 days",
        trend: [5, 4, 4, 2, 3, 2, 3],
      },
      {
        key: "quota",
        label: en.overview.kpiQuota,
        value: "17%",
        hint: "resets 12:00 PKT",
        trend: [8, 12, 30, 22, 9, 14, 17],
      },
      {
        key: "usage",
        label: en.overview.kpiUsage,
        value: "41%",
        hint: "Gemini free tier",
        delta: "+6%",
        delta_good: false,
        trend: [20, 28, 25, 33, 30, 35, 41],
      },
    ],
    pipeline: [
      { state: "IDEA", count: 12 },
      { state: "SCRIPTING", count: 2 },
      { state: "STORYBOARD", count: 1 },
      { state: "RENDER", count: 1 },
      { state: "AUDIT", count: 0 },
      { state: "UPLOAD", count: 1 },
    ],
    approvals: [
      { id: "ap-1", subject: "Why octopuses dream — script v3", type: "Script", age: "1 h" },
      { id: "ap-2", subject: "Ocean myths #4 — private upload", type: "Upload", age: "2 h" },
      { id: "ap-3", subject: "Calm Science → SEMI mode", type: "Mode change", age: "2 d" },
    ],
    alerts: [
      { id: "al-1", severity: "Warning", message: "Google sign-in for Urdu Kahaniyan expires in 20 h" },
      { id: "al-2", severity: "Info", message: "Gemini free tier at 41% of today's limit" },
    ],
    schedule: [
      { id: "sc-1", date: "2026-11-12 18:00", title: "Why octopuses dream", channel: "Calm Science" },
      { id: "sc-2", date: "2026-11-14 17:30", title: "Ocean myths #4", channel: "Calm Science" },
    ],
    activity: rowsFor(overview, 6),
    views_14d: [420, 510, 480, 620, 700, 660, 810, 760, 905, 990, 940, 1120, 1080, 1240].map((views, i) => ({
      date: new Date(Date.UTC(2026, 9, 26 + i)).toISOString().slice(0, 10),
      views,
    })),
  };
}

export function shellData(): Shell {
  return {
    channels: [
      { id: "ch-1", name: "Calm Science", mode: "MANUAL", private_only: true, token_expiring: false },
      { id: "ch-2", name: "Urdu Kahaniyan", mode: "MANUAL", private_only: true, token_expiring: true },
    ],
    quota: { youtube_default_pct: 17, free_tier_peak_pct: 41 },
    unread_notifications: 2,
  };
}
