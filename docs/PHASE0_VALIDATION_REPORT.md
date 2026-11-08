# Phase 0 — Validation Report (Step 2)

**Status:** Draft for Owner Checkpoint C0 · **Date:** 2026-11-08 · **Author:** Claude Code (planning mode)

This report reviews `docs/00_MASTER_PROMPT.md` and the owner's initial instructions. It covers gaps, conflicts, limits and risks to resolve during Phase 0. Items marked **[VERIFY 0.3]** will be checked against official sources in Step 0.3, with the URL and date recorded. Until then they are treated as `UNVERIFIED`.

---

## 1. Repository inspection

| Item | Finding |
|---|---|
| Working directory | Was empty. No existing code, no SEMRS OS artefacts, no dependencies. |
| Repo | New local git repo `tubeforge/` created (branch `main`). **No remote yet.** |
| Planning docs | One file: master prompt, saved as `docs/00_MASTER_PROMPT.md`. |
| Independence | Nothing to isolate from. TubeForge starts clean. |

> ⚠️ **This session runs in a temporary cloud container.** Unless the repo is pushed to a GitHub remote you own, the work here is lost when the session ends. **Owner action:** create an empty GitHub repo (e.g. `tubeforge`) and connect it to this session. See question Q8.

---

## 2. Conflicting or ambiguous specifications

