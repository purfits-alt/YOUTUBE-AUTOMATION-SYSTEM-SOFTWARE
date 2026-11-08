# Audit & Policy Specification

**Version:** 0.1 (Step 0.6, for Checkpoint C5) · **Date:** 2026-11-08
**Auditor agents:** A21 Copyright · A22 YouTube Policy · A23 Video Quality · A30 Security · A31 System · A32 Free-Tier Cost & Usage
**Policy sources (verified 2026-11-08):** [YouTube channel monetization policies](https://support.google.com/youtube/answer/1311392) · [Disclosure of altered/synthetic content](https://support.google.com/youtube/answer/14328491) · [YouTube API Developer Policies](https://developers.google.com/youtube/terms/developer-policies)

## 1. Report format (every audit)
```json
{"audit_type":"CONTENT|COPYRIGHT|POLICY|QUALITY|THUMBNAIL|SECURITY|SYSTEM|COST",
 "subject_sha256":"…", "result":"PASSED|WARNING|FAILED", "critical":false, "score":0-100,
 "findings":[{"code":"…","severity":"INFO|WARNING|CRITICAL","message":"…",
   "affected_component":"SCRIPT|METADATA|THUMBNAIL|VIDEO|AUDIO|ASSET|CHANNEL|AGENT|PROVIDER|SYSTEM",
   "responsible_agent":"A11|…|OWNER|EXTERNAL_EDIT","evidence":"…","remediation":"…"}]}
```
`result` = FAILED if any CRITICAL finding, or score < the channel threshold. WARNING if any WARNING finding. Otherwise PASSED.

## 2. Pre-upload audits (run in QC_AUDIT; all must be PASSED/WARNING or overridden)

### 2.1 Content audit (A22 content part + deterministic metrics) — threshold `min_audit_scores.content` (default 70)
| Code | Rule | Severity |
|---|---|---|
| FACT_CONTRADICTED | Any CONTRADICTED claim without owner override | CRITICAL |
| FACT_UNSUPPORTED_HIGH | > 20 % of factual claims UNSUPPORTED | WARNING |
| VALUE_ADD_MISSING | Owner value-add score = 0 | WARNING (CRITICAL in SEMI/FULLY-AUTO) |
| ORIGINALITY_LOW | Originality score < `min_originality_score` (default 70) | FAILED (score-based) |
| CATALOGUE_REPETITION | Script embedding similarity to any of the channel's last 20 videos > 0.85 | WARNING; > 0.92 CRITICAL |
| VIEWER_VALUE_LOW | Classifier: no educational, entertainment or narrative value | WARNING |

**Originality score (0–100)** = 30 × owner_value_add_norm + 20 × voice_factor (owner recording 1.0, owner clone 0.8, TTS 0.4) + 20 × (1 − max_similarity_last20) + 15 × visual_variety (1 − template reuse share) + 15 × (1 − stock_runtime_share above the 60 % threshold, scaled).

### 2.2 Copyright audit (A21) — deterministic
| Code | Rule | Severity | Overridable |
|---|---|---|---|
| RIGHTS_MISSING | Any asset in the cut without a rights record | CRITICAL | **No** |
| LICENCE_NONCOMMERCIAL | `commercial_use_allowed=false` on a monetised channel | CRITICAL | **No** |
| EDITORIAL_ONLY | Editorial licence on a monetised channel | CRITICAL | **No** |
| ATTRIBUTION_MISSING | `attribution_required` but the text is not in the description | CRITICAL | No (fix by adding it) |
| PAID_PROOF_MISSING | Paid stock or manual import without licence proof | WARNING | Yes |
| BLOCKED_LIBRARY_ITEM | External-edit declaration lists CapCut library music, Canva Popular Music or another flagged library without proof | CRITICAL | Only with proof attached |
| VOICE_CONSENT_MISSING | OWNER_CLONE narration without a READY consent | CRITICAL | **No** |
| TTS_VOICE_LICENCE | TTS voice registry commercial ≠ YES on a monetised channel | CRITICAL | No |
| MUSIC_UNKNOWN | Music asset with rights basis unknown | CRITICAL | No |
| THIRD_PARTY_VIDEO | Asset origin indicates a YouTube download (impossible by design; defensive) | CRITICAL | No |

### 2.3 YouTube Policy audit (A22) — threshold `min_audit_scores.policy` (default 80)
| Code | Rule (source) | Severity |
|---|---|---|
| INAUTHENTIC_TEMPLATE | Template-like video per YPP examples: slideshow/scrolling text with minimal narrative; generic AI template without owner insight; channel template reuse > 70 % | WARNING; CRITICAL if `block_high_inauthentic_risk` applies (always in SEMI/FULLY-AUTO; owner choice in MANUAL — OQ-4) |
| REUSED_CONTENT | Third-party material without significant commentary (stock share > 60 % runtime with no owner narration or commentary) | WARNING |
| MISLEADING_METADATA | Title/thumbnail claims not supported by content; deceptive patterns | CRITICAL |
| DISCLOSURE_MISSING | Realistic synthetic content present and `containsSyntheticMedia=false` | CRITICAL (override with reason) |
| IMPERSONATION | Content presents a real person saying or doing things they didn't | CRITICAL (no override) |
| CG_RISK | Community Guidelines red flags (harassment, hate, dangerous acts, medical misinformation, spam, scams) | CRITICAL for severe categories, else WARNING |
| ADVERTISER_RISK | Advertiser-unfriendly themes (strong language, violence, controversial issues) — informs, doesn't block | INFO/WARNING |
| MADE_FOR_KIDS_UNSET | Owner hasn't decided | CRITICAL (fix: decide) |
| CAP_EXCEEDED | Publishing would exceed channel caps | CRITICAL (fix: reschedule) |

### 2.4 Video quality audit (A23) — threshold `min_audit_scores.quality` (default 75)
Checks per VIDEO_PRODUCTION_SPEC §8. Corrupt or unreadable file, missing audio, or a Short > 180 s or wrong aspect → CRITICAL (no override). Loudness out of range, black/freeze/silence anomalies, caption drift → WARNING with an auto-fix loop (max 2).

### 2.5 Thumbnail audit (A22/A18 checks) — threshold `min_audit_scores.thumbnail` (default 70)
Checks per THUMBNAIL_SEO_SPEC §1.3. Wrong size or format → CRITICAL (fix). Misleading → CRITICAL. Low contrast or readability → WARNING.

## 3. Continuous audits
| Audit | Agent | Schedule | Checks | Output |
|---|---|---|---|---|
| AI agents | A31 | hourly | permission violations (attempts denied by guards), failure rate > 20 %/24 h, repair rate > 30 %, usage spikes > 3× 7-day median, stuck jobs > 2× expected runtime, audit-log hash chain | notifications + `security_events` |
| Security | A30 | daily 07:00 PKT | TOTP status, lockouts, keyring access, token health and expiry, backups age (< 48 h), restore test age (< 30 d), last dependency audit, gitleaks status, outbound-block count, Windows update hint | posture report (Audit & Security Center) |
| Cost | A32 | on every usage event + hourly | free-tier usage vs limits (70/90/100 %), paid indicators, budgets, quota forecast, re-verification due | provider auto-pause + alerts |

## 4. Blocking & overrides
- Any CRITICAL finding → project `BLOCKED` (WORKFLOW_STATE_MACHINE §3). The upload client re-checks independently (invariant I-4).
- **Override:** owner only, reason ≥ 20 chars, re-authentication required, stored in `audit_overrides` (append-only), visible in Copyright & Policy Center and the audit log.
- **Never overridable:** RIGHTS_MISSING, LICENCE_NONCOMMERCIAL, EDITORIAL_ONLY, VOICE_CONSENT_MISSING, TTS_VOICE_LICENCE, MUSIC_UNKNOWN, THIRD_PARTY_VIDEO, IMPERSONATION, corrupt file, Shorts duration/aspect.
- Any change to the audited subject (render, metadata, thumbnail) changes `subject_sha256`, so audits re-run and approvals are invalidated.
- Thresholds are configurable per channel (Publishing rules) within floors: content ≥ 50, policy ≥ 60, quality ≥ 50, thumbnail ≥ 50.

## 5. Independence guarantees
1. Auditor code lives in a separate package (`workers/tubeforge_auditors`). Production agents import nothing from it, and vice versa (import-lint).
2. DB role `tf_auditor` is the only role with INSERT on `audit_reports`. The worker uses it only inside auditor tasks.
3. Auditor prompts get production-agent notes as untrusted input.
4. Auditor agents cannot be disabled via API (only paused through a kill switch with a reason → projects needing that audit wait).

## 6. Acceptance tests (Phase 11)
- **Blocked video cannot upload:** for each non-overridable code, a fixture project → every API path to upload returns 422 `AUDIT_BLOCKED` or the preflight refuses.
- Override flow: reason < 20 → 400; no re-auth → 403 `REAUTH_REQUIRED`; success → audit row + override row + upload allowed.
- F3 example fixtures (slideshow with no narration, templated AI script, reused stock montage) → INAUTHENTIC/REUSED findings.
- Changing the selected thumbnail after approval → approval INVALIDATED.
