# TubeForge — Project Progress

> Living document. Updated at every checkpoint and at the end of every phase.

**Current phase:** Phase 0 — Research & Architecture (planning only, no application code)
**Current step:** 0.5 Interface specs (frontend, backend, DB, OAuth security, YouTube API) → working toward **C4**
**Last updated:** 2026-11-08

---

## Checkpoint log

| Checkpoint | Scope | Status | Date | Owner decision |
|---|---|---|---|---|
| C0 | Discovery questions | ✅ Closed | 2026-11-08 | Answers + defaults recorded below |
| C1 | PRODUCT_REQUIREMENTS.md | ✅ Approved | 2026-11-08 | All proposed defaults OQ-1…OQ-6 accepted |
| C2 | Tech stack, provider matrix, ADRs, fact verification | ✅ Approved | 2026-11-08 | All 18 ADRs accepted + owner added: own-voice cloning (ADR-0019) and optional stock media incl. paid (ADR-0020) |
| C3 | System architecture, state machine | ✅ Approved | 2026-11-08 | Defaults A-1…A-3 accepted; install root `D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE` |
| C4 | Frontend, backend, DB, OAuth, YouTube API specs | 🔄 In progress | 2026-11-08 | |
| C5 | Agents, prompts, discovery, production, SEO, notifications, audit, cost specs | Not started | | |
| C6 | Roadmap, QA, deployment, build instructions, risks, compliance, CLAUDE.md — **SPEC APPROVAL** | Not started | | |

---

## Phase 0 task list (Step 3 — actionable plan)

| ID | Task | Depends on | Output | Acceptance criteria |
|---|---|---|---|---|
| P0-01 | Inspect repo and planning docs; create repo skeleton | — | `docs/`, git repo | ✅ Done. Master prompt saved; repo initialised |
| P0-02 | Validation of the brief | P0-01 | `PHASE0_VALIDATION_REPORT.md` | ✅ Done (draft). Conflicts, gaps, limits, risks listed |
| P0-03 | Discovery questions (Step 0.1) | P0-01 | Owner answers | ✅ Done. Answers/defaults recorded |
| P0-04 | Product requirements (Step 0.2) | P0-03 | `PRODUCT_REQUIREMENTS.md`, `GLOSSARY.md` | ✅ Approved at C1. Personas, user stories with testable acceptance criteria for all 25 workflow steps, non-goals, success metrics (no revenue promises). Owner approves at C1 |
| P0-05 | Verify platform facts F1–F9 from official sources | P0-03 | Records in `FREE_TIER_PROVIDER_MATRIX.md`, `YOUTUBE_API_INTEGRATION.md` | ✅ Done (F7 not needed — adapter disabled). Each fact has URL + verification date, or is marked `UNVERIFIED` with a design workaround |
| P0-06 | Tech-stack evaluation + ADRs (Step 0.3) | P0-03, P0-05 | `TECH_STACK_EVALUATION.md`, `adr/ADR-0001…` | ✅ Approved at C2 (20 ADRs). ≥2 options per area of Section 4, compared on free status, licence, OS support, hardware, maintenance, testability. One ADR per decision. Owner approves at C2 |
| P0-07 | System architecture + state machine (Step 0.4) | P0-06 | `SYSTEM_ARCHITECTURE.md`, `WORKFLOW_STATE_MACHINE.md` | ✅ Approved at C3 (16 Mermaid diagrams, all parse-checked). 7 required Mermaid diagrams. Components A–N with interfaces and failure modes. All 6 state machines with guards and owners. Owner approves at C3 |
| P0-08 | Interface specs (Step 0.5) | P0-07 | Frontend, backend, DB, OAuth security, YouTube API docs | All 31 pages fully specified (4 states each). Every endpoint typed. Every table with constraints and indexes. Owner approves at C4 |
| P0-09 | Domain specs (Step 0.6) | P0-07 | Agent architecture, prompts, discovery, production, SEO, notifications, audit, cost docs | All 32 agents follow the template in §7.2. Prompts versioned with JSON schemas. Audit blocking rules defined. Owner approves at C5 |
| P0-10 | Roadmap + ops docs (Step 0.7) | P0-08, P0-09 | Roadmap, testing, deployment, build instructions, risk register, compliance checklist, `CLAUDE.md` | Each build phase lists tasks, files, acceptance tests, demo script and free-tier check ✔. **C6 spec approval** |

### Build-phase dependency outline (preliminary; finalised in P0-10)

