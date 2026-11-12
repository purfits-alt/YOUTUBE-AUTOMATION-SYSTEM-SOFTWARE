# Channel Discovery & Niche Intelligence Specification

**Version:** 1.0 (approved at C5, 2026-11-08) · **Date:** 2026-11-08
**Agents:** A02 Niche Discovery, A03 Trend Intelligence, A04 Competitor Research (lookup only), A05 Keyword Research, A06 Channel Strategy, A07 Channel Branding
**Policy basis:** ADR-0015 (no aggregation of YouTube API data across channels), DP-1, DP-2, F9

## 1. Data sources (all registered in `research_sources`)

| Code | Kind | What it gives | Default | Terms status |
|---|---|---|---|---|
| `WIKIPEDIA_PAGEVIEWS` | API (Wikimedia REST) | Daily pageviews per article/language → audience interest proxy, rising topics | ON | Wikimedia API — verify terms in Phase 6 |
| `RSS:<slug>` | RSS/Atom feeds the owner approves (news, official blogs, government sites) | Rising topics, facts | OFF until owner adds feeds | Per feed — `REQUIRES_OWNER_APPROVAL` |
| `TRENDS_API_ALPHA` | Google Trends API (alpha) | Search interest (5-year window) | OFF (only if the owner is accepted into the alpha) | Alpha terms |
| `OWN_ANALYTICS` | Own channels' YouTube Analytics | What works on the owner's channels (same content owner — allowed) | ON once connected | YouTube API ToS |
| `OWNER_NOTES` | Owner input | Expertise, interests, constraints | ON | — |
| `WEB_ALLOWLISTED` | Specific owner-approved hosts (e.g. official statistics sites) | Facts and figures | OFF | `REQUIRES_OWNER_APPROVAL` |
| ~~YouTube statistics of other channels~~ | — | **Not used for scoring** (DP-1) | — | — |
| ~~Scraped Google Trends / YouTube autocomplete~~ | — | **Forbidden** (scraping) | — | — |

Fetcher rules: OAUTH_SECURITY §6–7 (allowlist, SSRF guard, 2 MB cap, sanitising, untrusted wrapper). Documents expire after 90 days.

**Implemented in Phase 6 step A** (`apps/api/tubeforge/research/`, migration 0009):
- **Registry.** The four built-in sources are seeded. `WIKIPEDIA_PAGEVIEWS` (on) uses `wikimedia.org/api/rest_v1/metrics/pageviews`, with human traffic and all access methods. It provides daily pageviews per article and a daily top list without Main_Page or Special:, Wikipedia:, Portal:, Help:, File: and Talk: pages.
- **Terms check.** Its terms page could not be opened from the build machine on 2026-11-10, so `terms_verified_at` stays empty until the owner presses "I checked the terms".
- **RSS.** Each feed item is stored as its own document, and item links are never fetched.
- **Trends alpha.** `TRENDS_API_ALPHA` refuses every call: it is off, needs approval, and its adapter is added once the owner has alpha access.
- **Retention.** Hourly job `mnt.retention.purge_research_docs` (minute 50) deletes documents past `expires_at`. Fetching an identical document again refreshes its expiry.

**Implemented in Phase 6 step B** (`research/{scoring,niches,forbidden,signals,blueprint}.py`, `workers/tubeforge_agents/{discovery_agents,discovery}.py`, migration 0010):
- **Collecting evidence.** Discovery collects up to 40 documents:
  - one-year Wikipedia pageview series for up to 24 seed topics. With no interests ("let TubeForge suggest"), a fixed list of broad, advertiser-friendly topics that can be produced on H-LITE is used. This list is English only; other languages need interests given as Wikipedia titles in that language;
  - items from the owner's enabled RSS feeds.
- **Metrics.** Demand, growth and steadiness hints are computed in code and passed to A02. The model only reads them.
- **Checks on A02's answer:**
  - citations of unknown documents are removed, and a criterion that is not LOW but has no evidence left is downgraded to LOW with a note;
  - candidates that match the avoid list, contain a forbidden phrase or use a language that was not requested are dropped, with the reason shown in the report.
