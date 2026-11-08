# Compliance Checklist

**Version:** 1.0 (approved at C6, 2026-11-08) · **Date:** 2026-11-08
Each item lists its source, how TubeForge complies, the phase that implements it, and how it is verified. Re-check sources every 90 days (A32 reminder) and before launch (Phase 16).

## A. YouTube API Services Terms & Developer Policies
Source: [Developer Policies](https://developers.google.com/youtube/terms/developer-policies) (page updated 2026-11-06), [API Services ToS](https://developers.google.com/youtube/terms/api-services-terms-of-service)

| ✓ | Requirement | How TubeForge complies | Phase | Verified by |
|---|---|---|---|---|
| ☐ | Privacy policy before use; links Google Privacy Policy; explains data access/storage/use; revocation link; contact | GitHub Pages policy from template (OAUTH_SECURITY §8) | 4 | Owner review + checklist test |
| ☐ | Express consent before insert/update/delete actions on user's behalf (DP-6) | Approval records per action; FULLY-AUTO requires accepted rule set | 5/12 | T-APPROVAL |
| ☐ | Non-authorized data stored ≤ 30 days (DP-2) | `youtube_api_cache` CHECK + hourly purge | 4/6 | T-RET |
| ☐ | Authorized data: verify authorization & video existence every 30 days (DP-3) | `reauthorize_check` job | 4/13 | Job test |
| ☐ | Delete data within 7 days of revocation/request; 30 days if via Google security page (DP-4) | Disconnect & delete; deadline monitor | 4 | T-RET |
| ☐ | No aggregation across content owners; no insights into YouTube's business (DP-1) | ADR-0015; single-item lookups; static check | 6 | T-AGG |
| ☐ | No scraping of YouTube/Google apps (DP-8) | Outbound allowlist; anti-scrape test | 1/3 | Security tests |
| ☐ | No downloading/storing YouTube audiovisual content (DP-7) | No such code path; THIRD_PARTY_VIDEO audit | all | Copyright audit |
| ☐ | Don't collect user's YouTube login credentials | OAuth only; tokens never shown | 4 | Review |
| ☐ | Keep API project active (90-day inactivity rule, DP-9) | 60-day warning | 4 | Job test |
| ☐ | Accurate identification of the API client; latest API versions | Client name "TubeForge (personal)"; pinned library updated | 4 | Review |
| ☐ | Quota extension only via API Compliance Audit for the approved use case | Not needed by default; package generator optional | 12 | n/a |

## B. YouTube upload & metadata rules
Sources: [videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert), [videos resource](https://developers.google.com/youtube/v3/docs/videos), [revision history](https://developers.google.com/youtube/v3/revision_history)

| ✓ | Requirement | Compliance | Phase |
|---|---|---|---|
| ☐ | Explicit `privacyStatus` (omitted = public since 2 Nov 2026) | Invariant I-6, DB NOT NULL | 4/12 |
| ☐ | `publishAt` only with private & never-published; past time publishes immediately | Invariant I-8 (≥ now + 15 min) | 12 |
| ☐ | `containsSyntheticMedia` for realistic A/S content | Disclosure assessment + owner confirmation | 10/12 |
| ☐ | `selfDeclaredMadeForKids` decided by owner | NULL blocks upload | 10/12 |
| ☐ | Title ≤ 100 chars, description ≤ 5000 bytes, tags ≤ 500 chars, no `<` `>` | Validators + DB CHECKs | 10 |
| ☐ | Thumbnails JPEG/PNG ≤ 50 MB; verified channel | Checks; onboarding step | 10/4 |
| ☐ | Shorts ≤ 3 min, square/vertical | QC hard rule | 9 |

## C. YouTube Partner Program & Community Guidelines
Sources: [Channel monetization policies](https://support.google.com/youtube/answer/1311392), [Altered/synthetic disclosure](https://support.google.com/youtube/answer/14328491)

| ✓ | Requirement | Compliance | Phase |
|---|---|---|---|
| ☐ | Original, authentic; not mass-produced/repetitive ("inauthentic content") | Owner value-add, originality score, variety rules, caps, Policy Auditor | 7–11 |
| ☐ | Reused content needs significant original commentary | Stock-share rule, REUSED_CONTENT finding | 11 |
| ☐ | Community Guidelines | CG_RISK classifier + owner review | 11 |
| ☐ | Advertiser-friendly guidelines (informative) | ADVERTISER_RISK findings | 11 |
| ☐ | No misleading metadata/thumbnails | MISLEADING_METADATA, PROMISE_NOT_DELIVERED | 10/11 |
| ☐ | No impersonation; no cloning others' voices | NG-4, IMPERSONATION (non-overridable), owner-only clone | 8/11 |
| ☐ | No fake engagement | Non-goal; no such features | all |

## D. Google OAuth
Source: [OAuth 2.0 for Google APIs](https://developers.google.com/identity/protocols/oauth2), [Installed apps](https://developers.google.com/youtube/v3/guides/auth/installed-apps)

| ✓ | Requirement | Compliance | Phase |
|---|---|---|---|
| ☐ | Minimum scopes; incremental consent | Scope table (OAUTH_SECURITY §4.3) | 4 |
| ☐ | PKCE, loopback redirect, state check | Implemented | 4 |
| ☐ | Handle refresh-token expiry (Testing 7 days, 6-month unused, 100-token limit) | Token health job | 4 |
| ☐ | Consent screen info (app name, support email, privacy URL, home URL) | Onboarding step 6 | 4 |
| ☐ | Verification requirements for "In production" with sensitive scopes | Re-check at Phase 4 (🟡) | 4 |

## E. Licences (software, models, voices, media)
| ✓ | Requirement | Compliance | Phase |
|---|---|---|---|
| ☐ | Every dependency licence permissive or approved (no AGPL in network-facing code without approval; no non-commercial) | CI licence scan | 1 |
| ☐ | Every model/voice: licence + lineage + commercial flag in registry; NC blocked on monetised channels | Provider registry + Gateway rule | 5/8 |
| ☐ | Every media asset: rights record before render | Compiler refusal + Copyright audit | 8/9 |
| ☐ | Fonts: licensed list only (e.g. OFL Noto, Inter) | Font registry | 8/10 |
| ☐ | External editor library assets declared with licences | Declaration + BLOCKED_LIBRARY_ITEM | 9 |
| ☐ | Stock: licence proof kept; editorial-only blocked | asset_rights + audits | 8 |
| ☐ | Attribution text in description where required (CC-BY, Piper siwis, etc.) | ATTRIBUTION_MISSING check | 10/11 |

## F. Third-party service terms
| ✓ | Service | Key terms to respect | Phase |
|---|---|---|---|
| ☐ | Gemini API (free tier) | Free-tier content used to improve products; no sensitive data; no billing linked | 5 |
| ☐ | Groq | Account terms; rate limits | 5 |
| ☐ | Telegram Bot API | Rate limits; no spam | 14 |
| ☐ | Wikimedia APIs | User-Agent policy, rate limits (verify) | 6 |
| ☐ | Pexels / Pixabay | API terms (attribution, caching, no bulk) — verify | 8 |
| ☐ | GitHub (Actions, Pages) | Public repo free usage | 1/4 |

## G. Privacy & security (owner data)
| ✓ | Item | Phase |
|---|---|---|
| ☐ | Tokens/keys encrypted at rest; master key in Credential Manager | 3 |
| ☐ | Voice profiles encrypted, deletable, never sent to cloud | 8 |
| ☐ | Logs redacted | 1/3 |
| ☐ | Localhost-only binding | 1 |
| ☐ | Backups encrypted (secrets) and key export protected | 15 |
