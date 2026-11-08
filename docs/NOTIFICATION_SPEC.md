# Notification Specification

**Version:** 1.0 (approved at C5, 2026-11-08) · **Date:** 2026-11-08
**Agent:** A29 · **ADR:** 0014 · **State machine:** WORKFLOW_STATE_MACHINE §6 · **Tables:** notifications, notification_deliveries, notification_preferences, notification_targets

## 1. Channels
| Channel | Default | Cost | Setup |
|---|---|---|---|
| In-app (SSE + Notification Center) | Always on (cannot be disabled for CRITICAL) | Free | — |
| Telegram Bot API | On after setup (C0 default) | Free (verified: bots message users "at no cost"; ≈ 1 msg/s per chat) | Owner creates a bot with @BotFather, pastes the token, sends /start to the bot, and TubeForge captures the chat ID (verification code shown in the dashboard) |
| Email (SMTP) | Off | Free with the owner's mail provider | Host, port, TLS, user, password (encrypted), from, to |
| WhatsApp | **Disabled** (Tier P) | Paid (unverified) | Two-step paid activation required |

## 2. Event catalogue (event_type → default severity, channels, dedup window)

| Event type | Severity | Default channels | Dedup key / window |
|---|---|---|---|
| `niche.report_ready` (new channel opportunities) | INFO | in-app, digest | report_id / — |
| `trend.new` | INFO | in-app, daily digest | channel+topic / 24 h |
| `research.ready` | INFO | in-app | project / — |
| `script.ready` | INFO | in-app, Telegram | project+version / — |
| `render.finished` | INFO | in-app, Telegram | render_job / — |
| `render.failed` | WARNING | in-app, Telegram | render_job / — |
| `thumbnails.ready` | INFO | in-app | project / — |
| `audit.failed` (BLOCKED) | WARNING | in-app, Telegram | project+subject_sha / — |
| `approval.needed` | INFO | in-app, Telegram | approval_id / — |
| `upload.completed` | INFO | in-app, Telegram | upload_job / — |
| `video.published` | INFO | in-app, Telegram | video_id / — |
| `upload.failed` | WARNING | in-app, Telegram | upload_job+step / 1 h |
| `oauth.expiring` (Testing mode, < 24 h) | WARNING | in-app, Telegram | connection / 12 h |
| `oauth.revoked` / NEEDS_REAUTH | **CRITICAL** | in-app, Telegram, email (if on) | connection / 6 h |
| `quota.near_limit` (≥ 80 % any bucket) | WARNING | in-app | project+bucket+pt_day / 24 h |
| `quota.exhausted` | WARNING | in-app, Telegram | project+bucket+pt_day / 24 h |
| `usage.near_limit` (provider ≥ 80 %) | INFO | in-app | provider+period / 24 h |
| `usage.limit_reached` (provider paused) | WARNING | in-app, Telegram | provider+period / 24 h |
| `cost.paid_indicator` (possible charge) | **CRITICAL** | all enabled | provider / 6 h |
| `emergency_stop.activated` / cleared | **CRITICAL** | all enabled | timestamp / — |
| `security.event` (lockout, consent mismatch, chain broken) | WARNING/CRITICAL | in-app, Telegram | kind / 1 h |
| `deletion.deadline_risk` (DP-4 task due < 24 h) | **CRITICAL** | all | task / 6 h |
| `backup.failed` | WARNING | in-app, Telegram | day / 24 h |
| `disk.low` (D: < 15 % / < 10 %) | WARNING / CRITICAL | in-app, Telegram | level / 24 h |
| `provider.reverify_due` | INFO | in-app, weekly digest | provider / 7 d |
| `summary.daily` | INFO | Telegram or email | day |
| `summary.weekly` | INFO | Telegram or email | ISO week |

The owner can change channels and digest mode per event (`notification_preferences`), except that CRITICAL events always go in-app plus at least one other enabled channel.

## 3. Rules
- **Quiet hours:** 23:00–08:00 Asia/Karachi (system setting). Non-CRITICAL messages are DEFERRED to 08:00. CRITICAL messages bypass quiet hours.
- **Digests:** daily 09:00 PKT and weekly Monday 09:00 PKT (C4 default). They group by channel and project, max 30 lines, and link to the dashboard.
- **Dedup:** the same `dedup_key` within its window → SUPPRESSED (still counted in the in-app item as "×N").
- **Rate limits:** Telegram ≤ 1 msg/s per chat (queue spacing 1.1 s). Retries on 429 respect `retry_after`. 5 attempts with backoff 2^n × 5 s. After that → FAILED and fall back to in-app.
- **Content safety:** messages never include tokens, keys, full emails, file paths with user names, or comment text from viewers. Links point to `http://127.0.0.1:8765/...`, which only works on the owner's PC; this is stated in the bot's welcome message.
- **Delivery tracking:** `notification_deliveries` has a state per channel (CREATED → … → SENT/FAILED/READ).

## 4. Templates (examples, English UI)
```text
[TubeForge] ✅ Upload complete — "{title}" ({channel}) is {privacy}{schedule_part}. Open: {link}
[TubeForge] ⚠️ Approval needed — {subject_type} for "{title}" ({channel}). Open: {link}
[TubeForge] 🔴 Channel {channel} needs re-authorisation — uploads paused. Re-authorise: {link}
[TubeForge] Daily summary {date}: {n_published} published · {n_pending} approvals pending · quota {pct}% · free-tier peak {provider} {pct2}%
```

## 5. Acceptance tests (Phase 14)
- The same event twice within the window → one delivery.
- A non-critical event at 23:30 PKT → delivered at 08:00. A CRITICAL event is delivered immediately.
- Telegram 429 with retry_after=3 → retried after ≥ 3 s.
- A secret-bearing payload → redacted in the message text.
- Digest groups 50 events into ≤ 30 lines with a "+N more" line.
