# TubeForge — Project Progress

> Living document. Updated at every checkpoint and at the end of every phase.

**Current phase:** Phase 0 — Research & Architecture (planning only, no application code)
**Current step:** 0.2 Product requirements → waiting at **OWNER CHECKPOINT C1**
**Last updated:** 2026-11-08

---

## Checkpoint log

| Checkpoint | Scope | Status | Date | Owner decision |
|---|---|---|---|---|
| C0 | Discovery questions | ✅ Closed | 2026-11-08 | Answers + defaults recorded below |
| C1 | PRODUCT_REQUIREMENTS.md | ⏳ Waiting for owner | 2026-11-08 | |
| C2 | Tech stack, provider matrix, ADRs, fact verification | Not started | | |
| C3 | System architecture, state machine | Not started | | |
| C4 | Frontend, backend, DB, OAuth, YouTube API specs | Not started | | |
| C5 | Agents, prompts, discovery, production, SEO, notifications, audit, cost specs | Not started | | |
| C6 | Roadmap, QA, deployment, build instructions, risks, compliance, CLAUDE.md — **SPEC APPROVAL** | Not started | | |

---

## Phase 0 task list (Step 3 — actionable plan)

| ID | Task | Depends on | Output | Acceptance criteria |
|---|---|---|---|---|
| P0-01 | Inspect repo and planning docs; create repo skeleton | — | `docs/`, git repo | ✅ Done. Master prompt saved; repo initialised |
| P0-02 | Validation of the brief | P0-01 | `PHASE0_VALIDATION_REPORT.md` | ✅ Done (draft). Conflicts, gaps, limits, risks listed |
| P0-03 | Discovery questions (Step 0.1) | P0-01 | Owner answers | ✅ Done. Answers/defaults recorded |
| P0-04 | Product requirements (Step 0.2) | P0-03 | `PRODUCT_REQUIREMENTS.md`, `GLOSSARY.md` | ✅ Drafted, awaiting C1. Personas, user stories with testable acceptance criteria for all 25 workflow steps, non-goals, success metrics (no revenue promises). Owner approves at C1 |
| P0-05 | Verify platform facts F1–F9 from official sources | P0-03 | Records in `FREE_TIER_PROVIDER_MATRIX.md`, `YOUTUBE_API_INTEGRATION.md` | Each fact has URL + verification date, or is marked `UNVERIFIED` with a design workaround |
| P0-06 | Tech-stack evaluation + ADRs (Step 0.3) | P0-03, P0-05 | `TECH_STACK_EVALUATION.md`, `adr/ADR-0001…` | ≥2 options per area of Section 4, compared on free status, licence, OS support, hardware, maintenance, testability. One ADR per decision. Owner approves at C2 |
| P0-07 | System architecture + state machine (Step 0.4) | P0-06 | `SYSTEM_ARCHITECTURE.md`, `WORKFLOW_STATE_MACHINE.md` | 7 required Mermaid diagrams. Components A–N with interfaces and failure modes. All 6 state machines with guards and owners. Owner approves at C3 |
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
| D-1 | Task queue: Postgres-backed (Procrastinate) vs Celery/Dramatiq + Valkey — **leaning Postgres-backed (8 GB RAM)** | C2 |
| D-2 | Orchestration: custom Postgres state machine vs LangGraph vs Temporal | C2 |
| D-3 | Frontend: Next.js vs Vite+React — **leaning Vite+React SPA (8 GB RAM)** | C2 |
| D-4 | Image generation stack per hardware profile | C2 |
| D-5 | TTS engine(s), incl. language coverage | C2 |
| D-6 | Hosting of public privacy-policy/terms page (domain question) | C2 |
| D-7 | Dashboard network exposure — **decided: localhost only** | ✅ C0 |
| D-8 | Monetary Analytics scope — **decided: not now** | ✅ C0 |
| D-9 | Media retention & backup policy | C1 |
| D-10 | Windows 10 EOL — **decided: accept risk with mitigations** | ✅ C0 |

---

## Phase reports

_None yet — no build phase has started._

## Resource consumption

| Resource | Used |
|---|---|
| Paid services | None |
| Free-tier APIs | None called yet |
| YouTube API quota | 0 units |
