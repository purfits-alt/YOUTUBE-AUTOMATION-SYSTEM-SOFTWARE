# YouTube API Integration

**Status:** §1 written in Step 0.3 (verified facts). Sections 2+ (endpoints, OAuth flow, upload flow, quota ledger design, error classification, retention jobs) will be written in **Step 0.5**.

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
