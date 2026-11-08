# Frontend Specification

**Version:** 1.0 (approved at C4, 2026-11-08) · **Date:** 2026-11-08
**Stack:** Vite + React + TypeScript (strict) + React Router + TanStack Query/Table + Tailwind (ADR-0006). Hand-built components, inline SVG icons and charts, CSS motion and our own Lottie animations replace shadcn/ui and Recharts (ADR-0023). Served by FastAPI at `http://127.0.0.1:8765`.
**API:** `BACKEND_SPECIFICATION.md` (typed client generated from OpenAPI) · **Permissions:** `OAUTH_SECURITY.md` §3

---

## 0. Global design

### 0.1 App shell
- **Desktop (≥ 1024 px):** collapsible left sidebar (grouped nav), top bar, content area. Max content width 1440 px.
- **Tablet (640–1023 px):** sidebar collapses to icons.
- **Mobile (< 640 px):** bottom tab bar (Home, Approvals, Projects, Notifications, More) and a drawer for everything else.
- **Top bar (always visible on every page):**
  - 🔴 **Emergency Stop** button. A red outlined button; when active it is solid red with "STOPPED". Pressing it opens a confirm dialog with an optional reason field (target < 2 clicks). Clearing it needs re-authentication.
  - **Global search** (`Ctrl+K`): searches channels, ideas, projects, assets and notifications.
  - **Channel switcher** with a **mode badge** (MANUAL / SEMI / AUTO) and a **Private-only badge** for the selected channel.
  - **Quota/usage meter**: a mini bar for the YouTube DEFAULT bucket plus the highest free-tier usage %. Click → Cost & Usage.
  - **Notification bell** with unread count.
  - User menu.
- **Global banners** (stacked, dismissible only where noted):
  - Emergency Stop active (not dismissible).
  - Publishing kill switch active.
  - Private-only mode ON for the selected channel ("Uploads stay private; you publish in YouTube Studio").
  - Token expiring within 24 h or NEEDS_REAUTH.
  - Backend offline.
  - Re-verification overdue.

### 0.2 Navigation groups
| Group | Pages |
|---|---|
| Home | 1 Overview |
| Discover | 2 Channel Discovery · 5 Niche Research · 6 Trend Intelligence · 7 Competitor Research |
| Channels | 3 Channel Manager · 4 Onboarding · 8 Branding Studio · 32 Channel Trending |
| Create | 9 Idea Generator · 10 Content Calendar · 11 Script Studio · 12 Storyboard · 13 Video Studio · 14 Visual Assets · 15 Voiceover · 16 Thumbnails · 17 SEO · 18 Captions |
| Publish | 19 Render Manager · 20 Upload Manager · 21 Scheduler · 22 Approval Center |
| Grow | 23 Analytics · 24 Growth & Optimization |
| Library | 25 Asset Library |
| Control | 26 Cost & Usage · 27 Notifications · 28 Agent Control · 29 Copyright & Policy · 30 Audit & Security · 31 Settings |

Project-scoped pages (11–18) share a **Project header**: title, channel, format, state stepper (from WORKFLOW_STATE_MACHINE), allowed commands as buttons (computed by the API), and blocking-guard hints.

### 0.3 Standard states (every page implements all four)
| State | Pattern |
|---|---|
| **Empty** | Illustration-free card: one-sentence explanation + primary action + link to help |
| **Loading** | Skeletons that match the layout. Show them after 150 ms. Never a blank page. |
| **Error** | problem+json `title`/`detail` shown in plain language, plus `code` and `request_id` in a details toggle. Retry button. For 409 GUARD_FAILED, list each failed guard with a link to fix it. |
| **Success** | Toast (4 s) for actions. Inline "saved" indicators for forms. SSE-driven live updates without full reload. |

### 0.4 Cross-cutting behaviour
- **Forms:** react-hook-form + zod schemas generated from the OpenAPI/JSON Schemas. Server errors are mapped to fields. Unsaved-changes guard on navigation. Optimistic locking via `If-Match`; on 412, show a merge/reload dialog.
- **Idempotency:** each command button generates an `Idempotency-Key` on first click and is disabled until the response arrives (no double submits).
- **Step-up (re-auth):** a 403 `REAUTH_REQUIRED` opens a password/TOTP modal, then retries the request automatically.
- **Real-time:** a single SSE connection (`/events/stream`) feeds TanStack Query cache invalidation by entity type.
- **Accessibility:** WCAG 2.2 AA. Keyboard reachable. Focus rings. ARIA live region for toasts and progress. Colour never the only signal (badges have icons and text). Contrast checked in CI with axe.
- **Theming:** light/dark/system. Design tokens in CSS variables.
- **i18n:** all strings in `apps/web/src/i18n/en.json` (English UI v1). Content fields support RTL (`dir="auto"`) for Urdu.
- **Time display:** owner timezone (Asia/Karachi) by default. YouTube quota reset shown in both PT and PKT. Schedules show PKT and the channel's audience timezone.
- **Safety copy:** pages that show scores or analytics carry the note "Estimates with sources — not a promise of views or earnings."
- **Tables:** TanStack Table with server-side sort/filter/pagination (cursor), column visibility, CSV export where noted, sticky header, 50 rows per page.

### 0.5 Route permissions
The router reads `/auth/me` permissions. Pages the user can't view show a 403 page. Action buttons the user can't use are hidden (not just disabled), except approval buttons, which are shown disabled with a tooltip explaining who can approve.

---

## 1. Overview Dashboard

| Item | Specification |
|---|---|
| **Route** | `/` |
| **Purpose** | At-a-glance status of all channels, pipeline, approvals, quota, usage and alerts. |
| **Layout — desktop** | 12-col grid: KPI row (channels active, projects in progress, pending approvals, quota today, free-tier usage peak); Pipeline board (counts per state, click → Projects filtered); Pending approvals list (top 5); Alerts (critical first); Upcoming schedule (7 days); Recent activity feed. |
| **Layout — mobile** | Single column; KPI row becomes horizontal scroll cards; pipeline as collapsible list. |
| **Components** | StatTile, PipelineBoard, ApprovalList, AlertList, ScheduleList, ActivityFeed, QuotaMeter, UsageMeter |
| **Forms & validation** | None. |
| **Buttons & actions** | Open approval · Open project · Open alert target · Refresh. |
| **Tables** | Recent activity (time, actor, action, entity) — 20 rows, link to Audit Center. |
| **API calls** | GET /dashboard/overview |
| **Real-time events** | state.changed, approval.requested, notification.created, quota.updated, usage.updated, control.changed |
| **Permissions** | dashboard.view (all roles) |
| **Empty state** | No channels yet → hero card 'Start with Channel Discovery or add an existing channel' + two buttons. |
| **Loading state** | Skeleton tiles and list rows (no spinners over 300 ms without skeleton). |
| **Error state** | Inline error card per widget with Retry; global banner if API offline. |
| **Success state** | Live counters update; toast for new approvals. |

