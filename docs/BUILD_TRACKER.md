# TubeForge build tracker

This is our checklist. We build **phase by phase, in the roadmap's order** (`IMPLEMENTATION_ROADMAP.md`).
Each phase lists its steps and **your part** for that module.

**How we work (owner rule, 2026-11-15):**
- We work on one module at a time, together.
- I raise **your part** only when that module's turn comes. I don't ask for later parts early.
- A module is finished only when **both** parts are done: my build (tested, merged) **and** your part.
- **Gaps** from earlier phases are closed before the next new module starts.
- I update this file whenever a status changes, in the same PR as the work.

**Status:**

| Mark | Meaning |
|---|---|
| ✅ | done |
| 🟡 | in progress |
| ⬜ | not started |
| ⛔ | excluded: paid, or it would break a provider rule (with the reason) |

## Where we are now

| | |
|---|---|
| **Current module** | **Phase 8: storyboards, visuals, voice, channel art and stock.** Phase 7 approved by you on 2026-11-27. |
| Your channel | **Open Node AI**, handle **@OpenNodeAIHQ**, https://www.youtube.com/@OpenNodeAIHQ (created 2026-11-15; name, description and handle set from the setup kit) |
| Created in TubeForge | yes, from the approved blueprint, as a test channel (private uploads only) |
| Connected | ✅ 2026-11-15: Google sign-in done; private test upload visible (private) in YouTube Studio |

## Gaps from earlier phases (closed before new work)

| # | Gap | From | My part | Your part | Status |
|---|---|---|---|---|---|
| G1 | Real YouTube connection and one private test upload for Open Node AI | Phase 4 | ✅ built (onboarding, OAuth, setup kit, privacy pages) | Onboarding steps 3–10: phone verification; Google Cloud project (no billing); YouTube Data API v3; consent screen (Testing, yourself as test user); Desktop OAuth client pasted into TubeForge; privacy page on `tubeforge.semrs.com/app-privacy.html`; **Connect with Google**; **private test upload**. Then tell me the result. | ✅ 2026-11-15 |
| G2 | Confirm Wikimedia's terms on the Research sources panel | Phase 6 | ✅ built | Open **Terms**, read them, press **I checked the terms** | ✅ 2026-11-15 |
| G3 | Check the similarity model's scores | Phase 7 step A | ✅ built (`fetch-models`, `similarity-check`) | Run `uv run tubeforge-admin similarity-check` once after `setup` and send me the output | ✅ 2026-11-15: model2vec installed; limits calibrated (ADR-0029) |
| G4 | Duplicate-upload guard after an expired upload session | Phase 4 → moved | deferred to Phase 12 (task 1, "duplicate guard via uploads playlist") | none | ⬜ (Phase 12) |
| G5 | Friendlier password prompt in `setup` | Phase 1 | deferred to the Phase 15 installer | none | ⬜ (Phase 15) |
| G6 | Add a contact to research requests (Wikimedia asks for one) | Phase 6 | ✅ built (`research_contact`) | Optional: add `research_contact = "..."` to `config\tubeforge.toml` | ⬜ optional |

## Phase 1 — Foundation & repository ✅
| Step | Status |
|---|---|
| Repo layout, Python/uv, FastAPI health, config, logging | ✅ |
| Web app served by the API | ✅ |
| PostgreSQL, migrations, job queue (Windows tested) | ✅ |
| Workers (light and heavy) | ✅ |
| Lint, types, tests, security and licence tooling | ✅ |
| CI on Linux and Windows (path with spaces) | ✅ |
| `tubeforge.ps1` (setup, start, stop, status, doctor) | ✅ |
| Your part: install PostgreSQL 16, free space on D: | ✅ |

## Phase 2 — Frontend shell ✅
| Step | Status |
|---|---|
| App shell, themes, i18n, global elements | ✅ |
| All routes (now 32) with sample data and states | ✅ |
| Shared components, API client pipeline | ✅ |
| Browser tests (routes × states, accessibility, visual) | ✅ |
| Your part: none | — |

## Phase 3 — Backend, database & auth ✅
| Step | Status |
|---|---|
| All tables and migrations; repository layer | ✅ |
| Sign-in, 2FA, sessions, CSRF, lockout, re-auth | ✅ |
| Permissions on every route; audit hash chain; security events | ✅ |
| Encrypted secrets (Windows Credential Manager) | ✅ |
| Emergency Stop, kill switches, settings | ✅ |
| Errors, idempotency, pagination, live updates | ✅ |
| Your part: none (2FA is recommended: Audit & Security Center › enable 2FA) | — |

