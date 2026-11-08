# Free-Tier Provider Matrix & Platform Fact Verification

**Version:** 0.1 (Step 0.3, for Checkpoint C2) · **Verification date for all entries:** 2026-11-08 unless stated otherwise
**Method:** official pages were fetched directly. Sources marked *(secondary)* are reputable news or third-party pages, used only where the official page could not be reached from this environment.

> **Status legend:**
> ✅ VERIFIED (official source) · 🟡 PARTIAL (secondary sources only, or official page ambiguous) · ❌ UNVERIFIED · ⛔ NOT FREE

This file is the seed data for the **Provider Registry** table (Phase 5). Each row becomes a registry record. Every record must be re-verified at least every **90 days**, and the dashboard shows a "re-verify" badge once that is due.

---

## 1. Platform facts F1–F9 from the master prompt

| # | Brief said | Verified finding (2026-11-08) | Status | Source | Design consequence |
|---|---|---|---|---|---|
| **F1** | Uploads from unverified API projects (created after 28 Jul 2020) are forced private until an audit passes | **REVERSED on 2 Nov 2026.** "Videos uploaded through the videos.insert method from unverified API projects are **no longer restricted to private viewing mode**." Also: if `status.privacyStatus` is omitted, **the video defaults to `public`**. | ✅ | [Revision history, 2 Nov 2026](https://developers.google.com/youtube/v3/revision_history); [videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert) (page updated 2026-11-03) | No audit needed to publish publicly. **But the risk now runs the other way:** a missing `privacyStatus` makes a video public immediately. "Never set privacy implicitly" becomes a hard invariant, enforced in code and tests. Private-only mode stays as an owner-selectable *safety* mode and is no longer a platform limit. See ADR-0016. |
| **F2** | 10,000 units/day; upload cost unclear (1,600 vs. separate bucket) | **Granular quota since 1 Jun 2026.** Defaults per project per day: **100 `videos.insert` calls** (1 unit each, own bucket), **100 `search.list` calls** (1 unit each, own bucket), **10,000 units** shared by all other methods. Resets at midnight Pacific Time. Other costs: `thumbnails.set` ≈ 50, `captions.insert` 400, `captions.update` 450, `captions.list` 50, `videos.update` 50, `videos.list` 1, `channels.list` 1, `playlistItems.insert` 50, `commentThreads.list` 1, `comments.insert` 50. Invalid requests still cost ≥ 1. | ✅ | [Quota calculator](https://developers.google.com/youtube/v3/determine_quota_cost) (updated 2026-11-03); [revision history 1 Jun 2026, 4 Dec 2025](https://developers.google.com/youtube/v3/revision_history) | Uploads are **no longer the bottleneck**. A full publish (insert + thumbnail + captions + playlist) costs ≈ 500 units from the shared pool, so ~18/day fit with headroom. `search.list` is capped at **100 calls/day**, which is now the scarce research resource. The ledger tracks **three buckets** separately, with costs read from config. |
| **F3** | YPP treats mass-produced / repetitive "inauthentic" content as ineligible | Confirmed. Policy update dated **15 Jul 2025** renamed "repetitious" to "inauthentic". The examples that are *not allowed* explicitly include "Image slideshows, templated storylines, or scrolling text with minimal or no narrative, commentary, or educational value" and "**AI-generated content made with generic or unoriginal templates giving the impression of mass production without adding the creator's original, authentic insights or perspective**". Reviewers look at the channel's main theme, most-viewed videos, newest videos, metadata and About section. The policy applies to the **whole channel**. | ✅ | [YouTube channel monetization policies](https://support.google.com/youtube/answer/1311392) | Strongly confirms the "owner-directed, quality-first" design. The Policy Auditor's rule set is built directly from these listed examples. Owner value-add stays mandatory. Because the rule is channel-level, the repetition guard looks at the **catalogue**, not just single videos. |
| **F4** | `status.containsSyntheticMedia` exists (added 30 Oct 2024) | Confirmed, added **30 Oct 2024**. It is for *realistic* altered or synthetic content: making a real person appear to say or do something, altering footage of real events or places, or generating a realistic-looking scene that didn't happen. It can be set on `videos.insert` and `videos.update`. | ✅ | [Revision history, 30 Oct 2024](https://developers.google.com/youtube/v3/revision_history) | The AI-disclosure assessment uses **YouTube's definition** (realism), not "was any AI used". Motion graphics and TTS narration are usually `false`; realistic generated scenes are `true`. The value is always sent explicitly, with the reasoning logged. |
| **F5** | `publishAt` only while `private` | ✅ Confirmed: "It can be set only if the privacy status of the video is private" and "only … if the video has never been published". When used with `videos.update`, `privacyStatus` must also be sent as `private`. ⚠️ **A `publishAt` in the past publishes the video immediately** (same as switching to public). | ✅ | [videos resource — status.publishAt](https://developers.google.com/youtube/v3/docs/videos) | Scheduler uploads `private` + `publishAt`. New guard: `publishAt` must be ≥ now + 15 min at send time, otherwise the upload is refused and the owner is asked to pick a new time. No audit needed (F1 reversed). |
| **F6** | Testing-mode OAuth refresh tokens expire after ~7 days | Confirmed: "A Google Cloud Platform project with an OAuth consent screen configured for an external user type and a publishing status of 'Testing' is issued a refresh token expiring in 7 days." Also: a token unused for **6 months** expires. There is a limit of **100 refresh tokens per Google Account per client ID** (the oldest is silently invalidated). | ✅ | [Google OAuth 2.0 overview — Refresh token expiration](https://developers.google.com/identity/protocols/oauth2) | Token-health monitor. Re-auth flow. Never mint tokens in a loop (that would hit the 100-token limit). DEPLOYMENT_GUIDE covers moving the consent screen to "In production". |
| **F7** | WhatsApp business messaging is not free | Not re-verified (Meta pages are not on the network allowlist). The adapter stays **disabled**, so nothing depends on this. | ❌ | — | No change. Telegram is confirmed free (see §3). |
| **F8** | Some "open" models are non-commercial | Confirmed in practice: several **Piper voices are CC BY-NC-SA 4.0** (e.g. `en_US-ryan-high`, `en_US-hfc_female-medium`). Many English Piper voices are fine-tuned from `lessac`, whose dataset uses a Blizzard Challenge licence. The FLUX.1-schnell model card is gated (couldn't read it without login). | ✅ (Piper) / ❌ (FLUX) | [rhasspy/piper-voices model cards](https://huggingface.co/rhasspy/piper-voices) | Licence checks happen **per voice and per model**, not per engine. The registry stores a licence *and* a lineage ("fine-tuned from"). Lessac-derived voices are flagged `REQUIRES REVIEW`. |
| **F9** | No generally available official Google Trends API | The **Google Trends API is in alpha**. Google is "accepting applications for alpha testers", with a rolling 5-year data window. | ✅ | [Google Trends API alpha](https://developers.google.com/search/apis/trends) | Optional adapter, used only if the owner applies and is accepted. Not a dependency. Scraping Trends stays forbidden. |

---

## 2. NEW compliance findings (not in the brief): YouTube Developer Policies

Source: [YouTube API Services Developer Policies](https://developers.google.com/youtube/terms/developer-policies) (page updated 2026-11-06). ✅

| ID | Rule (quoted or paraphrased closely) | Impact on TubeForge |
|---|---|---|
| **DP-1 Data aggregation** | "**Do not aggregate API Data** except … API Data relating to YouTube channels that are under the same content owner …" and "Do not aggregate API Data or otherwise use API Data or YouTube API Services **to gain insights into YouTube's usage, revenue, or any other aspects of YouTube's business**." | ⚠️ **Conflicts with master prompt §8 (competitor patterns, niche scoring from YouTube data).** Cross-channel competitor aggregation and niche scoring built from YouTube API data are **not allowed**. See ADR-0015. |
| **DP-2 Storage of non-authorized data** | Non-authorized data (e.g. other channels' public stats) may be stored for "not longer than **30 calendar days**", after which it must be deleted or refreshed. The subscriber count of a channel you don't own must not be stored > 30 days. | Retention job. Every stored API record has a `fetched_at` and an `expires_at` (≤ 30 days). |
| **DP-3 Storage of authorized data** | The owner's own Analytics/Reporting data and statistics may be stored "for as long as is necessary", but the client "must still ensure **every 30 days** that it is still authorized" and that the video still exists. | A 30-day re-authorization and existence check is needed for analytics snapshots. |
| **DP-4 Revocation and deletion** | When a user revokes consent, the client must delete Authorized Data within **7 calendar days** (through the client) or **30 days** (through the Google security page). A deletion function must exist for the user. | A "Disconnect & delete data" action with a deadline monitor. |
| **DP-5 Privacy policy** | Required before use. It must link to the Google Privacy Policy, explain what data is accessed, stored and used, and mention revocation through `https://security.google.com/settings/security/permissions`. | Privacy policy template (Phase 4). The owner hosts it. |
| **DP-6 Explicit consent for actions** | Clients must "clearly identify any actions that they take to insert, share, update, or delete data … and the user must **expressly consent** to those actions prior to their actual execution." | Matches the owner-approval design. FULLY-AUTOMATIC mode needs a recorded, scoped consent ("auto-publish rules") that the owner has explicitly accepted. |
| **DP-7 No audiovisual copies** | Must not "download, import, backup, cache, or store copies of YouTube audiovisual content" without written approval. | Confirms the no-download rule. The backup feature backs up **our own masters**, never files fetched from YouTube. |
| **DP-8 No scraping** | Must not scrape YouTube or Google applications, or obtain scraped data. | Confirms the no-scraping rule. A CI test blocks HTTP clients aimed at YouTube HTML pages. |
| **DP-9 Inactivity** | Access or quota may be curtailed after **90 consecutive days** of project inactivity. | A health check warns when 60 days pass with no API calls. |
| **DP-10 Quota extension** | Request it through an API Compliance Audit that states the use case. Extra quota may be used only for the approved use case. | Probably not needed (see F2). The audit package stays in the roadmap as optional. |

---

## 3. Provider matrix

Tier: **L** local · **F** permanent free cloud tier · **P** paid / trial (disabled).
"Data use" = whether the provider may use our prompts or content to train or improve its products.

### 3.1 YouTube & Google

| Provider | Tier | Free limits | Licence / terms | Commercial use | Data use | Status |
|---|---|---|---|---|---|---|
| YouTube Data API v3 | F | 100 uploads + 100 searches + 10,000 units / day / project | YouTube API ToS + Developer Policies | Yes (within policies) | n/a | ✅ |
| YouTube Analytics API | F | Shared project quota (verify in 0.5) | Same | Yes | n/a | 🟡 |
| Google OAuth 2.0 | F | 100 refresh tokens / account / client | Google API ToS | Yes | n/a | ✅ |
| Google Trends API (alpha) | F? | Alpha, allowlisted | Alpha terms | Unknown | Unknown | 🟡 optional, needs owner application |

### 3.2 LLM (text)

| Provider / model | Tier | Free limits | Licence / terms | Commercial | Data use | Status |
|---|---|---|---|---|---|---|
| **Gemini API free tier**: Gemini 3.8 Flash, 3.6 Flash, 3.5 Flash-Lite, 3.1 Flash-Lite, 2.5 Flash, 2.5 Pro, Gemma 4 (hosted) | F | **Per project. Exact RPM/RPD shown only in AI Studio** for the owner's project. RPD resets at midnight PT. | Gemini API terms | Output usable (re-check terms) | ⚠️ **Free tier: "Content used to improve our products"** | ✅ free status / 🟡 limits |
| Gemini 4 Argon, 3.1 Pro Preview, Omni Flash | ⛔ P | Not on free tier | — | — | — | ⛔ blocked |
| **Groq free plan**: gpt-oss-120b, gpt-oss-20b, qwen3.8-27b | F | Docs list 30 RPM / 1K RPD / 8K TPM / 200K TPD per model, but the page says these are "base limits for the Developer plan". **Exact free limits only in the console.** | Groq terms | Check | Unknown | 🟡 |
| **Ollama** runtime | L | Hardware only | MIT | Yes | Local, nothing leaves the PC | ✅ |
| Local small model (≤ 3B, Q4) via Ollama | L | ~1.5–2.5 GB RAM | Per model: Apache-2.0 / MIT preferred | Per model | Local | ❌ model chosen in Phase 5 |
| Mistral free tier, OpenRouter free models | F? | — | — | — | — | ❌ not evaluated (host not allowlisted). Kept as future candidates. |

> ⚠️ **Billing trap (Gemini):** linking a billing account to a Google Cloud project **automatically moves it to a paid tier** (Tier 1), and paid tiers then auto-upgrade with spending. **Rule:** the Gemini API key comes from a dedicated Google Cloud project that **never** has billing linked. The YouTube project also has no billing. The setup guide states this in bold.

### 3.3 Speech

| Provider / model | Tier | Languages | Licence | Commercial | Status |
|---|---|---|---|---|---|
| **Kokoro-82M** | L | EN (US/GB), **ES, FR**, HI, IT, JA, PT-BR, ZH. **No DE, no UR.** | **Apache-2.0** | Yes | ✅ |
| **Piper**: `de_DE-thorsten-*` | L | DE | Dataset **CC0** | Yes | ✅ |
| **Piper**: `es_ES-davefx-medium` | L | ES | CC0 | Yes | ✅ |
| **Piper**: `fr_FR-siwis-medium` | L | FR | CC-BY 4.0 (attribution) | Yes, with attribution | ✅ |
| **Piper**: `ur_PK-fasih-medium`, `ur_PK-aegis_female-medium` | L | **UR** | Model card says **MIT** (v2, Oct 2026). A third-party site lists one as non-commercial (conflict). | Probably yes | 🟡 owner should listen and check before use |
| **Piper**: `en_US-joe-medium` | L | EN | CC0 dataset, **but fine-tuned from lessac** | Needs review | 🟡 |
| **Piper**: `en_US-ryan-high`, `en_US-hfc_female-medium` | L | EN | **CC BY-NC-SA 4.0** | **No** | ⛔ blocked for monetised channels |
| Piper engine (`OHF-Voice/piper1-gpl`) | L | — | **GPL-3.0** (engine) | Yes. Run as a separate process; no code linking. | 🟡 |
| Gemini TTS (3.8 Flash TTS, 3.8 Flash-Lite TTS) free tier | F | Multilingual (verify UR/DE in Phase 8) | Gemini terms | Check | ⚠️ data used to improve products | 🟡 optional fallback |
| **faster-whisper** (STT) | L | Multilingual incl. UR (lower accuracy) | MIT (engine), Whisper weights MIT | Yes | ✅ (well-known; LICENSE re-check in Phase 8) |
| Groq whisper-large-v3(-turbo) | F | Multilingual | Groq terms | Check | 🟡 optional fallback |
| **Owner's own voice** | L | Any | Owner-owned | Yes | ✅ **recommended** |

### 3.3a Owner voice cloning (ADR-0019, added at C2)

| Engine | Tier | Languages | Licence | Commercial | Notes | Status |
|---|---|---|---|---|---|---|
| **OpenVoice V2** tone-colour converter (on top of Kokoro/Piper) | L | Any TTS input language (native base: EN, ES, FR, ZH, JA, KO) | **MIT** ("Free for commercial use", since Apr 2024) | Yes | Light on CPU. Default clone engine. | ✅ code licence · 🟡 weights re-check Phase 8 |
| **Chatterbox Multilingual V3** | L | 23 langs incl. **EN, ES, FR, DE**, HI. **No UR.** | **MIT** | Yes | 0.5B. Slow on CPU. Built-in PerTh watermark. Repo archived (frozen). | ✅ code licence · 🟡 weights re-check Phase 8 |
| Paid cloud cloning (e.g. ElevenLabs) | P | — | — | — | Adapter slot only, disabled | ⛔ |
| **YouTube disclosure rule** | — | — | — | — | "Cloning one's own voice to create voice overs or dubs" is listed under content creators **don't have to disclose** | ✅ [YouTube Help 14328491](https://support.google.com/youtube/answer/14328491) |

### 3.4 Images & video

| Provider | Tier | Licence | Commercial | Status |
|---|---|---|---|---|
| Procedural / Pillow / FFmpeg / matplotlib graphics | L | Open source | Yes | ✅ default |
| Owner photos and footage | L | Owner | Yes | ✅ |
| CC0 / public-domain libraries (source chosen per asset, rights recorded) | — | CC0 / PD | Yes | 🟡 per asset |
| Gemini image models ("Nano Banana" family) | ⛔ P | — | — | ⛔ **not on free tier** |
| Local Stable Diffusion / FLUX on H-LITE | L | Varies (some non-commercial) | Varies | ⛔ not feasible on 8 GB CPU |
| Free-tier cloud image APIs (e.g. Cloudflare Workers AI, Hugging Face) | F? | Model-dependent | Model-dependent | ❌ evaluate in Phase 8 (hosts not allowlisted) |
| Generative video | P | — | — | ⛔ adapter only, disabled |
| **FFmpeg** | L | LGPL/GPL (build-dependent) | Yes (personal use; not redistributed) | ✅ |

### 3.4a Stock video & images (ADR-0020, added at C2) — all optional

| Provider | Tier | Access path | Licence summary (to verify from official terms in Phase 8) | Default | Status |
|---|---|---|---|---|---|
| **Any site, manual import** | — | Owner downloads or buys on the site, imports the file + licence proof | As purchased | Always available | ✅ design |
| **Pexels API** | F | Owner's free API key | Free commercial use. No standalone resale. No scraping or bulk / ML collection. Attribution requested. | OFF | 🟡 secondary sources |
| **Pixabay API** | F | Owner's free API key | Pixabay Content License. Reportedly 24 h response caching and no mass downloads. | OFF | 🟡 secondary sources |
| **Shutterstock** | P | API mostly enterprise / contact sales; else manual import | Per licence (standard / enhanced / editorial) | DISABLED, budget 0 | 🟡 |
| **Adobe Stock** | P | Developer API (pricing undisclosed); else manual import | Per licence | DISABLED, budget 0 | 🟡 |
| **Storyblocks** | P | API by custom contract; else manual import | Subscription licence | DISABLED, budget 0 | 🟡 |
| **Pond5, Getty / iStock** | P | Enterprise API; else manual import | Per licence | DISABLED, budget 0 | ❌ |
| **Envato Elements** | P | Manual import only (no general download API) | Subscription licence, register each project | Manual only | 🟡 |

**Editorial-only licences are blocked for monetised channels.** Every paid purchase needs a separate owner confirmation with the price shown. The monthly stock budget cap defaults to 0.

### 3.5 Infrastructure & notifications

| Component | Tier | Licence | Status |
|---|---|---|---|
| PostgreSQL | L | PostgreSQL licence (permissive) | ✅ (well-known) |
| **Procrastinate** (Postgres task queue) | L | **MIT** | ✅ |
| Redis 8+ | L | **Tri-licence: RSALv2 / SSPLv1 / AGPLv3** | ✅ (not needed, see ADR-0004) |
| Valkey | L | **BSD-3-Clause** | ✅ (fallback only) |
| **Telegram Bot API** | F | "bots are able to message their users **at no cost**". About 1 msg/s per chat, ~30 msg/s bulk. Files up to 50 MB. | ✅ [Bots FAQ](https://core.telegram.org/bots/faq) |
| SMTP email | F | Depends on the owner's mail provider | ❌ optional, off |
| WhatsApp | P | — | ⛔ disabled |
| **GitHub Actions** | F | **Standard GitHub-hosted runners in public repositories: "This usage remains free."** Larger runners are billed. | ✅ [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) |

### 3.6 Operating system (owner machine)

| Item | Finding | Status |
|---|---|---|
| Windows 10 end of support | General support ended **14 Oct 2025**. ESU program exists. | ✅ [Microsoft Learn](https://learn.microsoft.com/en-us/windows/whats-new/extended-security-updates) |
| Consumer ESU end date | Microsoft **extended consumer ESU to 12 Oct 2027** (announced around 25 Jun 2026). Already-enrolled PCs stay covered. Free enrolment routes exist (details on Microsoft's consumer page). | 🟡 (several secondary sources: [BleepingComputer](https://bleepingcomputer.com/news/microsoft/microsoft-quietly-extends-free-windows-10-esu-support-to-october-2027), [Tom's Hardware](https://tomshardware.com/software/windows/microsoft-extends-free-windows-10-security-updates-for-a-second-year), [Help Net Security](https://www.helpnetsecurity.com/2026/06/26/microsoft-windows-10-free-security-updates-esu-program/)) |

**Owner action (free):** enrol the PC in the Windows 10 consumer ESU program if it isn't already. It needs Windows 10 version 22H2. That turns D-10 from "unpatched OS" into "patched until Oct 2027".

---

## 4. Items still UNVERIFIED (carried into later steps)

| Item | Why | When |
|---|---|---|
| Exact Gemini & Groq free limits for the owner's account | Only shown in the provider consoles | Phase 5 setup, entered into the registry by the owner |
| Free-tier image generation provider with a commercial-OK licence | Hosts not allowlisted. Gemini image is not free. | Phase 8 spike |
| Mistral / OpenRouter free tiers | Not allowlisted | Optional, Phase 5+ |
| WhatsApp pricing | Adapter disabled | Only if the owner asks |
| `publishAt` rule detail, Analytics API quota | Detailed reading | Step 0.5 |
| Urdu Piper voice dataset licence | Model card says MIT; third-party site disagrees | Phase 8, owner check |
| Local small LLM choice + licence | Depends on Phase 1 RAM measurements | Phase 5 |
