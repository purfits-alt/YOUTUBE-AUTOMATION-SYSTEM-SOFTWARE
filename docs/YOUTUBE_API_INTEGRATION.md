# YouTube API Integration

**Version:** 0.1 (Step 0.5, for Checkpoint C4) · §1–§3 verified in Step 0.3, extended 2026-11-08

---

## 1. Verified platform facts (2026-11-08)

Full table with sources: `FREE_TIER_PROVIDER_MATRIX.md` §1–§2. Summary of what the integration must respect:

| # | Fact | Source |
|---|---|---|
| Y1 | Unverified API projects are **no longer** restricted to private uploads (since 2 Nov 2026). An omitted `privacyStatus` defaults to **public**. | [Revision history](https://developers.google.com/youtube/v3/revision_history) |
| Y2 | Quota buckets per project per day: `videos.insert` 100 calls (1 unit each) · `search.list` 100 calls (1 unit each) · all other methods 10,000 units. Reset at midnight PT. | [Quota calculator](https://developers.google.com/youtube/v3/determine_quota_cost) |
| Y3 | Costs: `thumbnails.set` ≈ 50 · `captions.insert` 400 · `captions.update` 450 · `captions.list` 50 · `videos.update` 50 · `videos.list` 1 · `channels.list` 1 · `playlistItems.insert` 50 · `comments.insert` 50 · `commentThreads.list` 1. Every request, even an invalid one, costs ≥ 1. | Quota calculator |
| Y4 | `videos.insert`: max 256 GB, MIME `video/*` or `application/octet-stream`. Scopes: `youtube.upload`, `youtube`, `youtubepartner`, `youtube.force-ssl`. | [videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert) |
| Y5 | `thumbnails.set`: max **50 MB** (raised from 2 MB on 14 Sep 2026), JPEG/PNG. Custom thumbnails for **Shorts** supported via API since 3 Nov 2026 (`shortsAspectRatio`). The channel must be verified. | [thumbnails.set](https://developers.google.com/youtube/v3/docs/thumbnails/set), [Help](https://support.google.com/youtube/answer/72431) |
| Y6 | `captions.insert`: max 100 MB, cost 400. | [captions.insert](https://developers.google.com/youtube/v3/docs/captions/insert) |
| Y7 | `status.containsSyntheticMedia` (since 30 Oct 2024) is for *realistic* altered or synthetic content. Settable on insert and update. | Revision history |
| Y8 | `status.selfDeclaredMadeForKids` is only updated if specified (clarified 15 Oct 2026). TubeForge always sends it explicitly after the owner decides. | Revision history |
| Y9 | Shorts = square or vertical video up to **3 minutes**. | [Help: three-minute Shorts](https://support.google.com/youtube/answer/15424877) |
| Y10 | `videos.list chart=mostPopular` now reflects Trending Music, Movies and Gaming charts (since 21 Jul 2025), **not** general trending. Its value for trend discovery is limited. | Revision history |
| Y11 | Public view counting changed (views count from the first frame, 2026). Monetisation uses "engaged views". Analytics dashboards label both. | Revision history 27 Aug 2026 |
| Y12 | Testing-mode OAuth refresh tokens expire in 7 days. Tokens unused for 6 months expire. Limit of 100 refresh tokens per account per client. | [Google OAuth 2.0](https://developers.google.com/identity/protocols/oauth2) |
| Y13 | Installed-app flow: loopback redirect + **PKCE** recommended. | [OAuth for installed apps](https://developers.google.com/youtube/v3/guides/auth/installed-apps) |
| Y14 | `publishAt` only if `private` **and the video has never been published**. With `videos.update` the request must also send `privacyStatus=private`. **A past `publishAt` publishes immediately.** | [videos resource](https://developers.google.com/youtube/v3/docs/videos) |
| Y15 | Scopes: `videos.insert` and `thumbnails.set` accept `youtube.upload`. `captions.insert` needs `youtube.force-ssl` / `youtubepartner`. `videos.update` and `playlistItems.insert` need `youtube` / `youtube.force-ssl`. | Method reference pages (verified 2026-11-08) |

## 2. Developer Policy rules that shape the integration

See `FREE_TIER_PROVIDER_MATRIX.md` §2 (DP-1 … DP-10) and ADR-0015 / ADR-0016. Key points:
- **No aggregation** of API data across channels that are not under the same content owner, and no "insights into YouTube's business".
- Non-authorized data is kept ≤ 30 days. Authorized data needs 30-day re-authorization and existence checks. Deletion within 7 days of disconnect or request.
- The privacy policy must link to the Google Privacy Policy and to `security.google.com/settings/security/permissions`.
- Express owner consent is needed before any insert, update or delete action on YouTube.
- No scraping. No storing YouTube audiovisual content.
- Projects inactive for 90 days may lose quota.

## 3. Daily capacity (default quota, one Cloud project)

| Activity | Bucket | Cost | Capacity/day |
|---|---|---|---|
| Upload video | uploads | 1 call | 100 |
| Full publish package (thumbnail 50 + captions 400 + playlist 50 + 1 metadata update 50) | shared | ≈ 550 | ≈ 16 (with 10 % reserve) |
| Research search | search | 1 call | 100 (TubeForge budget: 30 by default) |
| Analytics / list calls | shared / Analytics | 1 each | Large |

**Conclusion:** the default quota is enough for 1–10 channels at quality-first publishing caps. A quota extension is not needed in v1.


---

## 4. Module layout (`apps/api/tubeforge/youtube/`)

| Module | Responsibility |
|---|---|
| `oauth.py` | PKCE flow, code exchange, token refresh, revoke, incremental scopes (OAUTH_SECURITY §4) |
| `client.py` — `SafeYouTubeClient` | **The only place that calls YouTube mutation methods.** Preflight invariants (§5), quota reservation, idempotency, error classification |
| `uploads.py` | Resumable upload engine (chunks, offset persistence, resume, duplicate detection) |
| `metadata.py` | Builds `snippet`, `status` and `localizations` bodies from the approved SEO package. Validates lengths. |
| `quota.py` | Quota ledger, reservations, PT-day calculation, forecasts |
| `analytics.py` | YouTube Analytics API reports for own channels |
| `lookup.py` | Read-only, owner-initiated single-item lookups of other channels or videos (ADR-0015), cached ≤ 30 days |
| `retention.py` | DP-2/3/4 jobs (DATABASE_SCHEMA §15) |
| `errors.py` | Error classification table (§7) |

Library: `google-api-python-client` + `google-auth` + `google-auth-oauthlib` (Apache-2.0), versions pinned in `uv.lock`. The upload engine uses `MediaFileUpload(resumable=True, chunksize=8 MiB)` and persists the resumable session URI itself.

## 5. `SafeYouTubeClient` preflight invariants (every mutating call)

| # | Invariant | Failure → |
|---|---|---|
| I-1 | `system_settings.emergency_stop = false` | `REFUSED_EMERGENCY_STOP` |
| I-2 | No active kill switch for the channel. For public or scheduled actions, also no publishing kill switch (global or channel). | `REFUSED_KILL_SWITCH` |
| I-3 | Channel state ∈ {CONNECTED (test uploads only), ACTIVE}. Token healthy. | `REFUSED_CHANNEL_STATE` |
| I-4 | For non-test uploads: latest audit reports for the current `subject_sha256` are all PASSED or WARNING, or every FAILED one has an `audit_overrides` row. Copyright-critical failures cannot be overridden. | `REFUSED_AUDIT` |
| I-5 | Approval request APPROVED, `subject_sha256` == hash(render file sha + SEO package sha + thumbnail sha + upload choices) | `REFUSED_APPROVAL` |
| I-6 | `privacyStatus`, `selfDeclaredMadeForKids` and `containsSyntheticMedia` all explicitly present (non-null) in the request body | `REFUSED_IMPLICIT_FIELD` |
| I-7 | Private-only mode ON ⇒ `privacyStatus = private` and no `publishAt` | `REFUSED_PRIVATE_ONLY` |
| I-8 | `publishAt` set ⇒ `privacyStatus = private` AND `publishAt ≥ now + 15 min` AND the video was never published | `REFUSED_SCHEDULE` |
| I-9 | Channel publishing caps not exceeded (counts uploads per channel and day/week in the owner's timezone) | `REFUSED_CAP` |
| I-10 | Quota reservation succeeds in the method's bucket (with reserve %) | `WAITING_QUOTA` |
| I-11 | Idempotency key not already COMPLETED. The unique index `upload_once` holds. | Returns the existing result |
| I-12 | FULLY_AUTO and no human approval ⇒ the channel's `auto_publish_rules` were accepted (DP-6) and the rule conditions hold (scores, topics, quiet hours) | `REFUSED_AUTO_RULE` |

Every refusal → `audit_log` + `security_events` (WARNING) + a notification. Unit tests cover each invariant on its own.

## 6. Upload algorithm (detail for SYSTEM_ARCHITECTURE §9)

1. **Preflight** (§5). Reserve 1 unit in VIDEO_UPLOADS and ~550 units in DEFAULT for the post-upload steps.
2. **Duplicate guard** (only when an earlier session for this job expired before a video ID was received): read the newest items of the channel's **uploads playlist** with `playlistItems.list` (1 unit per page; `search.list` is not used) and fetch `contentDetails` for any candidate with `videos.list` (1 unit). A candidate is the same upload if (a) its title equals the approved title, (b) it was published within the job's session window (± 2 h), and (c) its duration is within ±1 s of the render. If found → adopt that video ID (no re-upload). If not → start a new session. Nothing is added to the viewer-facing description.
3. **Insert** with `part=snippet,status`, body built only from the approved package. `notifySubscribers` follows the owner's choice (default true for public, false otherwise).
4. **Chunks:** 8 MiB. After each chunk, persist `bytes_confirmed`. On a 5xx or network error, query the session (`PUT` with `Content-Range: bytes */total`) to get the offset, then resume. Backoff 2^n × 5 s, at most 8 resumes.
5. **Success:** persist `youtube_video_id` in the same transaction that marks the idempotency key complete and moves the project → PROCESSING.
6. **Post steps (separate jobs):**
   - `thumbnails.set`: JPEG/PNG ≤ 50 MB. Shorts use the 9:16 variant with `shortsAspectRatio`, only after processing completes (Nov 2026 API).
   - `captions.insert` per language (needs force-ssl).
   - `playlistItems.insert` (needs force-ssl).
7. **Processing poll:** `videos.list part=processingDetails,status` with backoff (30 s → 10 min, max 6 h). Final state → COMPLETED / PROCESSING_FAILED.
8. **Publication tracking:** for SCHEDULED or PRIVATE_DONE projects, a daily `videos.list part=status` call detects the publish and moves the project → PUBLISHED.

## 7. Error classification

| HTTP / reason | Class | Action |
|---|---|---|
| 401, `invalid_grant`, `authError` | AUTH_EXPIRED | Mark connection NEEDS_REAUTH, pause channel jobs, CRITICAL notification |
| 403 `quotaExceeded`, `dailyLimitExceeded` | QUOTA_EXCEEDED | WAITING_QUOTA until next PT midnight. Record in ledger. |
| 403 `rateLimitExceeded`, 429 | RATE_LIMITED | Backoff with jitter, retry (max 5) |
| 403 `forbidden`, `insufficientPermissions` | SCOPE_MISSING | Ask the owner for incremental consent. The step waits. |
| 400 `invalidMetadata`, `invalidTitle`, `invalidDescription`, `invalidTags`, `invalidCategoryId`, `invalidPublishAt` | INVALID_REQUEST | FAILED (step). Owner edits metadata, which needs a new approval hash. |
| 400 `uploadLimitExceeded` (channel-side limit) | CHANNEL_LIMIT | WAITING until the next day. Notify. |
| 403 `videoRejected`, processing `rejected` | POLICY_REJECTED | PROCESSING_FAILED. Notify with reason. |
| 5xx, timeouts, connection reset | TRANSIENT | Retry / resume |
| Anything else | UNKNOWN | FAILED + full (redacted) response in job log |

## 8. Quota ledger & forecasting

- **Buckets:** `VIDEO_UPLOADS` (100 calls), `SEARCH` (100 calls), `DEFAULT` (10,000 units), `ANALYTICS` (YouTube Analytics API, separate — limits read from Cloud Console by the owner and entered in `quota_config`).
- **PT day:** `pt_day = (now() AT TIME ZONE 'America/Los_Angeles')::date`. The reset time is shown in Asia/Karachi too (e.g. "resets at 13:00 PKT", which changes with US daylight saving).
- **Reservation:** `INSERT quota_reservations` in a SERIALIZABLE transaction, checking `sum(ledger today) + sum(held) + units ≤ limit × (1 − reserve%)`. Settled after the call (actual units from config). Released on failure-before-call. Held reservations expire after 30 min.
- **Research share:** SEARCH bucket use by research agents ≤ `research_share_pct` (default 30 → 30 searches/day).
- **Forecast:** daily job computes the planned uploads × package cost for the next 7 days against capacity, and shows warnings in the Upload Manager and the Cost & Usage Manager.
- Every request is recorded, including invalid ones (≥ 1 unit, per Google).

## 9. Analytics (Phase 13)

- YouTube Analytics API `reports.query` for the owner's channels: daily per-video metrics (views, engagedViews if exposed, estimatedMinutesWatched, averageViewDuration, subscribersGained/Lost, impressions and CTR where available, traffic sources).
- Snapshot table `analytics_snapshots` (authorized data, may be kept long-term) + the DP-3 30-day re-authorization and existence check.
- No cross-owner aggregation (one owner → allowed per DP-1).

## 10. Owner-initiated lookups (ADR-0015)

- `lookup_channel(channel_id | handle)` → `channels.list` (1 unit). `lookup_video(id)` → `videos.list` (1 unit). `search(query)` → `search.list` (SEARCH bucket), **only when the owner explicitly runs a search**, max 10 results shown.
- Results are shown individually. **No** combined statistics, rankings or charts across channels. Cached in `youtube_api_cache` ≤ 30 days, then purged.
- These results are **not** fed into niche scores or agent analyses. Agents may receive a lookup only when the owner explicitly attaches it to a project as a reference note. The UI labels it "public info about one channel/video — not combined".

## 11. Compliance task list (feeds COMPLIANCE_CHECKLIST.md, Step 0.7)

- [ ] Privacy policy and terms published (GitHub Pages) before the first OAuth connect.
- [ ] Consent screen configured with minimal scopes. Test user added.
- [ ] Retention jobs active (DP-2/3/4) before the first lookup or analytics fetch.
- [ ] "Disconnect & delete data" verified (7-day deadline monitor).
- [ ] Anti-scraping test and outbound allowlist in CI.
- [ ] No aggregation across channels (code review checklist item + unit test that lookup results never join).
- [ ] API project kept active (warning after 60 days without calls, DP-9).
- [ ] Optional: compliance audit package (only if a quota extension is ever needed).