## Phase 4 — Channel onboarding, OAuth & quota ledger ✅
| Step | Status |
|---|---|
| 10-step onboarding with help links | ✅ |
| Privacy and terms pages (now on `tubeforge.semrs.com`) | ✅ |
| OAuth (PKCE), identity check, token health, revoke | ✅ |
| SafeYouTubeClient, quota ledger | ✅ |
| Private test upload (test channel only) | ✅ |
| Retention jobs; notifications | ✅ |
| Channel Manager and onboarding pages | ✅ |
| **Added:** YouTube setup kit (name, @handles, description, brand briefs) | ✅ |
| Your part: Google Cloud project, OAuth client, channel, privacy page details, connect, test upload | ✅ 2026-11-15 (G1) |

## Phase 5 — Orchestrator & agent infrastructure ✅
| Step | Status |
|---|---|
| Orchestrator, guards, approvals, reconciler, Emergency Stop | ✅ |
| State machines as code | ✅ |
| AI Provider Gateway (limits, cache, validation, retries, 300 s waits, second Gemini model) | ✅ |
| Gemini adapter | ✅ |
| Ollama adapter (local fallback) | ✅ (optional to install) |
| Groq adapter | ✅ built · ⛔ **not used**: Groq asked you for payment, so its kill switch stays on |
| Agent framework, prompts, run logs | ✅ |
| Paid activation (two steps), budgets, paid-sign detector | ✅ (paid providers stay off) |
| Agent Control Center, Cost & Usage pages | ✅ |
| Your part: Gemini key from a no-billing project | ✅ |
| Your part: Groq free account | ⛔ (payment asked) |

## Phase 6 — Niche discovery & trends ✅
| Step | Status |
|---|---|
| Research fetcher (allowlist, safety), source registry, Wikipedia, RSS | ✅ |
| Google Trends adapter | ⛔ off: no approved free API; scraping is forbidden (ADR-0015) |
| Discovery agents, scoring, weight profiles ("Evergreen ad revenue" default, remarks, Recommended) | ✅ |
| Competitor lookup (single item, 30-day cache) | ✅ |
| Branding Studio, approve → channel; blueprint and niche list pages | ✅ |
| **Added:** agent job descriptions (`agents/`), product site and demo on `tubeforge.semrs.com` | ✅ |
| Your part: none (Wikimedia terms: see G2) | — |