| # | Conflict | Proposed resolution |
|---|---|---|
| C-1 | The owner's instructions say "implement the first approved development phase". The master prompt says Phase 0 is documents only, with no code before C6. | No phase is approved yet. The **first phase is Phase 0 (planning)**. No application code until C6. |
| C-2 | Phase 4 needs a "first private test upload". Phase 11 says a video that fails audit must not be uploadable. Phase 12 builds the uploader. | Phase 4 ships a **minimal uploader for the test channel only** (synthetic test file, private, flagged `is_test=true`). Phase 12 replaces it with the full audited upload pipeline. The audit gate becomes mandatory for all non-test uploads from Phase 11. |
| C-3 | OAuth-expiry and quota alerts are needed from Phase 4, but Notifications arrive in Phase 14. | Phase 4/5 send **in-app notifications only**, through a minimal notifications table. Phase 14 adds Telegram and email, plus digests and dedup. |
| C-4 | The Emergency Stop UI comes in Phase 2, its backend in Phase 3/5. | Phase 2 uses a mocked Emergency Stop. Phase 3 adds the `system_settings.emergency_stop` flag and API. Phase 5 makes workers honour it. |
| C-5 | Owner time is Asia/Karachi (default), but the YouTube quota resets at midnight **Pacific Time**. | Store all times in UTC. Show the quota-reset time in both the owner's timezone and PT. The quota ledger buckets by PT day. |
| C-6 | "Local-first" vs. the OAuth consent screen and compliance audit. Both need a **publicly reachable homepage and privacy policy**, and possibly a verified domain. | Host the static privacy policy and terms on a free static host (e.g. GitHub Pages). Whether Google accepts a `*.github.io` domain for verification is **[VERIFY 0.3]**. A custom domain costs money and needs owner approval. |
| C-7 | The 32 agents include **Comment Moderation (#28)** and **Keyword Research (#5)**, but no frontend section or roadmap phase covers comment moderation. | Add comment moderation to Phase 13 (read and suggest only, owner approves every action) and to the Growth Center UI. Needs a broader OAuth scope (`youtube.force-ssl`) **[VERIFY 0.3]**. Keyword Research belongs in Phase 6. |
| C-8 | Phase 2 requires all 31 routes. That is very large for one phase. | Keep all 31 routes as shells with four states and mocked data. Real functionality arrives in the phase that owns each feature. |
| C-9 | "Fully automatic" mode needs the YouTube audit to pass. The audit may not be granted to a single-owner internal tool. | Design for **Private-only mode as a permanent, supported way to run**, not a temporary state. Whether the audit is available to this use case is **[VERIFY 0.3]**. |
| C-10 | Frontend Next.js + FastAPI + Postgres + Redis/Valkey + Ollama + ComfyUI on a possible H0 (CPU, 16 GB) machine. | Evaluate a **Postgres-backed queue** (e.g. Procrastinate) to remove Redis/Valkey. Run heavy services (ComfyUI, the LLM) on demand, not always on. Decided in ADRs in Step 0.3. |

---

## 3. Missing requirements (to add to PRODUCT_REQUIREMENTS / specs)

1. **Disk and retention policy** — how long to keep raw assets, intermediate renders and final masters. Disk limits per channel. Cleanup rules. Long-form 1080p projects can take several GB each.
2. **Backup target and frequency** — local disk, external drive or a free cloud bucket. RPO/RTO targets.
3. **Languages and scripts** — if Urdu (RTL, Nastaliq), the specs need RTL text rendering in thumbnails and captions, font licensing (e.g. Noto Nastaliq Urdu, OFL), local TTS that supports Urdu (**[VERIFY 0.3]** — open TTS voices for Urdu may be limited), and Whisper accuracy for Urdu.
4. **Keyword / search-volume data** — no free official search-volume API is known. The spec must state what "keyword research" can honestly mean: YouTube autocomplete is unofficial and not allowed, `search.list` result counts are costly and approximate. Mark as limited.
5. **Prompt-injection defence** — research agents will read untrusted web, RSS and Reddit content and pass it to LLMs. This needs a sanitising and isolation policy (see Section 6).
6. **Legal identity for policy pages** — who is the "developer" named in the privacy policy and on the OAuth consent screen (person or company), plus a contact email.
7. **Revenue analytics** — monetary metrics need an extra Analytics scope (`yt-analytics-monetary.readonly`) **[VERIFY 0.3]**. Is it wanted?
8. **Accessibility target** for the dashboard (proposed: WCAG 2.2 AA).
9. **Remote access** — is the dashboard reachable only on `localhost`, on the LAN, or remotely (e.g. from a phone)? This changes the auth and TLS design.
10. **Model download budget** — first-run model downloads (LLM 4–20 GB, image model 2–12 GB) need disk space and bandwidth up front.
11. **Owner value-add capture** — the exact fields and minimum thresholds that count as "owner contribution" for the YPP originality defence.
12. **Definition of test channel** — a separate Google account/brand channel used only for staging uploads.

---

## 4. Free-tier limitations (preliminary — all [VERIFY 0.3])

| Area | Limitation | Design impact |
|---|---|---|
| YouTube Data API | 10,000 units/day per project. Worst-case upload ≈ 1,600 units, `thumbnails.set` ≈ 50, `captions.insert` ≈ 400, `search.list` = 100. | Worst case ≈ **4 full uploads/day** per Cloud project, with almost nothing left for research. The quota ledger reads costs from config. Research uses `videos.list` (mostPopular, 1 unit) and caching instead of `search.list`. |
| Unverified API project | Uploads are forced to private (F1). | Private-only mode is the default. The owner makes videos public in Studio. |
| OAuth "Testing" status | Refresh tokens expire after about 7 days (F6). | Weekly re-auth prompt, detected before failure. Plan to move to "In production". |
| Free cloud LLM tiers | Rate- and day-limited. Some may use prompts for training. Terms change often. | Local Ollama is primary. Cloud free tiers are opt-in, carry data-use labels and are blocked by default for sensitive content. |
| Generative video | No reliable free long-form generative video. | Adapter only, disabled. Default styles: motion graphics, Ken Burns, kinetic text, data visuals, owner footage. |
| Image models | Some (e.g. certain FLUX variants) are non-commercial. | The provider registry blocks non-commercial licences for monetised channels. |
| WhatsApp | Business-initiated messages are paid. | Disabled adapter. Telegram + SMTP + in-app are the defaults. |
| Email (SMTP) | Free providers cap daily sends and may block automated mail. | Digest mode. Telegram preferred. |
| GitHub Actions | Free minutes are limited for private repos. | Lightweight CI with mocked providers. GPU tests run locally only. |
| Google Trends | No generally available free official API (F9). | Not a dependency. Use Wikipedia pageviews, RSS, `videos.list` charts, and Reddit only if its terms allow. |

---

## 5. Technical dependencies and hardware requirements

**Hard dependencies:** FFmpeg/ffprobe, PostgreSQL, Python 3.12+, Node.js LTS, Ollama (or llama.cpp), a Google Cloud project with YouTube Data API v3 and the Analytics API enabled, an OAuth client, and a test YouTube channel.

**Optional / profile-dependent:** ComfyUI or diffusers (images), Piper/Kokoro (TTS), faster-whisper (STT), Redis/Valkey (only if the queue ADR picks them), Docker Desktop.

| Profile | Est. disk needed | Notes |
|---|---|---|
| H0 (CPU, 16 GB) | ~60–100 GB free | 3–4B LLM at Q4 is slow. Image generation is slow (minutes per image) or uses a free-tier API. Rendering is fine, but 1080p long-form may take a long time. |
| H1 (8 GB VRAM) | ~100–150 GB | 7–8B LLM, SD1.5/SDXL-class images. Workable. |
| H2 (12–24 GB VRAM) | ~150–250 GB | Comfortable. Larger models. |

RAM contention matters: an LLM, an image model and Postgres running at the same time on 16 GB will swap. The orchestrator needs a **resource scheduler** (one GPU-heavy job at a time, model unload between stages).

---

## 6. Security risks

| Risk | Mitigation (to specify in OAUTH_SECURITY.md) |
|---|---|
| OAuth refresh-token theft (full channel takeover) | AES-GCM encryption at rest. Key held in the OS keyring, not in `.env`. Minimum scopes. Revoke on disconnect. |
| Dashboard exposed on LAN/internet | Bind to `127.0.0.1` by default. Argon2 + TOTP. CSRF protection. Secure cookies. TLS if remote access is enabled. |
| Prompt injection from research sources | Treat fetched content as data. Strip instructions. Agents get no tool access while handling untrusted text. Auditors are independent. Agents cannot trigger upload or publish. |
| Malicious model files / ComfyUI custom nodes | safetensors only. Hash-pinned model registry. No arbitrary custom nodes without owner approval. |
| SSRF / malicious URLs in research fetcher | Allowlist of source domains. Block private IP ranges. Size and time limits. |
| Supply chain (npm/PyPI) | Lockfiles, `pip-audit`/`npm audit` in CI, secret scanning, pre-commit hooks. |
| Accidental paid usage | Paid adapters are disabled at the code level. Two-step activation. Billing never configured. Cost dashboard. |
| Notification bot tokens leaked | Encrypted secrets store. Redact in logs. |
| Data isolation across channels | `channel_id` scoping on every query. Authorization tests per channel. |

---

## 7. YouTube API restrictions (summary — all [VERIFY 0.3])

1. Uploads from unverified projects are **private-only** until the compliance audit passes (F1).
2. Quota is 10,000 units/day. Upload cost is unclear in the docs (F2). Plan for the worst case.
3. `publishAt` only works with `privacyStatus=private` (F5). In practice, scheduled public release needs the audit.
4. `containsSyntheticMedia` must be set explicitly on every upload (F4).
5. No API for creating channels. Onboarding is manual (non-goal confirmed).
6. Developer Policies limit how long API data may be stored and require refresh/deletion. Analytics snapshots and competitor metadata need a retention job **[VERIFY 0.3]**.
7. Custom thumbnails need a verified channel (phone verification) and have size/format limits **[VERIFY 0.3]**.
8. Shorts: vertical, maximum length **[VERIFY 0.3]** (believed to be 3 minutes since late 2024).
9. Made-for-kids (`selfDeclaredMadeForKids`) is always the owner's decision.
10. Competitor research is limited to public metadata through the API, at quota cost. No scraping, no downloads.

---

## 8. Business / policy risk (top item for RISK_REGISTER)

**YPP "inauthentic / mass-produced content" (F3)** is the main threat to the product's goal. A pipeline that turns out templated narrated slideshows is likely to be refused monetisation, whatever the software quality. The design responses (originality scoring, publishing caps, owner value-add fields, owner-voice option, Policy Auditor blocking) are **core features, not extras**. Whether the owner will record their own voice or appear on camera (Q4) is the most important input to this risk.

---

## 9. Unresolved decisions (owner input needed)

Discovery questions Q1–Q7 from Step 0.1 come first. The other decisions are listed in `PROJECT_PROGRESS.md` → *Open decisions*. They are mostly technology ADRs for Step 0.3, which need the C0 answers, chiefly about hardware and OS.

---

## 10. C0 update — owner hardware and language answers (2026-11-08)

**Owner answers:** Windows 10 · 8 GB RAM · no GPU · languages English, Spanish, French, German, Urdu · timezone Asia/Karachi.

### 10.1 New hardware profile: **H-LITE** (below the brief's H0)

The brief's lowest profile (H0) assumed 16 GB RAM. With 8 GB, Windows 10 already uses about 3–4 GB, which leaves roughly **4 GB for TubeForge**.

| Capability | Feasible locally on H-LITE? | Plan |
|---|---|---|
| Rendering (FFmpeg, CPU x264) | ✅ Yes, slow | 1080p30 long-form renders take a long time. Default to 720p/1080p with a `veryfast`/`faster` preset, render overnight, and use low-res proxy previews. |
| Database (PostgreSQL native) | ✅ Yes | About 150–300 MB with tuned settings. |
| Job queue | ✅ Yes, if Postgres-backed | Avoid a separate Redis/Valkey process. This makes **ADR D-1 lean toward Procrastinate or a custom Postgres queue**. |
| Dashboard | ✅ Yes | Prefer a static-built React SPA (Vite) served by FastAPI. That avoids a resident Node/Next.js server. **D-3 leans to Vite + React.** |
| Docker | ⚠️ Not recommended | Docker Desktop's WSL2 VM takes 2+ GB. Make the **native Windows install primary** and keep Docker for CI/dev only. |
| Local LLM | ⚠️ Very limited | Only ~1–3B models at Q4 (~1–2.5 GB). They're too weak for good multilingual scripts. Use them only for small tasks (classification, JSON repair, offline fallback). |
| Main LLM work (research, scripts, translation) | ➡️ Free-tier cloud | Use Gemini/Groq/Mistral/OpenRouter free tiers through the Gateway. Hard local limits, plus labels for data-use and training terms. **[VERIFY 0.3]** |
| Image generation | ❌ Not practical locally | SD-class models on CPU with 4 GB of headroom would run out of memory or take many minutes per image. Use free-tier image APIs only where the licence allows monetised use; otherwise use non-generative visuals: procedural graphics, charts, kinetic text, owner photos, CC0/public-domain libraries with rights records. |
| TTS | ✅ Partly | Piper runs well on CPU. EN/ES/FR/DE voices are believed available; **Urdu voice availability is [VERIFY 0.3]**. Check every voice's licence. |
| STT / subtitles | ✅ Yes | faster-whisper `base`/`small` int8 on CPU. Urdu accuracy is lower, so the owner reviews Urdu captions. |
| Concurrency | ⚠️ One heavy job at a time | The resource scheduler is mandatory: render, STT and LLM never run in parallel. |

**Consequence:** on this machine TubeForge is a **hybrid**: the orchestration, database, rendering, TTS and STT run locally, and the heavy AI text and images use free-tier cloud services. Daily output is capped by free-tier limits *and* CPU time. That suits the quality-over-volume principle. Upgrading to 16 GB RAM would help a lot. That is a one-time hardware cost and entirely the owner's choice; it is not required.

### 10.2 Windows 10 end of support — security risk

Microsoft ended Windows 10 support on 14 Oct 2025. As far as I know, the consumer Extended Security Updates programme ran only until Oct 2026 **[VERIFY 0.3]**. An unpatched OS that stores YouTube OAuth tokens raises the risk of account takeover. Options for the owner:

1. Free upgrade to Windows 11, if the PC meets its requirements.
2. Run TubeForge on a free Linux install.
3. Accept the risk: localhost-only binding, an encrypted token store, an up-to-date browser and antivirus. Recorded in RISK_REGISTER.

### 10.3 Five languages

- **One content language per channel** (a channel field). The UI starts in English, with i18n-ready strings.
- Urdu needs RTL layout in thumbnails and captions, Nastaliq fonts (Noto Nastaliq Urdu, OFL licence) and an Urdu TTS check. **Urdu is the hardest of the five and is flagged high-risk for local quality.**
- Recommended rollout: launch **one channel in one language** in Phase 16, then expand.
- Translating a video into another language is not original content by default. The Policy Auditor treats near-duplicate translated catalogues as a repetition risk, unless the owner adds language-specific value.