```
P1 Foundation ─┬─ P2 Frontend shell
               └─ P3 Backend/DB/Auth ── P4 OAuth + quota ledger (+ test-only upload)
                                     └─ P5 Orchestrator + Gateway ─┬─ P6 Niche/Trends
                                                                   ├─ P7 Ideas/Research/Scripts ── P8 Storyboard/Images/Voice ── P9 Render
                                                                   │                                                           └─ P10 Thumbs/SEO
                                                                   └──────────────────────────────── P11 Auditing (gates P12)
                                                                       P12 Upload/Schedule ── P13 Analytics/Optimisation (+ comment moderation)
                                                                       P14 Notifications ── P15 Security/E2E/Deploy ── P16 Launch
```

---

## C0 answers (closed 2026-11-08 — owner said "use defaults" for open items)

| Q | Answer | Source |
|---|---|---|
| 1 Hardware | Windows 10, 8 GB RAM, no GPU → **H-LITE** profile (validation report §10). Free disk: unknown → installer checks for ≥ 60 GB and warns | Owner / default |
| 2 Channels / languages | Languages supported: EN, ES, FR, DE, UR. **Launch: 1 channel, English.** Others added after launch review | Owner / default |
| 3 Timezone / notifications | Asia/Karachi. **In-app + Telegram** (email optional, off) | Owner / default |
| 4 Own voice / camera | Unknown → owner-voice recording supported and **recommended**; TTS allowed with value-add checks | Default |
| 5 Niches | None preset → Phase 6 discovery runs open, owner picks | Default |
| 6 Google Cloud / test channel | Not yet → setup guide in DEPLOYMENT_GUIDE, needed before Phase 4 | Default |
| 7 Docker | **Native Windows install primary**; Docker for CI/dev only | Default |
| 8 GitHub repo | `purfits-alt/YOUTUBE-AUTOMATION-SYSTEM-SOFTWARE` (**public**) | Owner |
| 9 Dashboard access | **Localhost only** (`127.0.0.1`) | Default |
| 10 Policy identity / revenue scope | Identity: individual owner, name & email filled in before Phase 4. **No monetary analytics scope** for now | Default |
| D-10 Windows 10 EOL | **Accept risk** with mitigations: localhost-only, encrypted token store, OS-keyring key, updated browser/AV; recorded in RISK_REGISTER | Default |

## Open decisions (beyond C0 questions)

| ID | Decision | Decide at |
|---|---|---|
| D-1 | Task queue — **decided: Procrastinate (ADR-0004)** | ✅ C2 |
| D-2 | Orchestration — **decided: custom PG state machine (ADR-0005)** | ✅ C2 |
| D-3 | Frontend — **decided: Vite + React SPA (ADR-0006)** | ✅ C2 |
| D-4 | Visuals — **decided: non-generative default, image adapter disabled (ADR-0010)** | ✅ C2 |
| D-5 | TTS — **decided: owner voice > Kokoro > Piper (ADR-0008)** | ✅ C2 |
| D-6 | Privacy-policy hosting — **proposed: GitHub Pages of this public repo (free); domain verification only needed if consent screen goes "In production" with sensitive scopes — detailed in Step 0.5** | C2/C4 |
| D-7 | Dashboard network exposure — **decided: localhost only** | ✅ C0 |
| D-8 | Monetary Analytics scope — **decided: not now** | ✅ C0 |
| D-9 | Media retention & backup — **decided: 30-day intermediates, daily DB+secrets backup** | ✅ C1 |
| D-10 | Windows 10 EOL — **decided: accept risk with mitigations**; update: enrol in free consumer ESU (to Oct 2027) | ✅ C0 / C2 |
| D-11 | Research data policy under YouTube Data Aggregation rule — **decided: conservative (ADR-0015)** | ✅ C2 |
| D-12 | Publishing safety after F1 reversal — **decided: explicit privacy, private by default (ADR-0016)** | ✅ C2 |
| D-13 | Owner voice cloning — **decided: OpenVoice V2 converter (default) + Chatterbox zero-shot (optional), owner-only with consent (ADR-0019)** | ✅ C2 |
| D-15 | Install location — **decided: `D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE`** (all program/data/DB/models on D:) | ✅ C3 |
| D-14 | Stock media — **decided: manual import always; Pexels/Pixabay optional; paid APIs disabled, budget 0 (ADR-0020)** | ✅ C2 |

---

## Phase reports

_None yet — no build phase has started._

## Resource consumption

| Resource | Used |
|---|---|
| Paid services | None |
| Free-tier APIs | None called yet (research used public web pages only) |
| YouTube API quota | 0 units |
