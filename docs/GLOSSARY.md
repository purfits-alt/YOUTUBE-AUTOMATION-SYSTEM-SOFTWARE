# Glossary

| Term | Meaning |
|---|---|
| **Owner** | The single person who controls TubeForge (the "CEO"). The only user in v1. |
| **Agent** | A logical AI role (e.g. Scriptwriting, Policy Auditor). Not a separate service. Agents run as tasks in shared workers. |
| **Auditor agent** | An independent checking agent (#21, 22, 23, 30, 31, 32). Only the owner can override it, and every override is logged. |
| **Orchestrator** | The component that owns workflow state and decides which task runs next. |
| **AI Provider Gateway** | The only path to any AI model (LLM, image, TTS, STT). Enforces limits, licences, caching and logging. |
| **Provider Registry** | Database of every provider and model: tier, limits, licence, commercial-use permission, data-use notes, verification date and URL. |
| **Tier L / F / P** | Local / permanent Free-tier cloud / Paid, trial or promotional credit (disabled by default). |
| **H-LITE / H0 / H1 / H2** | Hardware profiles. H-LITE = 8 GB RAM, no GPU (the owner's current PC). |
| **Quota ledger** | Record of YouTube API units spent per call, per Pacific-Time day. |
| **Private-only mode** | Owner safety switch: all uploads are private and the owner makes videos public manually. ON by default for a new channel until 3 successful test uploads. (YouTube no longer forces unverified API projects to private since 2 Nov 2026 — ADR-0016.) |
| **Compliance audit** | Google's review of an API project. Since 2 Nov 2026 it is **not** needed for public uploads; it is only needed to request a quota extension. |
| **Packaging promise** | The title + thumbnail-text promise of a video; the script must deliver it in the first 15 s (Shorts 3 s) and pay it off (US-4.5). |
| **Re-hook** | A mid-video moment (≈25/50/75 % of runtime) that renews curiosity: open loop, twist, progress marker, pattern interrupt. |
| **Open loop** | A question or tease the script raises and must close later. |
| **Hand-off folder** | Folder on D: used to round-trip a video/thumbnail through an optional external editor (ADR-0021). |
| **YPP** | YouTube Partner Program (monetisation). |
| **Inauthentic content** | YPP term for mass-produced or repetitive content that is not eligible for monetisation. |
| **Owner value-add** | Recorded contributions by the owner (opinion, experience, data, voice, footage) that make a video original. |
| **Rights record** | Proof of permission to use an asset: source, licence, commercial-use flag, attribution, evidence. |
| **`containsSyntheticMedia`** | YouTube API field that declares realistic altered or synthetic content. Always set explicitly. |
| **`publishAt`** | YouTube API field for scheduled release. Only valid while the video is private. |
| **Timeline JSON** | A machine-readable description of a video edit, rendered by FFmpeg. The same input gives the same output. |
| **Proxy render** | A low-resolution preview render used in the editor. |
| **LUFS** | Loudness unit used for audio normalisation (target default −14 LUFS integrated). |
| **Emergency Stop** | Global switch that stops all jobs and blocks uploads and publishing. |
| **Kill switch** | A narrower stop for one channel, agent, provider, or for publishing. |
| **ADR** | Architecture Decision Record (`docs/adr/`). |
| **Checkpoint (C0–C6)** | A Phase 0 owner-approval stop. |
| **RBAC** | Role-based access control (Owner, Editor, Reviewer, Viewer). |
| **Idempotency key** | A unique key that makes a repeated request have no extra effect (e.g. no duplicate upload). |
