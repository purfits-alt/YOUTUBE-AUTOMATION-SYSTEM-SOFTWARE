# Risk Register

**Version:** 0.1 (Step 0.7, for Checkpoint C6) · **Date:** 2026-11-08 · Reviewed at every phase report and the 30-day launch review.
Scale: Likelihood (L) and Impact (I) 1–5 · Score = L × I · Owner: **O** = owner, **C** = Claude Code / developer

| ID | Risk | L | I | Score | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|---|
| R01 | **YPP rejects or demonetises the channel as inauthentic / mass-produced (F3)** | 4 | 5 | 20 | Owner-directed, quality-first design; owner value-add fields; own voice / own-voice clone; originality score; format variety; publishing caps; Policy Auditor; script craft with honest promises; 30-day review | O + C | Open (core business risk — cannot be eliminated by software) |
| R02 | Revenue or growth expectations not met | 4 | 4 | 16 | No revenue promises in product; success metrics are process metrics; analytics-driven improvement; owner's niche choice | O | Open (accepted) |
| R03 | **Accidental public upload** (API default flipped to public on 2 Nov 2026) | 2 | 5 | 10 | Invariant I-6 (explicit privacy), Private-only default ON, approval hash, publishing kill switch, tests T-PRIV | C | Mitigated by design |
| R04 | YouTube API access revoked for policy misuse (aggregation, retention) | 2 | 5 | 10 | ADR-0015, retention jobs, compliance checklist, no scraping, privacy policy | C + O | Mitigated by design |
| R05 | Free-tier terms/limits change or free tier withdrawn (Gemini, Groq) | 3 | 4 | 12 | Fallback chains incl. local Ollama; registry re-verification every 90 days; usage limits; graceful degradation | C | Open |
| R06 | Accidental paid charges | 1 | 4 | 4 | No billing on GCP projects; Tier P two-step; budget caps 0; paid-indicator detection; COST_CONTROL_SPEC tests | C + O | Mitigated |
| R07 | 8 GB RAM / CPU-only too slow (renders, TTS, clone) | 4 | 3 | 12 | One heavy job at a time; night window; 720p profile; proxies; benchmarks in Phase 9; optional RAM upgrade (owner choice) | O + C | Open |
| R08 | Windows 10 security after ESU ends (Oct 2027, secondary sources) | 3 | 4 | 12 | Enrol in consumer ESU; localhost-only; encryption; plan Win 11/Linux before Oct 2027 | O | Open |
| R09 | OAuth "Testing" tokens expire every 7 days → missed uploads | 4 | 2 | 8 | Expiry warnings 24 h ahead; one-click re-auth; move consent screen to "In production" | O + C | Mitigated |
| R10 | Copyright claims (music, stock, external editor libraries) | 3 | 4 | 12 | Rights records mandatory; CapCut/Canva library flags; licence proofs kept; YouTube Audio Library/CC0/owner music | O + C | Mitigated |
| R11 | Voice-clone misuse or consent dispute | 1 | 4 | 4 | Owner-only live enrolment, consent code + speaker match, encrypted, no export, deletion | C | Mitigated |
| R12 | Prompt injection via research sources/comments | 3 | 3 | 9 | Untrusted wrappers, no-tools rule, schema validation, auditors independent, adversarial tests | C | Mitigated |
| R13 | Factual errors in videos | 3 | 4 | 12 | Cited research, fact-check agent, contradicted-claim block, owner review | O + C | Mitigated |
| R14 | Data loss (disk failure on D:) | 2 | 4 | 8 | Daily DB backups, key export to USB, manual media backup, restore tests | O | Open |
| R15 | Urdu quality (TTS, captions, RTL thumbnails) poor | 4 | 2 | 8 | Owner voice recommended; Urdu captions require owner review; launch in English first | O | Accepted |
| R16 | Archived/unsupported components (Chatterbox repo archived) break | 2 | 2 | 4 | Hash-pinned, optional; OpenVoice converter as default | C | Accepted |
| R17 | Procrastinate Windows compatibility issue | 2 | 3 | 6 | Phase 1 spike + fallback SKIP LOCKED queue | C | Open (resolved in Phase 1) |
| R18 | Public GitHub repo leaks secrets | 1 | 5 | 5 | gitleaks pre-commit + CI, .gitignore, no secrets in config, encrypted at rest | C | Mitigated |
| R19 | Single-owner bus factor / owner time limited | 3 | 3 | 9 | Runbooks, MANUAL mode default, clear dashboards, notifications | O | Accepted |
| R20 | Google changes YouTube API (quota, fields, policies) again | 3 | 3 | 9 | Costs/limits in config; revision-history check monthly (A32 reminder); adapters isolated | C | Open |
| R21 | Platform/AI-content policy tightening (disclosure, likeness) | 3 | 4 | 12 | Disclosure assessment per official definition; auditor rules versioned; monthly policy review reminder | O + C | Open |
| R22 | External editor watermarks or licence surprises | 3 | 2 | 6 | Declaration form, watermark warning, library flags | O | Mitigated |
| R23 | Scope size (31 pages, 32 agents) delays delivery | 4 | 3 | 12 | Strict phase gating, MVP-first per phase, owner approvals, reuse of shared components | C + O | Open |

## Unresolved items carried into build (for C6)
| Item | Resolved in |
|---|---|
| Exact Gemini/Groq free limits for the owner's accounts | Phase 5 (owner enters from consoles) |
| Local small LLM choice + licence after RAM measurement | Phase 5 |
| Free image-generation provider with commercial-OK licence (or none) | Phase 8 spike |
| Pexels/Pixabay official API terms | Phase 8 (verify before enabling) |
| OpenVoice / Chatterbox **weights** licences on Hugging Face | Phase 8 (before enabling) |
| Urdu Piper voices licence conflict (MIT card vs third-party note) | Phase 8 (owner check) |
| Google OAuth verification needs for "In production" with sensitive scopes | Phase 4 |
| Wikimedia API terms, RSS feed terms per feed | Phase 6 |
| H-LITE performance numbers (render, TTS, clone) | Phase 9 benchmarks |
| Windows 10 consumer ESU end date from Microsoft's own page | Owner / Phase 15 |
| WhatsApp pricing (only if owner ever asks) | n/a (disabled) |
