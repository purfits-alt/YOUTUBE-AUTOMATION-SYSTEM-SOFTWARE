# Channel Discovery & Niche Intelligence Specification

**Version:** 0.1 (Step 0.6, for Checkpoint C5) · **Date:** 2026-11-08
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

## 2. Channel Opportunity Score

Score per candidate = **Σ (wᵢ × vᵢ) / Σ wᵢ**, where vᵢ ∈ [0, 100] is the criterion value and wᵢ ∈ [0, 10] is the owner-adjustable weight. A criterion with `confidence = LOW` and no evidence counts at **50 % weight** (an uncertainty penalty). Recalculating with new weights is done in code without calling an LLM (`POST /niches/rescore`).

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