## Phase 7 — Ideas, research, fact-check & scripts ✅ (approved 2026-11-27)
| Step | Status |
|---|---|
| A — Content core: similarity (ADR-0029), script craft checks, value-add score, script versions | ✅ |
| B — Agents A08 ideas, A09 research, A10 fact-check, A11 scripts; pipelines; golden, injection and craft tests | ✅ |
| C — API: ideas, calendar, projects, research, claims, script versions and diff, replicate | ✅ |
| D — Pages: Idea Generator, Content Calendar, Script Studio, Channel Trending tabs; browser tests; phase report | ✅ |
| Owner request (2026-11-16): **Build** tab beside Run discovery (your own channel name or TubeForge's names, or a channel you already have) | ✅ |
| Owner request (2026-11-16): channels onboarded outside discovery go through the same ideas, calendar, Script Studio and Trending pages (blueprint can be attached to them) | ✅ |
| Owner request (2026-11-18): **Pipeline** page: state board (per station: inbox from the previous station, in progress, complete, forwarded to the next), live % and stage of every job, what comes next, stopped or stalled jobs shown with the reason; live bar in Script Studio; **Write again** for the script (ADR-0031) | ✅ |
| Your part, now: run the Phase 7 demo (`PROJECT_PROGRESS.md`, Phase 7 report, item 11) and rate 10 scripts for "sounds human" (≥ 4/5), then reply "approved" | ✅ "APPROVED", 2026-11-27 |

## Phase 8 — Storyboards, visuals, voice & stock 🟡 (started 2026-11-27)
| Step | Status |
|---|---|
| Storyboard, visual plan, 16 procedural templates, renderer | ⬜ |
| Asset library, rights forms, manual licensed import | ⬜ |
| Pexels/Pixabay free adapters (off by default) | ⬜ |
| Paid stock | ⛔ interface only, disabled (paid) |
| Voice: recorder, Kokoro and Piper TTS with licence registry | ⬜ |
| Own-voice clone with live consent (owner's voice only) | ⬜ |
| Image-provider spike (only free, commercial-OK; otherwise off) | ⬜ |
| **Channel art:** logo 800×800 and banner 2560×1440 from the blueprint, in Branding Studio and the setup kit; Download/Copy; you upload | ⬜ |
| **Video watermark with your SEMRS brand:** 150×150 PNG from your SEMRS logo file (yours, with a rights record), shown next to the channel art; Download; you set it in YouTube Studio › Customization › Branding › Video watermark | ⬜ (owner request, 2026-11-15) |
| Your part (when Phase 8 starts): record voice samples and consent; listen to Urdu voices; optional Pexels/Pixabay keys; **give your SEMRS logo file** (PNG/SVG) for the watermark | ⬜ |

## Phase 9 — Editing & rendering ⬜
| Step | Status |
|---|---|
| Timeline schema, auto-assemble, edit instructions | ⬜ |
| FFmpeg rendering (segments, loudness, RAM guard) | ⬜ |
| Quality checks (black, frozen, silence, loudness) | ⬜ |
| Video Studio, Render Manager | ⬜ |
| External editors (hand-off and return, declaration) | ⬜ |
| Benchmarks on your PC | ⬜ |
| Your part: none (benchmarks run on your PC when asked) | — |

## Phase 10 — Thumbnails & SEO ⬜
| Step | Status |
|---|---|
| Thumbnail concepts, composer, checks | ⬜ |
| SEO package and AI-disclosure assessment | ⬜ |
| Captions | ⬜ |
| Made-for-kids and disclosure decisions (always yours) | ⬜ |
| Pages wired | ⬜ |
| Your part: none | — |

## Phase 11 — Copyright, policy & quality auditing ⬜
| Step | Status |
|---|---|
| Copyright, policy and quality auditors; originality score | ⬜ |
| Separate auditor role | ⬜ |
| Override flow (reason, re-auth, non-overridable list) | ⬜ |
| Security and system auditors | ⬜ |
| Copyright & Policy Center, Approval Center | ⬜ |
| Your part: none | — |

## Phase 12 — Upload & scheduling ⬜
| Step | Status |
|---|---|
| Full upload safety rules; upload jobs; duplicate guard (G4) | ⬜ |
| Thumbnail, captions, playlists after upload | ⬜ |
| Scheduling (private + publish time ≥ now + 15 min) | ⬜ |
| Private-only switch, mode guards | ⬜ |
| Quota-extension audit package (optional) | ⬜ |
| Your part: none | — |

## Phase 13 — Analytics & optimisation ⬜
| Step | Status |
|---|---|
| Analytics fetch and snapshots; 30-day re-auth checks | ⬜ |
| Analytics Dashboard | ⬜ |
| Growth suggestions (retention vs hooks) | ⬜ |
| Comment moderation (you approve every action) | ⬜ |
| Own-channel outliers (Channel Trending) | ⬜ |
| Your part: none | — |

## Phase 14 — Notifications ⬜
| Step | Status |
|---|---|
| Dispatcher, Telegram, e-mail (SMTP), digests, quiet hours | ⬜ |
| Notification Center | ⬜ |
| Your part (when Phase 14 starts): create a Telegram bot | ⬜ |

## Phase 15 — Security, testing & deployment hardening ⬜
| Step | Status |
|---|---|
| Threat-model review and fixes | ⬜ |
| Backups, key export, restore test | ⬜ |
| Full end-to-end test on the test channel | ⬜ |
| Deployment guide verified on a clean Windows machine; installer (G5) | ⬜ |
| Performance tuning | ⬜ |
| Your part: none (a clean-machine check if you have one) | — |

## Phase 16 — Launch & monitoring ⬜
| Step | Status |
|---|---|
| Real channel live (Private-only ON → OFF after 3 tests) | ⬜ |
| Runbooks | ⬜ |
| Monitoring and weekly review | ⬜ |
| 30-day launch review | ⬜ |
| Your part: none listed (your approvals at each publish) | — |

## After completion — White-label selling (not scheduled) ⬜
| Step | Status |
|---|---|
| Product site, white-label pages, live demo (`tubeforge.semrs.com`) | ✅ |
| Licence decision for future versions (repository public under MIT today) | ⬜ (your decision) |
| "TubeForge" trademark check | ⬜ (your part) |
| Branding settings, licence key, Windows installer, payments, end-user licence agreement, support | ⬜ |
| Hosted online version (SaaS) | ⛔ not planned: needs a paid VPS, Google verification and its own ADR |
| Hosting on Vercel's free plan | ⛔ its free plan forbids commercial use |
