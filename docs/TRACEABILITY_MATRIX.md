# Traceability Matrix — master prompt → specs → phases → tests

**Version:** 1.0 (C6 completeness check, 2026-11-08)
**Purpose:** prove every requirement in `00_MASTER_PROMPT.md` (and the owner's additions) is covered by a spec, a build phase and a test. A Phase 1 CI check (`tools/check_traceability.py`) verifies that every referenced file exists and that each referenced heading or ID appears in it.

## 1. Required documents (§18, §21)
| Required | File | Status |
|---|---|---|
| 00_MASTER_PROMPT | docs/00_MASTER_PROMPT.md | ✅ |
| PRODUCT_REQUIREMENTS | docs/PRODUCT_REQUIREMENTS.md | ✅ v1.4 |
| SYSTEM_ARCHITECTURE | docs/SYSTEM_ARCHITECTURE.md | ✅ v1.0 |
| TECH_STACK_EVALUATION | docs/TECH_STACK_EVALUATION.md | ✅ v1.0 |
| FRONTEND_SPECIFICATION | docs/FRONTEND_SPECIFICATION.md | ✅ v1.0 |
| BACKEND_SPECIFICATION | docs/BACKEND_SPECIFICATION.md | ✅ v1.0 |
| DATABASE_SCHEMA | docs/DATABASE_SCHEMA.md | ✅ v1.0 |
| AI_AGENT_ARCHITECTURE | docs/AI_AGENT_ARCHITECTURE.md | ✅ v1.1 |
| AGENT_PROMPTS | docs/AGENT_PROMPTS.md | ✅ v1.1 |
| CHANNEL_DISCOVERY_SPEC | docs/CHANNEL_DISCOVERY_SPEC.md | ✅ v1.0 |
| VIDEO_PRODUCTION_SPEC | docs/VIDEO_PRODUCTION_SPEC.md | ✅ v1.0 |
| THUMBNAIL_SEO_SPEC | docs/THUMBNAIL_SEO_SPEC.md | ✅ v1.0 |
| YOUTUBE_API_INTEGRATION | docs/YOUTUBE_API_INTEGRATION.md | ✅ v1.0 |
| OAUTH_SECURITY | docs/OAUTH_SECURITY.md | ✅ v1.0 |
| WORKFLOW_STATE_MACHINE | docs/WORKFLOW_STATE_MACHINE.md | ✅ v1.0 |
| NOTIFICATION_SPEC | docs/NOTIFICATION_SPEC.md | ✅ v1.0 |
| AUDIT_AND_POLICY_SPEC | docs/AUDIT_AND_POLICY_SPEC.md | ✅ v1.0 |
| FREE_TIER_PROVIDER_MATRIX | docs/FREE_TIER_PROVIDER_MATRIX.md | ✅ v1.0 |
| COST_CONTROL_SPEC | docs/COST_CONTROL_SPEC.md | ✅ v1.0 |
| DEPLOYMENT_GUIDE | docs/DEPLOYMENT_GUIDE.md | ✅ v1.0 (commands verified in Phase 15) |
| TESTING_AND_QA | docs/TESTING_AND_QA.md | ✅ v1.0 |
| IMPLEMENTATION_ROADMAP | docs/IMPLEMENTATION_ROADMAP.md | ✅ v1.0 |
| CLAUDE_CODE_BUILD_INSTRUCTIONS | docs/CLAUDE_CODE_BUILD_INSTRUCTIONS.md | ✅ v1.0 |
| RISK_REGISTER | docs/RISK_REGISTER.md | ✅ v1.0 |
| COMPLIANCE_CHECKLIST | docs/COMPLIANCE_CHECKLIST.md | ✅ v1.0 |
| GLOSSARY | docs/GLOSSARY.md | ✅ |
| adr/ADR-0001… | docs/adr/ (21 ADRs) | ✅ all Accepted |
| CLAUDE.md (repo root) | CLAUDE.md | ✅ |
| Extra: progress, validation, traceability | PROJECT_PROGRESS.md, PHASE0_VALIDATION_REPORT.md, this file | ✅ |

## 2. End-to-end workflow (§2.4, 25 steps)
| # | Step | User story | Spec | Agent(s) | Phase | Key test |
|---|---|---|---|---|---|---|
| 1 | Discover niches | US-2.1 | CHANNEL_DISCOVERY §2–3 | A02 | 6 | rescore determinism, forbidden phrases |
| 2 | Trending/emerging opportunities | US-2.2 | CHANNEL_DISCOVERY §5 | A03 | 6 | delta + injection tests |
| 3 | Channel concepts | US-2.4 | CHANNEL_DISCOVERY §4 | A06 | 6 | blueprint schema |
| 4 | Name, branding, description | US-2.4 | CHANNEL_DISCOVERY §4 | A07 | 6 | font licence, golden |
| 5 | Manual channel creation + OAuth | US-3.1–3.3 | CHANNEL_DISCOVERY §8, OAUTH_SECURITY §4 | — | 4 | OAuth mocks + manual connect |
| 6 | Trending video ideas | US-4.1 | AGENT_PROMPTS A08 | A08, A03 | 7 | similarity/diversity |
| 7 | Competitor & audience research (official APIs) | US-2.3 | CHANNEL_DISCOVERY §7, ADR-0015 | A04 | 6 | T-AGG, retention |
| 8 | Original ideas and scripts | US-4.4, US-4.5 | AGENT_PROMPTS A11, VIDEO_PRODUCTION §1a | A11 | 7 | T-PROMISE, owner blind review |
| 9 | Fact-check with citations | US-4.2, 4.3 | AGENT_PROMPTS A09/A10 | A09, A10 | 7 | contradicted-claim block |
| 10 | Storyboard | US-5.1 | AGENT_PROMPTS A12 | A12 | 8 | duration sum |
| 11 | Original images / visuals | US-5.2 | VIDEO_PRODUCTION §5, ADR-0010/0020 | A13, A14 | 8 | T-RIGHTS |
| 12 | Authorised voiceover | US-5.3 | VIDEO_PRODUCTION §6, ADR-0019 | A15 | 8 | T-CONSENT, NC block |
| 13 | Assemble long-form | US-6.1, 6.2 | VIDEO_PRODUCTION §3–4, §8 | A16, A17 | 9 | ffprobe/determinism |
| 14 | Produce Shorts | US-6.2 | VIDEO_PRODUCTION §9 | A16, A17 | 9 | ≤ 180 s hard rule |
| 15 | Thumbnails | US-7.1 | THUMBNAIL_SEO §1 | A18 | 10 | thumbnail fixtures |
| 16 | SEO titles, descriptions, tags, chapters | US-7.2 | THUMBNAIL_SEO §2 | A19 | 10 | validators (100 chars / 5000 bytes / 500 chars) |
| 17 | Subtitles | US-6.3 | VIDEO_PRODUCTION §4 | A20 | 10 | sync ≤ 200 ms |
| 18 | Quality, copyright, policy audit | US-8.1, 8.2 | AUDIT_AND_POLICY §2 | A21, A22, A23 | 11 | **T-BLOCK** |
| 19 | Upload (resumable, official API) | US-9.1 | YOUTUBE_API §5–7 | A24 | 4 (test), 12 | T-PRIV, T-DUP, resume |
| 20 | Thumbnail & metadata | US-9.1 | YOUTUBE_API §6 | A24 | 12 | post-step retries |
| 21 | Schedule publishing | US-9.2 | YOUTUBE_API §5 (I-8), Y14 | A25 | 12 | schedule guards |
| 22 | Pull analytics | US-10.1 | YOUTUBE_API §9 | A26 | 13 | mock analytics, DP-3 |
| 23 | Improve with performance data | US-10.2 | VIDEO_PRODUCTION §1a (retention loop) | A27 | 13 | evidence-required |
| 24 | Notify the owner | US-11.1 | NOTIFICATION_SPEC | A29 | 4 (in-app), 14 | dedup / quiet hours |
| 25 | Audit agents, activity, costs, operations | US-1.4, US-12.x | AUDIT_AND_POLICY §3, COST_CONTROL | A30, A31, A32 | 3, 5, 11 | T-LIMIT, chain verify |

## 3. Zero-cost policy (§3.1)
| Rule | Where | Test |
|---|---|---|
| 1 No paid API by default | COST_CONTROL G1 | T-PAID |
| 2 No auto-upgrade | G2 | grep test |
| 3 Billing only with logged permission | G3, §3 | T-PAID |
| 4 No payment credentials | G4 | schema review |
| 5 Monitoring | G5 | A32 tests |
| 6 Configurable limits | G6, `usage_limits` | T-LIMIT |
| 7 Pause + notify at limit | G7 | T-LIMIT |
| 8 Free fallback | G8 | fallback test |
| 9 Cost & Usage dashboard | FRONTEND §26 | E2E |
| 10 Provider Registry with licence, limits, verification | G10, FREE_TIER_PROVIDER_MATRIX | registry seed test |

## 4. Architecture components (§5 A–N) → SYSTEM_ARCHITECTURE §4
A Web App · B API · C Orchestrator · D Agents · E Queue · F DB · G Media store · H AI Gateway · I YouTube service · J Render · K Notifications · L Analytics · M Auditing · N Monitoring — all specified (purpose, boundaries, interfaces, data, failure modes, scaling, tests). Added: **O** Stock & Voice modules. Required diagrams (context, container, long-form, Short, OAuth, upload, failure/retry) are SYSTEM_ARCHITECTURE §2, §3, §6, §7, §8, §9, §10.

## 5. Frontend (§6) → FRONTEND_SPECIFICATION
All 31 sections (§1–§31 of that file), each with route, purpose, desktop and mobile layout, components, forms and validation, actions, tables, API calls, real-time events, permissions, and empty/loading/error/success states. Global elements in §0.1: Emergency Stop, mode badge, quota/usage meter, bell, Private-only banner. Owner additions: "Edit with…" picker (pages 13, 16, 31), voice clone (page 15), stock (page 25).

## 6. Agents (§7) → AI_AGENT_ARCHITECTURE + AGENT_PROMPTS
32 agents with the full §7.2 template. Prompts exist for all 17 prompted agents. The 15 agents that don't use a text prompt are listed in AGENT_PROMPTS §0a with the spec that defines their rules instead. §7.3 rules (logical roles, no direct calls, Gateway only, schema validation + one repair, independent auditors, disallowed actions) are in AI_AGENT_ARCHITECTURE §1 and the common rules.

## 7. Database (§15) → DATABASE_SCHEMA
| Brief name | Table(s) |
|---|---|
| users · roles · permissions | users, roles, permissions, role_permissions, user_roles, sessions |
| channel profiles | channels, channel_publishing_rules, onboarding_steps |
| OAuth connections | oauth_clients, oauth_connections, oauth_pending_flows |
| channel strategies | channel_strategies |
| research sources | research_sources, source_documents |
| trend reports | trend_items |
| competitor reports | youtube_api_cache (single-item lookups, ≤ 30 days, ADR-0015) |
| keywords | keywords |
| video ideas / projects | video_ideas, video_projects, owner_value_add, research_briefs |
| scripts + versions | scripts, script_versions, fact_check_claims |
| storyboards + scenes | storyboards, scenes |
| media assets · rights/licences | media_assets, asset_rights, stock_purchases |
| voice configurations + consent | voice_configurations, voice_profiles, voice_consents, narration_segments |
| render jobs | timeline_versions, render_jobs |
| thumbnails · SEO metadata | thumbnails, seo_packages, disclosure_assessments, caption_tracks |
| policy checks · audit reports | audit_reports, audit_overrides |
| approval records | approval_requests |
| upload jobs · publishing schedules | upload_jobs (privacy_status, publish_at) |
| analytics snapshots | analytics_snapshots, growth_suggestions, comment_suggestions |
| notifications + deliveries | notifications, notification_deliveries, notification_preferences, notification_targets |
| agent configurations · runs | agent_configurations, agent_runs |
| workflow tasks | workflow_transitions, job_meta (+ Procrastinate tables) |
| provider registry · usage records | provider_registry, provider_credentials, usage_limits, usage_records, gateway_cache, cost_budgets, provider_reverify_reminders |
| quota ledger | quota_ledger, quota_reservations, quota_config |
| security events | security_events, audit_log (hash chain), kill_switches |
| system settings | system_settings |
| ADR references | adr_references |
| (added) | external_editors, external_edit_sessions, data_deletion_tasks, niche_reports, niche_candidates, score_weight_profiles, system_health_samples, backups |

## 8. Other sections
| Brief § | Covered in |
|---|---|
| §1 Facts F1–F9 | FREE_TIER_PROVIDER_MATRIX §1 (verified; F1 reversed 2 Nov 2026; F7 not needed) |
| §2.5 Non-goals | PRD §4.2 (NG-1…NG-10) |
| §3.2–3.3 Tiers, hardware | TECH_STACK_EVALUATION §3, PRD §2 (H-LITE) |
| §4 Tech evaluation | TECH_STACK_EVALUATION, ADR-0001…0018 |
| §8 Discovery | CHANNEL_DISCOVERY_SPEC |
| §9 Production | VIDEO_PRODUCTION_SPEC |
| §10 Thumbnails & SEO | THUMBNAIL_SEO_SPEC |
| §11 YouTube integration + compliance tasks | YOUTUBE_API_INTEGRATION, OAUTH_SECURITY, COMPLIANCE_CHECKLIST |
| §12 Notifications | NOTIFICATION_SPEC |
| §13 Audits | AUDIT_AND_POLICY_SPEC |
| §14 Modes & controls | PRD §5, WORKFLOW_STATE_MACHINE §0, SYSTEM_ARCHITECTURE §5 |
| §16 State machines (Channel, Idea, Project, Render, Upload, Notification) | WORKFLOW_STATE_MACHINE §1–6 (+ Approval, Voice Profile, Stock Purchase, External edit) |
| §17 Testing & release | TESTING_AND_QA |
| §19 Checkpoints | PROJECT_PROGRESS checkpoint log (C0–C6) |
| §20 Roadmap (per-phase fields + free-tier check) | IMPLEMENTATION_ROADMAP (16 phases) |
| §22 Deliverable standard | This matrix + RISK_REGISTER "Unresolved items" |

## 9. Owner additions during Phase 0
| Addition | ADR / story | Phase |
|---|---|---|
| Windows 10, 8 GB, no GPU (H-LITE); 5 languages; Asia/Karachi | PRD §2, validation §10 | all |
| Code on GitHub (public repo) | PROJECT_PROGRESS C0 | all |
| Free tier only | COST_CONTROL | all |
| Own voice recording + cloning | ADR-0019, US-5.3 | 8 |
| Optional stock video/images (free + paid) | ADR-0020, US-5.2 | 8 |
| Install on D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE | ADR-0001 amendment, SYSTEM_ARCHITECTURE §11 | 1, 15 |
| Optional external editors (Canva, CapCut, InShot, Filmora, …) | ADR-0021, US-6.4 | 9–10 |
| Promise in intro, 10–15 s hook, mid-video re-hooks, curiosity/suspense, human voice | US-4.5, AGENT_PROMPTS A11 v1.1 | 7 |