- **Storage.** Scores are stored to two decimals. The model's originality angles are kept in a side record `{"code": "_ORIGINALITY_ANGLES"}` inside `criteria`.
- **Report status.** `niche_reports.status` is one of QUEUED, RUNNING, DONE, FAILED, WAITING_QUOTA or STOPPED. The outcome (documents, candidates, dropped, skipped, error) is stored in `params.result`.
- **Blueprint generation (A07, then A06).**
  - Near-duplicate ideas (similarity ≥ 0.85) are removed and the calendar is re-pointed to the remaining ideas. Code picks the palette contrast pair and adds font licences.
  - A blueprint that breaks the schema or contains a forbidden phrase is not saved.
  - A06 and A07 are told the forbidden phrases up front. If an answer still uses one (e.g. "guaranteed" in one of 50 ideas), that agent is asked once more, with the rule name and field path (never the model's own text). A second offence fails the blueprint as before.
  - Otherwise it is saved as a DRAFT `channel_strategies` row (`channel_id` empty, version per candidate). Any remaining rule problems are returned with it and block approval (step D).
- **Trend scan (A03).**
  - Runs daily at 06:00 PKT for ACTIVE channels with an approved blueprint.
  - Signals: for each pillar, the 7-day vs 28-day pageview z-score and the feed frequency (matching items ÷ 2, capped at 5).
  - Only signals of at least 1.0 are sent to A03.
  - The stored strength is always the code value; expiry is clamped to 3–60 days; items citing no real document are dropped.
- **Keywords (A05).** Phrases that claim a search volume without a cited document are dropped. Phrases are upserted per channel.

## 2. Channel Opportunity Score

Score per candidate = **Σ (wᵢ × vᵢ) / Σ wᵢ**, where vᵢ ∈ [0, 100] is the criterion value and wᵢ is the owner-adjustable weight. Owner weights are 0–10. Weights up to 15 are accepted because the built-in profiles multiply some defaults by 1.5 (decided in Phase 6). A criterion with `confidence = LOW` and no evidence counts at **50 % weight** (an uncertainty penalty). Recalculating with new weights is done in code without calling an LLM (`POST /niches/rescore`).

| Code | Meaning (higher = better for the owner) | Default weight | Evidence typically from |
|---|---|---|---|
| AUDIENCE_DEMAND | Size and stability of interest | 8 | Wikipedia pageviews, Trends alpha |
| SEARCH_INTEREST | People actively look for answers | 6 | Trends alpha, question-form keywords |
| RISING_TOPICS | Momentum in the last 90 days | 5 | pageview deltas, RSS frequency |
| EVERGREEN | Interest lasts beyond news cycles | 7 | 3–5-year pageview history |
| COMPETITION_LEVEL | Room for a new voice (qualitative; no YouTube stats) | 4 | LLM reasoning over sources, marked LOW confidence unless evidenced |
| ADVERTISER_SUITABILITY | Advertiser-friendly topic | 6 | Policy knowledge (advertiser-friendly guidelines) |
| PRODUCTION_FEASIBILITY | Achievable on the owner's hardware with licensed visuals | 9 | Hardware profile + format analysis |
| ORIGINALITY_OPPORTUNITY | Room for the owner's own insight, data, voice | 9 | Owner profile + niche nature |
| LONG_FORM_POTENTIAL | Depth for 8–20 min videos | 5 | Topic breadth |
| SHORTS_POTENTIAL | Works in ≤ 3 min vertical | 4 | Topic nature |
| INAUTHENTIC_RISK_INVERSE | Low risk of "inauthentic/reused" judgement | 10 | YPP examples vs typical formats in the niche |

Display rules:
- The score is shown with one decimal place and a confidence band (± 10 if more than 30 % of the weight is LOW-confidence).
- The breakdown table is always visible.
- A fixed footer reads: *"Estimates based on cited sources. Not a prediction of views, subscribers or earnings."*

**Weight profiles:** "Balanced" (defaults), "Originality-first" (ORIGINALITY ×1.5, INAUTHENTIC ×1.5), "Low effort on H-LITE" (FEASIBILITY ×1.5). The owner can save custom profiles.

**"Evergreen ad revenue" (default since migration 0012, owner request 2026-11-12):** the owner's goal is steady ad income from long-lasting views.
- Weights: EVERGREEN 15, ADVERTISER_SUITABILITY 14, AUDIENCE_DEMAND 12, INAUTHENTIC_RISK_INVERSE 12, SEARCH_INTEREST 11, LONG_FORM_POTENTIAL 11, ORIGINALITY 9, FEASIBILITY 8, RISING_TOPICS 6, COMPETITION 6, SHORTS 5.
- The inauthentic-content guard stays heavy: ad income needs YPP, and reused or inauthentic content is the main reason channels are refused.
- Shorts and rising topics help early reach, but long-form earns most ad income, so they weigh less.
- 0012 moves the default only if it was still "Balanced"; its downgrade restores it.

**Remarks (deterministic, no AI):** every candidate lists up to 3 strengths and up to 2 things to watch.
- A strength is a criterion with value ≥ 65, ranked by weight × value.
- A thing to watch is a criterion with weight ≥ 8 that has value < 50 or LOW confidence.
- Remarks follow the weights in use, so they change on rescore.
- The best candidate the owner has not dismissed is marked "Recommended".
- Remarks name criteria and values only. Like every score, they are an estimate, not a prediction of views or earnings.

## 3. Discovery flow

1. The owner starts discovery (languages, interests, niches to avoid).
2. A02 plans source queries. The fetcher collects ≤ 40 documents (pageviews series + feed items + allowed pages). Documents are deduplicated by hash.
3. A02 returns ≤ 15 candidates (schema in AGENT_PROMPTS A02). The orchestrator validates that every non-LOW criterion cites a document that exists.
4. Scores are computed in code. Candidates are stored (`niche_candidates`).
5. The owner reviews them, adjusts weights, then shortlists or dismisses.
6. For a shortlisted candidate the owner clicks **Generate blueprint** → A06 strategy + A07 branding → `channel_strategies` DRAFT → owner edits → PROPOSED → APPROVED (creates the channel in state APPROVED).

## 4. Channel Blueprint (`channel_blueprint.json`)

| Section | Content | Producer |
|---|---|---|
| name_ideas (10) | name, reason, "check availability manually" note | A07 |
| description | ≤ 1000 chars | A07 |
| brand identity | tone words, palette (4–6 hex with roles + contrast pair), fonts (licensed list), logo brief, banner brief | A07 |
| positioning | one paragraph naming the owner's unique contribution | A06 |
| target audience | description + needs | A06 |
| content pillars | 3–7 | A06 |
| video formats | ≥ 3 (long + Shorts), each with the owner's role (voice, data, on-camera, screen recording) | A06 |
| 30-day editorial calendar | respects channel caps (default ≤ 1 long-form/day, ≤ 7/week, ≤ 2 Shorts/day; recommended start is 2 long-form + 4 Shorts per week on H-LITE) | A06 |
| 50 initial ideas | title, format, pillar, angle; diversity check (pairwise similarity < 0.85) | A06 (+ A08 similarity) |
| competitor summary | **only** from owner-initiated lookups the owner attached; each channel described separately; no combined stats | Owner-driven (A04) |
| growth strategy | legitimate tactics only (consistent schedule, playlists, community posts by the owner, collaborations) | A06 |
| policy & monetisation risks | including inauthentic-content risk and its mitigation, advertiser-friendliness, copyright pitfalls | A06 |

Logo and banner: TubeForge produces **briefs** and simple procedural drafts (text logo with brand font and colours). The owner may design them in an external editor (ADR-0021).

## 5. Trend Intelligence (A03)

- **Daily scan** per ACTIVE channel (light queue, 06:00 PKT): pageview deltas for the pillar-related article set (7-day vs 28-day baseline, z-score), RSS item frequency per entity, and Trends alpha if enabled.
- **Signal strength** = max(z-score, normalised feed-frequency delta), computed in code. A03 only clusters and summarises.
- **Expiry:** news topics 7 days, seasonal 30 days, evergreen-rising 60 days. Expired items are hidden.
- `videos.list chart=mostPopular` is **not used** for trends (it only reflects the Music, Movies and Gaming charts since Jul 2025, Y10).

## 6. Keyword Research (A05)
- Seeds come from pillars and ideas. Output phrases come with intent and evidence. **No invented search volumes.**
- Keywords feed A11 (natural use in scripts) and A19 (titles and tags). They never feed niche scores as numeric evidence unless they are sourced (e.g. Trends alpha).

## 7. Competitor research (A04) — compliance-first
- Single-item lookups only, started by the owner (Competitor Research page).
- Results show only that item's public metadata: title, published date, view count as of fetch time, duration, description excerpt, channel name, subscriber count if public.
- **Not allowed:** tables comparing several channels, averages, rankings, "competitor pattern" analytics, automatic background lookups, or use in scoring.
- Cache ≤ 30 days (`youtube_api_cache.expires_at` CHECK). Purged hourly.

**Implemented in Phase 6 step C** (`youtube/lookup.py`, `api/v1/lookups.py`):
- **What the owner can enter.** A channel ID (UC…), a @handle, a youtube.com or youtu.be link (only parsed, never opened), or a search of 2–100 characters showing at most 10 results.
- **What is kept.** Only the listed public fields; everything else Google returns is dropped before storage. Searches keep the search snippets only, with no per-result statistics calls.
- **Cache.** 30 days, shared by identical queries. A cached answer makes no call and uses no quota. Expired entries are never shown and are purged hourly.
- **Which access is used.** Calls use the owner's first connected channel (`youtube.readonly`) and are metered in the quota ledger (searches in the SEARCH bucket). Emergency Stop blocks new calls.
- **Every answer** carries the notice "Public info about one channel or video — not combined with others. Kept for 30 days at most."

**Phase 6 step D (screens):**
- **Channel Discovery** (page 2):
  - runs: "let TubeForge suggest" when no interests are given, or your interests, plus the avoid list and weight profile;
  - candidates with score ± band, risk and difficulty;
  - shortlist, dismiss and generate blueprint;
  - weights and profiles (rescore without AI), and the list of what was left out and why;
  - the research-source registry: switch on/off with the password for new sources, "I checked the terms", test fetch, and add feed.
- **Niche Research** (5): the breakdown with evidence links and quotes, originality angles, and links to the candidate's blueprints.
- **Trend Intelligence** (6): scan now; dismiss. Turning a trend into an idea arrives in Phase 7.
- **Competitor Research** (7): policy banner; one result per lookup, each with the notice; recent lookups shown one by one.
- **Channel Branding Studio** (8):
  - shows the blueprint and the problems that must be fixed;
  - you can edit the description, positioning and idea titles;
  - Propose, Approve (choose the name; it starts as the test channel; it creates the channel and opens its onboarding), Reject and New version.

## 8. Onboarding (manual channel creation + connection)
Steps are stored in `onboarding_steps`, and each shows official help links (verified when Phase 4 starts):
1. Create or choose a Google account for the channel (a separate account is recommended for the test channel).
2. Create the YouTube channel (brand account optional).
3. Verify the channel (phone), which is needed for custom thumbnails (Y5).
4. Create a Google Cloud project — **no billing**.
5. Enable YouTube Data API v3 + YouTube Analytics API.
6. Configure the OAuth consent screen (External, test user = owner).
7. Create an OAuth client (Desktop app) and register it in TubeForge.
8. Publish the privacy policy and terms (GitHub Pages template).
9. Connect (OAuth PKCE) and confirm the channel identity.
10. Run a test private upload → ACTIVE (Private-only ON).

## 9. Acceptance tests (Phase 6)
- Rescore is deterministic: the same inputs and weights give the same score, with no LLM call.
- Every candidate criterion with value and confidence ≠ LOW references existing `source_documents`.
- The forbidden-phrase scan of all discovery and blueprint outputs finds 0 hits.
- A static check finds no code path that writes YouTube API data from `youtube_api_cache` into `niche_candidates`, `trend_items` or `channel_strategies`.
- Blueprint schema valid, with 50 ideas and pairwise similarity < 0.85.