## 2. Channel Discovery

| Item | Specification |
|---|---|
| **Route** | `/discovery` |
| **Purpose** | Run niche discovery and compare opportunity candidates with transparent scores and evidence. |
| **Layout — desktop** | Left: 'New discovery' form card. Right: Reports list. Report detail: candidates table + side panel with criteria breakdown (value × weight, evidence links, confidence), inauthentic-risk and hardware-difficulty badges, weight sliders (live re-score). |
| **Layout — mobile** | Form full width; candidates as cards; criteria panel as bottom sheet. |
| **Components** | DiscoveryForm, ReportList, CandidateTable, CriteriaBreakdown, WeightSliders, EvidenceList, RiskBadge |
| **Forms & validation** | Discovery form: languages (multi-select of en/es/fr/de/ur, ≥1), interests (tags, ≤10, each ≤40 chars), avoid niches (tags), weight profile (select). Weight sliders: 0–10 each, normalised. |
| **Buttons & actions** | Run discovery (⚙ job) · Shortlist · Dismiss · Generate blueprint (→ Branding Studio) · Save weight profile. |
| **Tables** | Candidates: name, language, opportunity score (sortable), inauthentic risk, difficulty, confidence, status; filters: status, risk, language. |
| **API calls** | POST /niches/reports, GET /niches/reports/{id}, POST /niches/rescore, POST /niches/candidates/{id}/commands/*, GET/POST /niches/weight-profiles, POST /strategies |
| **Real-time events** | job.progress, job.finished |
| **Permissions** | research.view; run/shortlist research.run; blueprint strategy.manage |
| **Empty state** | No reports → explainer of how scoring works (no YouTube aggregation, ADR-0015) + 'Run first discovery'. |
| **Loading state** | Report running → progress bar with stage names (fetch sources, analyse, score). |
| **Error state** | Job failed → reason + 'Retry'; source blocked → link to Settings › Research sources. |
| **Success state** | Candidates appear; banner: 'Scores are estimates with sources — not a promise of earnings.' |

## 3. Channel Manager

| Item | Specification |
|---|---|
| **Route** | `/channels` |
| **Purpose** | List and manage all channels: state, mode, private-only, token health, caps. |
| **Layout — desktop** | Table of channels + detail drawer (overview, publishing rules, mode, kill switch, voice config summary, OAuth health, danger zone). |
| **Layout — mobile** | Cards per channel; drawer becomes full screen. |
| **Components** | ChannelTable, ChannelDrawer, ModeSwitcher (2-step), PrivateOnlyToggle, TokenHealthBadge, PublishingRulesForm, DangerZone |
| **Forms & validation** | Publishing rules: max long/day (0–5), long/week (0–21), shorts/day (0–10), min originality (0–100), min audit scores per type (0–100), allowed/blocked topics (tags), max stock share (0–100 %), block high inauthentic risk in MANUAL (bool). Channel edit: name (1–80), audience timezone (IANA select), local-only (bool), monetised (bool). |
| **Buttons & actions** | Add channel · Pause/Resume · Change mode (2-step + re-auth) · Private-only on/off (re-auth) · Accept auto-publish rules (shows rules diff, re-auth) · Kill switch · Disconnect & delete data (re-auth) · Delete channel. |
| **Tables** | Channels: name, language, state, mode, private-only, token status (expiry hint), projects in progress, last upload; sort by name/state/last upload. |
| **API calls** | GET/POST/PATCH /channels, POST /channels/{id}/commands/*, /mode, /private-only, GET/PUT /publishing-rules, accept-auto-rules, /oauth/health, POST /system/kill-switches |
| **Real-time events** | state.changed, channel.health, control.changed |
| **Permissions** | channel.view; edits channel.manage; mode/private-only channel.mode (owner) |
| **Empty state** | No channels → 'Create from a blueprint' or 'Add existing channel'. |
| **Loading state** | Table skeleton. |
| **Error state** | Row-level error badge (e.g. NEEDS_REAUTH → 'Re-authorise' button). |
| **Success state** | Toasts for saves; mode badge updates everywhere. |

## 4. Channel Onboarding

| Item | Specification |
|---|---|
| **Route** | `/channels/:id/onboarding` |
| **Purpose** | Guided manual channel creation, Google Cloud/OAuth setup, connection, identity confirmation and test upload. |
| **Layout — desktop** | Stepper (10 steps from onboarding_steps) with instructions, official help links, screenshots placeholders; right panel shows status and what is still missing. |
| **Layout — mobile** | Vertical stepper, one step per screen. |
| **Components** | OnboardingStepper, StepInstructions, OAuthClientForm, ConnectButton, IdentityConfirmCard, PrivacyPolicyChecklist, TestUploadCard |
| **Forms & validation** | OAuth client: label (1–60), client ID (regex '^[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com$'), client secret (optional, write-only). Privacy policy URL (https, must be reachable — checked server-side). Step notes (≤500). |
| **Buttons & actions** | Mark step done/skip · Register OAuth client · Connect with Google (opens consent) · Confirm channel identity · Run test private upload · Finish (→ ACTIVE when guards met). |
| **Tables** | None (stepper). |
| **API calls** | GET /channels/{id}/onboarding, PATCH steps, POST /oauth/clients, POST /oauth/youtube/start, POST /channels/{id}/oauth/confirm-identity, POST /channels/{id}/test-upload |
| **Real-time events** | state.changed, job.progress (test upload), channel.health |
| **Permissions** | oauth.manage, channel.manage (owner) |
| **Empty state** | N/A (always has steps). |
| **Loading state** | Waiting for Google callback → 'Complete sign-in in the browser tab…' with cancel. |
| **Error state** | OAuth error (denied, wrong account, scope missing) → explanation + retry; identity mismatch → 'This is not the channel you selected'. |
| **Success state** | Green check per step; final 'Channel is ACTIVE (Private-only ON)'. Warning card: 'Testing mode: re-authorise every 7 days' with guide link. |

## 5. Niche Research

| Item | Specification |
|---|---|
| **Route** | `/research/niches/:candidateId` |
| **Purpose** | Deep dive into one niche: evidence, sources, audience notes, risks, keyword evidence. |
| **Layout — desktop** | Header (score, risks) + tabs: Evidence, Audience, Content pillars draft, Risks & policy, Keywords. |
| **Layout — mobile** | Tabs become segmented control; evidence as list. |
| **Components** | EvidenceTable, SourceCard, RiskList, KeywordEvidenceTable |
| **Forms & validation** | Keyword add: phrase (1–80), language. |
| **Buttons & actions** | Shortlist · Dismiss · Add keyword · Generate blueprint. |
| **Tables** | Evidence: criterion, source (domain), quote/snippet, fetched at, confidence. Keywords: phrase, evidence count, notes. |
| **API calls** | GET /niches/candidates/{id}, /channels/{id}/keywords |
| **Real-time events** | — |
| **Permissions** | research.view |
| **Empty state** | No evidence (should not happen) → 'Re-run analysis'. |
| **Loading state** | Skeleton. |
| **Error state** | Source unavailable → marked 'expired' with refresh option. |
| **Success state** | — |

## 6. Trend Intelligence

| Item | Specification |
|---|---|
| **Route** | `/trends` |
| **Purpose** | Rising topics per channel from permitted sources, with expiry and confidence. |
| **Layout — desktop** | Channel selector; trend cards grid (topic, summary, sources, strength, confidence, expires in); filters. |
| **Layout — mobile** | Single column cards. |
| **Components** | TrendCard, SourceChips, ConfidenceBadge, ExpiryCountdown |
| **Forms & validation** | Scan options: channel (required). |
| **Buttons & actions** | Scan now (⚙) · Dismiss · Turn into idea. |
| **Tables** | Optional table view: topic, strength, confidence, detected, expires, status. |
| **API calls** | GET /trends, POST /trends/scan, POST /trends/{id}/commands/* |
| **Real-time events** | job.progress, job.finished |
| **Permissions** | research.view; actions research.run |
| **Empty state** | No trends → 'Run a scan' + note on which sources are enabled (link to Settings › Research sources). |
| **Loading state** | Card skeletons. |
| **Error state** | Source failures listed per source; partial results still shown. |
| **Success state** | New trends highlighted; 'Turned into idea' toast with link. |

## 7. Competitor Research

| Item | Specification |
|---|---|
| **Route** | `/research/lookup` |
| **Purpose** | Owner-initiated lookup of ONE public channel/video at a time (Developer-Policy compliant, ADR-0015). |
| **Layout — desktop** | Lookup form (kind + query) → result card (public metadata of that single item); recent lookups list (not combined). Permanent info banner explaining the no-aggregation rule and 30-day cache. |
| **Layout — mobile** | Form then card. |
| **Components** | LookupForm, ChannelInfoCard, VideoInfoCard, PolicyBanner, QuotaCostHint |
| **Forms & validation** | Kind (CHANNEL|VIDEO|SEARCH), query (1–200; channel ID 'UC…', @handle, video ID/URL). SEARCH shows 'uses 1 of 100 daily searches (research share 30)'. |
| **Buttons & actions** | Look up · Attach to project as reference note · Open on YouTube (external link). |
| **Tables** | Recent lookups: kind, query, fetched, expires (no aggregated columns). |
| **API calls** | POST /lookups/youtube, GET /lookups/youtube |
| **Real-time events** | quota.updated |
| **Permissions** | research.lookup |
| **Empty state** | No lookups → explanation + example queries. |
| **Loading state** | Spinner on the result card (single call). |
| **Error state** | Quota wait → 'Search quota used — resets at HH:MM PKT'; not found. |
| **Success state** | Result card; cached badge with expiry date. |

## 8. Channel Branding Studio

| Item | Specification |
|---|---|
| **Route** | `/strategies/:id` |
| **Purpose** | View/edit the channel blueprint (names, description, brand identity, logo/banner briefs, positioning, audience, pillars, formats, 30-day calendar, 50 ideas, risks). |
| **Layout — desktop** | Section navigation left; editable sections right; version selector; approval bar. |
| **Layout — mobile** | Accordion sections. |
| **Components** | BlueprintEditor (JSON-schema form), VersionSelector, NameIdeasList (with 'check availability manually' note), BrandPalettePreview, CalendarPreview, IdeaListPreview |
| **Forms & validation** | All blueprint fields per channel_blueprint.json (e.g. description ≤1000, pillars 3–7, each idea title ≤100). |
| **Buttons & actions** | Save (new version) · Propose · Approve (creates channel) · Reject · Regenerate section (⚙). |
| **Tables** | Ideas (50): title, format, pillar. |
| **API calls** | GET/PATCH /strategies/{id}, POST /strategies/{id}/commands/* |
| **Real-time events** | job.finished |
| **Permissions** | strategy.view; edit/approve strategy.manage |
| **Empty state** | Generating → section placeholders. |
| **Loading state** | Skeleton per section. |
| **Error state** | Schema validation errors inline per field. |
| **Success state** | Approved → 'Channel created — continue to onboarding'. |

## 9. Idea Generator

| Item | Specification |
|---|---|
| **Route** | `/channels/:id/ideas` |
| **Purpose** | Backlog of ideas with similarity warnings; generate, edit, shortlist, approve. |
| **Layout — desktop** | Toolbar (generate, filters, search) + Kanban columns (Suggested, Shortlisted, Scheduled, Approved) or table toggle. |
| **Layout — mobile** | List with state filter chips. |
| **Components** | IdeaCard (similarity badge), IdeaForm, GenerateDialog, KanbanBoard |
| **Forms & validation** | Idea: title (1–100), angle (1–500), target viewer (≤200), format (LONG|SHORT), pillar (select), originality notes (≤1000). Generate: count (1–20), format, pillar. |
| **Buttons & actions** | Generate (⚙) · New idea · Shortlist · Schedule (date picker) · Approve (→ project; blocked if similarity ≥ threshold unless override reason) · Discard. |
| **Tables** | Table: title, format, pillar, similarity, source, state, calendar date; sort/filter. |
| **API calls** | GET/POST /channels/{id}/ideas, POST generate, PATCH /ideas/{id}, POST /ideas/{id}/commands/* |
| **Real-time events** | job.finished, state.changed |
| **Permissions** | content.view; edit content.edit; approve content.approve |
| **Empty state** | No ideas → 'Generate ideas from your blueprint' or 'Add your own idea'. |
| **Loading state** | Card skeletons. |
| **Error state** | Generation failed (quota) → wait time + fallback provider info. |
| **Success state** | New ideas animate in; similarity warnings shown in amber. |

## 10. Content Calendar

| Item | Specification |
|---|---|
| **Route** | `/calendar` |
| **Purpose** | Month/week view of planned ideas, projects in production and scheduled releases across channels. |
| **Layout — desktop** | Month grid with channel colour coding; side list of unscheduled shortlisted ideas (drag onto days). Caps indicator per day. |
| **Layout — mobile** | Agenda list view. |
| **Components** | CalendarGrid, DraggableIdea, CapIndicator, ChannelLegend |
| **Forms & validation** | Date change via drag or date picker. |
| **Buttons & actions** | Drag to schedule · Open item · Filter channels. |
| **Tables** | Agenda: date, channel, title, state. |
| **API calls** | GET /calendar, PATCH /calendar/items/{id} |
| **Real-time events** | state.changed |
| **Permissions** | content.view; edit content.edit |
| **Empty state** | Empty month → 'Drag shortlisted ideas here'. |
| **Loading state** | Grid skeleton. |
| **Error state** | Drop rejected (cap exceeded) → toast with reason. |
| **Success state** | Item moved; caps recalculated. |

## 11. Script Studio

| Item | Specification |
|---|---|
| **Route** | `/projects/:id/script` |
| **Purpose** | Edit AI-drafted script with versions, fact-check results and owner value-add fields. |
| **Layout — desktop** | Three panes: outline (hook/sections/CTA) · editor (rich text, word count, est. duration) · right panel tabs: Fact-check claims, Research brief, Value-add, Versions/diff. |
| **Layout — mobile** | Editor full screen; panels as bottom sheet tabs. |
| **Components** | ScriptEditor, ClaimList (verdict colours), ResearchBriefViewer, ValueAddForm, VersionDiff, DurationEstimator |
| **Forms & validation** | Script body (sections ≥1; hook ≤ 60 words recommended; SHORT total ≤ 180 s est.). Value-add: opinion, experience, data, examples (each ≤ 2000), owner voice (NONE|RECORDED|CLONE), owner footage/photos (bool). Claim override reason (≥20). |
| **Buttons & actions** | Save version · Regenerate section (⚙) · Run fact-check (⚙) · Override claim · Approve research / Approve script (gate) · Request changes. |
| **Tables** | Claims: claim, verdict, sources, explanation, override. |
| **API calls** | GET /projects/{id}, script/versions, /diff, POST script/versions, regenerate, GET claims, POST /claims/{id}/override, GET/PUT value-add, POST commands approve-script |
| **Real-time events** | job.progress, job.finished, state.changed |
| **Permissions** | content.view; edit content.edit; approve content.approve |
| **Empty state** | No script yet → 'Script is being written…' progress or 'Start scripting'. |
| **Loading state** | Editor skeleton. |
| **Error state** | Contradicted claims block approval → list with links; version conflict → merge dialog. |
| **Success state** | Version saved toast; value-add score shown. |

## 12. Storyboard Studio

| Item | Specification |
|---|---|
| **Route** | `/projects/:id/storyboard` |
| **Purpose** | Scene list with narration, visual instruction, on-screen text, durations. |
| **Layout — desktop** | Scene table/cards with drag reorder; scene detail panel; total duration vs target. |
| **Layout — mobile** | Scene cards stacked. |
| **Components** | SceneList (sortable), SceneEditor, DurationBar |
| **Forms & validation** | Scene: narration (1–2000), visual instruction (1–1000), on-screen text (≤120), duration (0.5–120 s), style (select). |
| **Buttons & actions** | Add/remove/reorder scene · Regenerate scene (⚙) · Save (new version). |
| **Tables** | Scenes: #, narration excerpt, visual, duration. |
| **API calls** | GET/PUT /projects/{id}/storyboard, POST scenes/{id}/regenerate |
| **Real-time events** | job.finished |
| **Permissions** | content.view; edit content.edit |
| **Empty state** | Not generated → progress or 'Generate storyboard'. |
| **Loading state** | Skeleton cards. |
| **Error state** | Duration mismatch warning (> ±10 % of target). |
| **Success state** | Saved toast. |

## 13. AI Video Studio

| Item | Specification |
|---|---|
| **Route** | `/projects/:id/studio` |
| **Purpose** | Timeline editor with proxy preview; assemble, adjust, approve rough cut. |
| **Layout — desktop** | Top: preview player (proxy). Bottom: multi-track timeline (video, overlays/text, narration, music, SFX, captions). Right: inspector for selected clip (in/out, effect, transition, text style). Toolbar: assemble, render proxy, approve cut. |
| **Layout — mobile** | Preview + read-only timeline summary; editing recommended on desktop (banner). |
| **Components** | PreviewPlayer, Timeline (tracks, clips, playhead, zoom), ClipInspector, AssetPicker, RenderProgress |
| **Forms & validation** | Clip in/out (≥0, ≤asset duration), transition (none|cut|fade|slide, 0–2 s), Ken Burns params, text style (font from licensed list, size, colour with contrast check), music volume (−40–0 dB, ducking on/off). |
| **Buttons & actions** | Auto-assemble (⚙) · Add asset · Save timeline (version) · Render proxy (⚙) · Approve cut (gate) · Request changes · **Edit with… ▾** (picker, ADR-0021): *Built-in (default)* plus every external editor enabled in Settings (Canva, CapCut, InShot, Filmora, DaVinci Resolve, Kdenlive, Shotcut, OpenShot, Premiere Pro, Other…). Choosing one opens the hand-off dialog (folder path, Open folder, Launch app / Open website, mobile copy instructions), then the **Return dialog**: drop the exported file + mandatory declaration (app & plan, library assets used with licences, AI content added). A licence warning is shown for CapCut library music and Canva Popular Music on monetised channels. |
| **Tables** | None (timeline). |
| **API calls** | GET/PUT /projects/{id}/timeline, POST timeline/assemble, POST renders {PROXY}, POST commands approve-cut |
| **Real-time events** | job.progress (render), job.finished |
| **Permissions** | content.view; edit content.edit; approve content.approve |
| **Empty state** | No timeline → 'Auto-assemble from storyboard'. |
| **Loading state** | Timeline skeleton; proxy rendering progress overlay on player. |
| **Error state** | Assets without rights highlighted red; save blocked with list. |
| **Success state** | Proxy ready → plays; 'Cut approved' badge. |

## 14. Image & Visual Asset Studio

| Item | Specification |
|---|---|
| **Route** | `/projects/:id/visuals` |
| **Purpose** | Create/assign visuals per scene: procedural graphics, charts, kinetic text, owner media, CC0, stock import. |
| **Layout — desktop** | Scene list left; per-scene visual options right (generated procedural variants, uploads, stock search tab). |
| **Layout — mobile** | Scene by scene wizard. |
| **Components** | SceneVisualPicker, ProceduralTemplateGallery, UploadDropzone, StockSearchPanel, RightsStatusBadge |
| **Forms & validation** | Procedural style (select), chart data (CSV paste, validated), text overlay (≤120). |
| **Buttons & actions** | Generate visuals (⚙) · Upload own media · Search/import stock (if enabled) · Assign to scene. |
| **Tables** | Per scene: assigned asset, origin, rights status. |
| **API calls** | POST /projects/{id}/visuals/generate, POST /assets, POST scenes/{id}/assign-asset, GET /stock/search, POST /stock/import |
| **Real-time events** | job.finished |
| **Permissions** | content.edit |
| **Empty state** | No visuals → template gallery suggestions. |
| **Loading state** | Thumbnails skeleton. |
| **Error state** | Licence blocked (editorial/NC on monetised channel) → explanation. |
| **Success state** | Scene marked complete. |

## 15. Voiceover Studio

| Item | Specification |
|---|---|
| **Route** | `/projects/:id/voice` |
| **Purpose** | Produce narration per scene: record own voice, use own voice clone, or licensed TTS; manage voice profiles. |
| **Layout — desktop** | Tabs: Narration (scene list with take player, record button, generate buttons), Voice settings (channel voice config), My voice profiles (create/enrol/consent/delete). |
| **Layout — mobile** | Scene-by-scene recorder. |
| **Components** | SceneNarrationList, Recorder (level meter, countdown, noise reduction toggle), TakeSelector, VoicePicker (licence badges), VoiceProfileWizard (samples → consent code → verify), ConsentCodeCard |
| **Forms & validation** | Voice config: source (OWNER_RECORDING|OWNER_CLONE|TTS), TTS voice (only commercial-OK for monetised), clone mode (CONVERTER|ZERO_SHOT; zero-shot disabled for ur), speaking rate (0.8–1.2). Profile: label (1–40), engine. |
| **Buttons & actions** | Record take · Select take · Generate narration (⚙) · Preview TTS voice · Create voice profile · Record samples · Record consent · Disable/Delete profile (re-auth). |
| **Tables** | Scenes: #, text excerpt, source, take, duration, status. |
| **API calls** | GET/PUT /channels/{id}/voice-config/{lang}, GET /voices/tts, POST /voices/tts/preview, POST narration/generate, recordings/session, recordings, /narration/{id}/select, voice-profiles endpoints |
| **Real-time events** | job.progress, job.finished |
| **Permissions** | content.edit; voice profiles voice.profile (owner only) |
| **Empty state** | No narration → 'Record your voice (recommended) or generate'. |
| **Loading state** | Generating per scene progress. |
| **Error state** | Mic permission denied → instructions; consent mismatch → security notice; language unsupported by engine → alternatives. |
| **Success state** | Take saved; profile READY badge. |

## 16. Thumbnail Creator

| Item | Specification |
|---|---|
| **Route** | `/projects/:id/thumbnails` |
| **Purpose** | Generate/upload ≥3 thumbnails, check them, compare side by side, select. |
| **Layout — desktop** | Grid of variants with check results; comparison mode (2–4 side by side at large and mobile sizes); editor for text overlay. |
| **Layout — mobile** | Swipe carousel. |
| **Components** | ThumbnailGrid, CheckList (dimensions, size ≤50 MB, contrast, small-size readability), CompareView, OverlayEditor |
| **Forms & validation** | Overlay text (≤40 chars recommended, warn >6 words), font (licensed), colours (contrast ≥4.5:1 check), aspect (16:9; 9:16 for Shorts). |
| **Buttons & actions** | Generate (⚙) · Upload own · Edit overlay · Select final (gate input for approval) · **Edit with… ▾** (picker, ADR-0021): *Built-in overlay editor (default)* plus enabled external editors (Canva, CapCut, InShot, Filmora, Photopea, GIMP, Krita, Adobe Express, Photoshop, Other…). Hand-off pack = base image + overlay text + brand colours/fonts + required size (recommended 3840×2160 for videos / 2160×3840 for Shorts; minimum 640 px on the short side). The returned image becomes a new variant and must pass checks and the rights declaration. |
| **Tables** | None. |
| **API calls** | POST thumbnails/generate, POST thumbnails, GET thumbnails, POST /thumbnails/{id}/select |
| **Real-time events** | job.finished |
| **Permissions** | content.edit; select content.approve |
| **Empty state** | None yet → 'Generate 3 variants'. |
| **Loading state** | Grid skeleton. |
| **Error state** | Check failures shown per variant. |
| **Success state** | Selected badge. |

## 17. YouTube SEO Studio

| Item | Specification |
|---|---|
| **Route** | `/projects/:id/seo` |
| **Purpose** | Titles, description, tags, hashtags, chapters, playlists, language, made-for-kids (owner), AI disclosure. |
| **Layout — desktop** | Form sections + live preview of how title/description appear; chapter editor synced to render duration; disclosure card with reasons. |
| **Layout — mobile** | Sections accordion. |
| **Components** | TitleOptions (char counters), DescriptionEditor (≤ 5000 **bytes** — byte counter, important for Urdu), TagInput, ChapterEditor (validates first at 0:00, ≥3 chapters, ≥10 s each), PlaylistPicker, MadeForKidsDecision (explicit yes/no, no default), DisclosureCard |
| **Forms & validation** | Title ≤100 chars, no `<` `>` (warn >70), description ≤5000 bytes, tags total ≤500 chars (commas and quotes around multi-word tags count), hashtags ≤15, chapters valid vs final duration, category, default language, audio language, made_for_kids (required explicit), containsSyntheticMedia confirm (required explicit). |
| **Buttons & actions** | Generate (⚙) · Save version · Decide made-for-kids · Confirm disclosure value. |
| **Tables** | Chapters: start, title. |
| **API calls** | POST seo/generate, GET/PUT /projects/{id}/seo, POST seo/made-for-kids, GET/POST disclosure |
| **Real-time events** | job.finished |
| **Permissions** | content.edit; made-for-kids & disclosure publish.decide (owner) |
| **Empty state** | Not generated → 'Generate SEO package'. |
| **Loading state** | Form skeleton. |
| **Error state** | Misleading-metadata warning with explanation. |
| **Success state** | Saved; checks green. |

## 18. Caption & Subtitle Manager

| Item | Specification |
|---|---|
| **Route** | `/projects/:id/captions` |
| **Purpose** | Generate, edit and review caption tracks per language. |
| **Layout — desktop** | Track list; editor with waveform + cue list; sync check result. |
| **Layout — mobile** | Cue list editor. |
| **Components** | TrackList, CueEditor, WaveformTimeline, SyncCheckBadge |
| **Forms & validation** | Cue text (≤ 42 chars/line recommended, ≤2 lines), times (non-overlapping, within duration). |
| **Buttons & actions** | Generate (⚙) · Edit & save · Mark reviewed (required for Urdu). |
| **Tables** | Tracks: language, method, reviewed, sync status. |
| **API calls** | GET captions, POST captions/generate, PUT /captions/{id} |
| **Real-time events** | job.finished |
| **Permissions** | content.edit |
| **Empty state** | No tracks → 'Generate from script'. |
| **Loading state** | Skeleton. |
| **Error state** | Sync check failed → highlighted cues. |
| **Success state** | Saved. |

## 19. Render Manager

| Item | Specification |
|---|---|
| **Route** | `/renders` |
| **Purpose** | All proxy/final render jobs with progress, QC reports and resource waits. |
| **Layout — desktop** | Table with filters; detail drawer with segments progress, QC report (duration, streams, loudness, black/freeze/silence findings), logs. |
| **Layout — mobile** | Cards. |
| **Components** | RenderTable, SegmentProgress, QCReportView, ResourceWaitBadge, NightWindowInfo |
| **Forms & validation** | None. |
| **Buttons & actions** | Cancel · Retry · Open project. |
| **Tables** | Renders: project, kind, state, progress %, ETA, started, duration, QC result; filter state/kind/channel. |
| **API calls** | GET /renders, /renders/{id}, POST commands |
| **Real-time events** | job.progress, job.finished |
| **Permissions** | content.view; actions render.run |
| **Empty state** | No renders. |
| **Loading state** | Skeleton. |
| **Error state** | Failure class + stderr excerpt (redacted). |
| **Success state** | QC pass badge. |

## 20. Upload Manager

| Item | Specification |
|---|---|
| **Route** | `/uploads` |
| **Purpose** | Upload jobs with step-by-step progress (transfer, thumbnail, captions, playlist, processing), quota and retries. |
| **Layout — desktop** | Quota strip (three buckets + reset time PT/PKT + forecast) + uploads table + detail drawer with step timeline. |
| **Layout — mobile** | Cards; quota strip collapsible. |
| **Components** | QuotaStrip, UploadTable, StepTimeline, PreflightResult |
| **Forms & validation** | None. |
| **Buttons & actions** | Retry step · Cancel (before transfer completes) · Open on YouTube Studio. |
| **Tables** | Uploads: project, channel, privacy, publish at, state, progress, video ID, steps status. |
| **API calls** | GET /uploads, /uploads/{id}, POST commands, GET /quota |
| **Real-time events** | job.progress, job.finished, quota.updated |
| **Permissions** | upload.view; actions upload.execute |
| **Empty state** | No uploads. |
| **Loading state** | Skeleton. |
| **Error state** | Preflight refusal shown with invariant code (e.g. IMPLICIT_PRIVACY) and fix link. |
| **Success state** | Completed with video link. |

## 21. Publishing Scheduler

| Item | Specification |
|---|---|
| **Route** | `/schedule` |
| **Purpose** | See and adjust scheduled releases (private + publishAt), respecting caps and quiet hours. |
| **Layout — desktop** | Week/month timeline per channel; list of scheduled items; reschedule dialog. |
| **Layout — mobile** | Agenda list. |
| **Components** | ScheduleTimeline, RescheduleDialog, CapIndicator |
| **Forms & validation** | Publish at (datetime, ≥ now + 15 min, shown in PKT and channel audience tz). |
| **Buttons & actions** | Reschedule (requires new approval) · Open project. |
| **Tables** | Scheduled: channel, title, publish at (PKT/audience tz), privacy, state. |
| **API calls** | GET /schedule, PATCH /schedule/{upload_id} |
| **Real-time events** | state.changed |
| **Permissions** | upload.view; reschedule publish.decide |
| **Empty state** | Nothing scheduled. |
| **Loading state** | Skeleton. |
| **Error state** | Private-only ON → scheduling disabled with explanation. |
| **Success state** | Rescheduled toast. |

## 22. Owner Approval Center

| Item | Specification |
|---|---|
| **Route** | `/approvals` |
| **Purpose** | All pending decisions in one place with full context and hash-bound approval. |
| **Layout — desktop** | Queue list left; review pane right: subject preview (player for cuts/renders, script diff, thumbnail, metadata), audit summary, changes since last approval, decision bar. For UPLOAD_PACKAGE: explicit choice controls (privacy, publish at, made-for-kids, synthetic, notify subscribers) with no defaults pre-selected for made-for-kids. |
| **Layout — mobile** | Queue → full-screen review. |
| **Components** | ApprovalQueue, SubjectPreview, AuditSummary, DiffView, UploadChoicesForm, DecisionBar |
| **Forms & validation** | Upload choices: privacy (required radio, Private pre-selected), publish at (optional, ≥ now+15 min; disabled in Private-only), made-for-kids (required yes/no), synthetic (required, prefilled with assessment), comment (≤1000; required for REJECT/REQUEST_CHANGES). |
| **Buttons & actions** | Approve · Request changes · Reject. |
| **Tables** | Queue: type, channel, subject, requested, age; filter type/channel. |
| **API calls** | GET /approvals, /approvals/{id}, POST /approvals/{id}/decision |
| **Real-time events** | approval.requested, state.changed |
| **Permissions** | approval.view; decisions per subject (publish.decide for uploads) |
| **Empty state** | No pending approvals → 'All caught up'. |
| **Loading state** | Skeleton. |
| **Error state** | APPROVAL_STALE → 'Content changed since this request — reload'. |
| **Success state** | Decision recorded; next item auto-selected. |

## 23. Analytics Dashboard

| Item | Specification |
|---|---|
| **Route** | `/analytics` |
| **Purpose** | Own-channel performance over time (views, engaged views, watch time, AVD, CTR, subs) per channel and video. |
| **Layout — desktop** | Filters (channel, date range); KPI tiles; line charts; top videos table; per-video detail. |
| **Layout — mobile** | Stacked charts. |
| **Components** | KpiTile, TimeSeriesChart, VideoTable, VideoDetail |
| **Forms & validation** | Date range (≤ 365 d), metrics multi-select. |
| **Buttons & actions** | Refresh (⚙) · Export CSV. |
| **Tables** | Videos: title, published, views, engaged views, watch time, AVD, CTR. |
| **API calls** | GET /analytics/channels/{id}, /analytics/videos/{id}, POST /analytics/refresh |
| **Real-time events** | job.finished |
| **Permissions** | analytics.view |
| **Empty state** | No data → 'Analytics appear 48 h after first publish' or enable analytics scope. |
| **Loading state** | Chart skeletons. |
| **Error state** | Scope missing → 'Grant analytics access' button (incremental consent). |
| **Success state** | Charts render; footnote on view-count definition change (2026). |

## 24. Growth & Optimization Center

| Item | Specification |
|---|---|
| **Route** | `/growth` |
| **Purpose** | Data-backed suggestions (topics, hooks, length, upload time) and comment moderation assistant — owner decides. |
| **Layout — desktop** | Suggestions list with evidence; comment suggestions tab (off by default). |
| **Layout — mobile** | Cards. |
| **Components** | SuggestionCard (evidence), CommentSuggestionList, EnableFeatureCard |
| **Forms & validation** | Edited reply (≤ 1000). |
| **Buttons & actions** | Accept · Reject · (Comments) Approve reply / Reject / Enable feature (incremental consent). |
| **Tables** | Suggestions: kind, suggestion, evidence, state. |
| **API calls** | GET /growth/suggestions, POST decision, GET comment-suggestions, POST decision |
| **Real-time events** | notification.created |
| **Permissions** | analytics.view; decide content.approve; comments comments.moderate |
| **Empty state** | No suggestions yet → needs ≥ 3 published videos with 7 days data. |
| **Loading state** | Skeleton. |
| **Error state** | — |
| **Success state** | Accepted suggestions linked to new ideas/tasks. |

## 25. Asset Library

| Item | Specification |
|---|---|
| **Route** | `/assets` |
| **Purpose** | All media with rights status; upload, set rights, manual stock import, free stock search, paid purchase (optional). |
| **Layout — desktop** | Tabs: Library (grid/table), Stock (search per enabled provider), Manual import, Purchases. Detail drawer: preview, metadata, rights form, usage (where used). |
| **Layout — mobile** | Grid with filters sheet. |
| **Components** | AssetGrid, AssetTable, RightsForm, StockSearch, ManualImportForm, PurchaseQuoteDialog (price, budget remaining, confirm), UsageList |
| **Forms & validation** | Rights: basis (enum), licence name, licence URL, commercial (bool), editorial-only (bool), attribution text, proof file. Manual import: file, provider name, asset ref/URL, licence type, cost+currency (optional), proof file (required for paid). |
| **Buttons & actions** | Upload · Set rights · Import stock · Get quote · Confirm purchase (owner, re-auth) · Delete. |
| **Tables** | Assets: preview, kind, origin, channel, rights status, licence, size, created; filter kind/origin/rights status/channel. |
| **API calls** | GET/POST /assets, PUT rights, GET /stock/providers, /stock/search, POST /stock/import, /stock/manual-import, /stock/purchases/quote, /confirm |
| **Real-time events** | job.finished |
| **Permissions** | asset.view; edit asset.edit; stock per provider permissions; purchase owner |
| **Empty state** | Empty library → upload or import. |
| **Loading state** | Grid skeleton. |
| **Error state** | BUDGET_EXCEEDED / provider disabled → link to Cost & Usage. |
| **Success state** | Rights OK badge. |

## 26. Cost & Usage Manager

| Item | Specification |
|---|---|
| **Route** | `/usage` |
| **Purpose** | Every provider's usage vs limit, YouTube quota buckets, stock/paid budgets, disk usage; provider enable/verify; paid activation. |
| **Layout — desktop** | Top: zero-cost status banner ('€0 this month — no paid providers enabled'). Provider table; quota buckets; budgets; disk usage per channel. |
| **Layout — mobile** | Cards. |
| **Components** | ProviderTable (tier, licence, commercial, data-use, limits, verified, re-verify due), UsageBar, QuotaBuckets, BudgetCard, PaidActivationWizard (2 steps, 60 s gap, confirm phrase), DiskUsageChart |
| **Forms & validation** | Limits per provider (≥0 ints). Budget cap (≥0; raising needs re-auth). Credentials (write-only). Verify: URL + notes. |
| **Buttons & actions** | Enable/disable provider · Set limits · Save credentials · Mark verified · Paid activation step 1/2 · Set budget. |
| **Tables** | Providers & usage as described; filter capability/tier. |
| **API calls** | GET /providers, PATCH, PUT credentials, POST paid-activation/step1, step2, POST verify, GET /usage, GET/PUT /budgets, GET /quota |
| **Real-time events** | usage.updated, quota.updated |
| **Permissions** | providers.view; manage providers.manage; paid providers.paid (owner) |
| **Empty state** | N/A. |
| **Loading state** | Skeleton. |
| **Error state** | Re-verification overdue warnings. |
| **Success state** | Saved. |

## 27. Notification Center

| Item | Specification |
|---|---|
| **Route** | `/notifications` |
| **Purpose** | Inbox of notifications; preferences per event × channel; targets setup (Telegram, email); delivery tracking. |
| **Layout — desktop** | Tabs: Inbox, Preferences (matrix), Targets, Deliveries. |
| **Layout — mobile** | Inbox list; matrix as per-event list. |
| **Components** | NotificationList, PreferenceMatrix, TelegramSetup (BotFather guide), EmailSetup, DeliveryTable |
| **Forms & validation** | Telegram bot token (regex '^[0-9]+:[A-Za-z0-9_-]{30,}$'), chat ID (integer); SMTP host/port/user/password/from/to; quiet hours shown read-only (edit in Settings). |
| **Buttons & actions** | Mark read · Mark all read · Save preferences · Send test message. |
| **Tables** | Deliveries: notification, channel, state, attempts, last error, sent at. |
| **API calls** | GET /notifications, POST read, GET/PUT preferences, PUT targets/*, POST test, GET deliveries |
| **Real-time events** | notification.created |
| **Permissions** | session; targets settings.manage |
| **Empty state** | Inbox zero. |
| **Loading state** | Skeleton. |
| **Error state** | Telegram test failed → error text + guide. |
| **Success state** | Test message delivered. |

## 28. AI Agent Control Center

| Item | Specification |
|---|---|
| **Route** | `/agents` |
| **Purpose** | All 32 agents: status, config, limits, runs, errors; pause via kill switch. |
| **Layout — desktop** | Agent grid (grouped: Research, Production, Publishing, Auditors, Ops) with health; detail: config form, prompt version, recent runs, metrics. |
| **Layout — mobile** | List grouped. |
| **Components** | AgentCard, AgentConfigForm, RunTable, RunDetail (input/output JSON viewer, redacted), MetricsChart |
| **Forms & validation** | Provider chain (ordered select from enabled providers with licence/data-use compatibility), limits (calls/day, tokens/day, max runtime), enabled (not editable for auditors). |
| **Buttons & actions** | Save config · Pause agent (kill switch with reason) · Resume · Open run. |
| **Tables** | Runs: time, agent, project, status, provider, tokens, duration, quality score. |
| **API calls** | GET /agents, PATCH /agents/{code}, GET /agents/{code}/prompts, GET /agent-runs, POST /system/kill-switches |
| **Real-time events** | job.progress, job.finished, control.changed |
| **Permissions** | agents.view; manage agents.manage |
| **Empty state** | N/A. |
| **Loading state** | Skeleton. |
| **Error state** | Agent failing rate > 20 % flagged. |
| **Success state** | Saved. |

## 29. Copyright & Policy Center

| Item | Specification |
|---|---|
| **Route** | `/policy` |
| **Purpose** | All audit reports across projects; blocked items; overrides; policy reference. |
| **Layout — desktop** | Summary tiles (blocked, warnings, overrides 30 d); audits table; report detail (findings with evidence and remediation); override dialog. |
| **Layout — mobile** | Cards. |
| **Components** | AuditTable, FindingList, OverrideDialog (reason ≥20, re-auth), PolicyReferenceLinks |
| **Forms & validation** | Override reason (≥20 chars). |
| **Buttons & actions** | Open project · Re-run audit · Override (owner; not for copyright-critical). |
| **Tables** | Audits: project, channel, type, result, score, critical, date; filter result/type/channel. |
| **API calls** | GET /audits, GET /projects/{id}/audits, POST audits/run, POST /audit-reports/{id}/override |
| **Real-time events** | state.changed |
| **Permissions** | audit.view; override audit.override (owner) |
| **Empty state** | No audits yet. |
| **Loading state** | Skeleton. |
| **Error state** | — |
| **Success state** | Override recorded (visible in Audit & Security Center). |

## 30. Audit & Security Center

| Item | Specification |
|---|---|
| **Route** | `/security` |
| **Purpose** | Audit log (hash-chain verified), security events, security posture checklist, sessions. |
| **Layout — desktop** | Tabs: Posture, Audit log, Security events, Sessions. |
| **Layout — mobile** | Tabs as list. |
| **Components** | PostureChecklist, AuditLogTable, ChainVerifyBadge, SecurityEventTable, SessionList |
| **Forms & validation** | Filters only. |
| **Buttons & actions** | Verify chain · Revoke session · Export CSV. |
| **Tables** | Audit log: time, actor, action, entity, channel, details; security events: time, kind, severity, details. |
| **API calls** | GET /security/posture, /audit-log, /audit-log/verify-chain, /security-events, /auth/sessions |
| **Real-time events** | control.changed |
| **Permissions** | security.view (owner) |
| **Empty state** | N/A. |
| **Loading state** | Skeleton. |
| **Error state** | Chain broken → CRITICAL banner with first broken ID. |
| **Success state** | Chain OK badge. |

## 31. Settings & Integrations

| Item | Specification |
|---|---|
| **Route** | `/settings` |
| **Purpose** | System settings, Google Cloud/OAuth clients, research sources, AI providers shortcuts, notifications targets, backups, account & 2FA, about/versions. |
| **Layout — desktop** | Left nav sections: General, Account & security, YouTube & Google, Research sources, AI providers (link to Cost & Usage), Notifications, **External editors** (enable/disable each app, set exe path or website, add custom editor, licence notes such as 'free-plan watermark' or 'library music not for monetised YouTube'), Storage & backups, Advanced. |
| **Layout — mobile** | Section list → detail. |
| **Components** | SettingsForm, OAuthClientList, ResearchSourceTable, BackupPanel (run, list, restore-test, key export), AccountSecurity (password, TOTP enrol, recovery codes) |
| **Forms & validation** | Timezone (IANA), quiet hours, night render window, disk budget (GB ≥ 20), default render profile, password (≥12, strength), TOTP code (6 digits), backup passphrase (≥ 12, confirm). |
| **Buttons & actions** | Save (If-Match) · Enrol/disable TOTP · Run backup · Export key file · Restore test · Enable source (approval-required ones re-auth). |
| **Tables** | OAuth clients; research sources; backups list. |
| **API calls** | GET/PUT /settings, /oauth/clients, /research-sources, /system/backups*, /auth/* |
| **Real-time events** | — |
| **Permissions** | settings.manage (owner) |
| **Empty state** | N/A. |
| **Loading state** | Skeleton. |
| **Error state** | Validation errors inline. |
| **Success state** | Saved toast. |

---

## 32. Channel Trending

*Owner request during Phase 3 (US-4.6, ADR-0025). Screens with sample data now; real data from Phase 7 (ideas) and Phase 13 (own analytics).*

| Item | Specification |
|---|---|
| **Route** | `/channels/:id/trending` |
| **Purpose** | One place to double down on what works **for this channel**: own outliers, variations of own winners, and fresh ideas. |
| **Layout — desktop** | Channel header; three tabs: **Outliers** (own videos ranked by outlier multiple, with KPI tiles: outliers this month, best multiple, median views), **Replicate / Milk** (own winners with variation suggestions and their similarity to the source), **New Ideas** (newest suggested ideas with the reason). |
| **Layout — mobile** | Tabs as a segmented control; tables as cards. |
| **Components** | Tabs, StatTile, DataTable, OutlierBadge (×multiple), VariationCard, SimilarityMeter, SafetyNote |
| **Forms & validation** | Replicate: variation kind (PART_2, NEW_ANGLE, UPDATE, SHORT_FROM_LONG, LONG_FROM_SHORT, SERIES), optional note ≤ 500 chars. |
| **Buttons & actions** | Outliers: Refresh analytics (⚙), Replicate this. Replicate: Create variation idea (blocked when similarity > threshold), Open source on YouTube Studio. New Ideas: Generate ideas (⚙), Shortlist, Open in Idea Generator. |
| **Tables** | Outliers: title, published, views, multiple, engaged views, CTR, AVD. Replicate: source, variation, angle, similarity, state. New Ideas: title, format, reason, similarity, state. |
| **API calls** | GET /channels/{id}/outliers, GET /channels/{id}/replicate, POST /channels/{id}/ideas/replicate 🔁⚙, GET /channels/{id}/ideas?source=AGENT, POST /channels/{id}/ideas/generate 🔁⚙ |
| **Real-time events** | job.finished, state.changed |
| **Permissions** | content.view + analytics.view; create/generate content.edit |
| **Empty state** | Outliers: "No outliers yet — they appear once your videos have 7 days of analytics." Replicate: "Pick an outlier to replicate." New Ideas: "Generate ideas from your trends and winners." |
| **Loading state** | Tile and table skeletons. |
| **Error state** | Per-tab problem card with Retry. |
| **Success state** | "Variation idea created" toast with link to the Idea Generator. Safety note: "Estimates with sources — not a promise of views or earnings." |
| **Compliance** | Own channels only (ADR-0015, ADR-0025): no other channel's videos are ranked or compared. Variations must pass the originality guard (similarity ≤ threshold, owner value-add) and the auditors. |

## 33. Test plan for the frontend (Phase 2 onward)
- **Phase 2 (shell):** all 31 routes render with mocked data in all four states. A Playwright test visits each route × state via MSW (Mock Service Worker) scenarios.
- **Emergency Stop** button is visible on every route (Playwright asserts it on all 31).
- **axe** accessibility scan per route: no serious or critical violations.
- **Visual regression** (Playwright screenshots, desktop + mobile) for key pages: 1, 13, 15, 22, 25, 26.
- **Contract:** the generated TS client is compiled with `tsc --strict` in CI. A breaking API change fails the build.
