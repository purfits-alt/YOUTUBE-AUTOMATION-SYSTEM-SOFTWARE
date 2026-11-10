# Cost Control Specification (Zero-Cost Guarantee)

**Version:** 1.0 (approved at C5, 2026-11-08) · **Date:** 2026-11-08
**Agent:** A32 · **Components:** AI Provider Gateway, Quota ledger, Stock Purchase Gate, Provider Registry · **ADRs:** 0007, 0017, 0020

## 1. Guarantees (enforced in code)
| # | Guarantee | Mechanism |
|---|---|---|
| G1 | No paid API by default | All Tier P registry rows ship `enabled=false`, `paid_activation_step=0`. The Gateway refuses Tier P unless step = 2. |
| G2 | No automatic upgrade | TubeForge never calls any billing or plan endpoint. There is no code path for it (CI grep for billing APIs). |
| G3 | Billing never activated without explicit, logged permission | Two-step activation (§3) with re-auth. Audit log + security event. |
| G4 | No payment credentials stored | No card, bank or billing fields exist in the schema. Stock purchases use the owner's provider account. |
| G5 | Continuous monitoring | Usage reservation before every call. Settlement after. A32 thresholds. |
| G6 | Configurable limits per provider, task and channel (day, month, minute) | `usage_limits` |
| G7 | At the limit → related tasks pause + owner notified | Gateway returns LIMIT → task WAITING_QUOTA; A32 → notification |
| G8 | Approved free fallback used automatically | Provider chain per task (Tier L/F only unless Tier P is activated) |
| G9 | Cost & Usage dashboard | Page 26 |
| G10 | Provider Registry with licence, limits, data-use, verification | `provider_registry` seeded from FREE_TIER_PROVIDER_MATRIX; 90-day re-verify reminders |
| G11 | Trials and promotional credits are never labelled "free" | Registry tier P for trials; UI label "Trial / credit — paid" |

## 2. Limits model
- **Reservation:** before a call, the Gateway inserts `usage_records(kind=RESERVE)` with the estimate (prompt tokens + max output tokens, or chars or seconds) inside a transaction that checks `used + held + estimate ≤ limit`. After the call it settles the actual amount and releases the remainder.
- **Default limits for free-tier providers:** set **below** the provider's published or console limits (safety margin 10 %). Because exact Gemini and Groq free limits are only visible in each console, the **owner enters them during setup** (Phase 5). Until then conservative placeholders apply: Gemini 200 req/day and 500k tokens/day; Groq 500 req/day and 150k tokens/day.
- **Per-task budgets** (default per day): script drafts 30, research 40, ideas 30, SEO 20, policy classifier 30. Configured in Agent Control Center.
- **Local providers** (Tier L) have resource budgets instead of money: heavy-queue CPU minutes per day (default 240), night-window scheduling.
- **YouTube quota:** separate ledger with three buckets (YOUTUBE_API_INTEGRATION §8). Not money, but treated with the same pause-and-notify behaviour.

## 3. Paid provider activation (Tier P) — two steps
1. **Step 1** (re-auth): the owner opens the provider's card → sees the estimated cost per unit and per typical video, the provider's pricing URL and verification date → ticks "I understand this costs money" → `paid_activation_step=1`.
2. **Step 2** (separate request, ≥ 60 s later, re-auth): the owner types `ENABLE PAID <provider_code>` and sets a **monthly cap** (> 0) → `paid_activation_step=2`, `enabled=true`.

Every paid call then shows the estimated cost on the triggering action (e.g. "Generate with X — est. $0.04") and is debited against the cap (`cost_budgets`). At the cap the provider auto-pauses. Disabling is one click and immediate. Re-enabling repeats both steps.

**Implementation (Phase 5, `gateway/paid.py`):**
- The step-1 time is read from the tamper-evident audit log. Step 2 must come at least 60 s **and at most 30 min** after step 1; a stale step 1 is reset.
- A paid call needs a recorded price (`limits.price_in_per_mtok_minor` / `price_out_per_mtok_minor`). Before sending, the gateway checks that the worst case fits this month's budget: estimated input plus the full output allowance. After the call it debits the actual cost.
- At the cap the provider is disabled and a CRITICAL alert is sent. Budgets are per calendar month (UTC).

## 4. Stock purchases (ADR-0020)
- Monthly stock budget `cost_budgets(scope='STOCK')`, cap default **0**. Raising it needs re-auth.
- Each purchase: quote → owner confirmation of **that** purchase with the price shown (re-auth) → licence → download. Agents can never confirm.
- `spent_minor ≤ cap_minor` is enforced by a DB CHECK constraint and an application check.

## 5. Paid-indicator detection (A32)
Triggers a provider kill switch + CRITICAL alert if any of these appear:
- Provider response headers or fields indicating a paid or billing tier (e.g. a tier name changing from free) — per-provider parser
- Rate-limit responses showing limits typical of paid tiers (sudden large increase)
- Gemini: the owner's project shows a usage tier other than Free in the rate-limit header or console info (best effort)
- Any API error mentioning billing, payment or charges
- A manual monthly "statement check" reminder: the owner confirms that no charges appeared on Google Cloud billing (no billing account is expected at all)

**Implementation (Phase 5):**
- Error responses that mention billing or payment are flagged by the adapters.
- Successful responses are checked by `gateway/indicators.py`: a usage-tier header other than free, or a request limit more than 10× the published free limit.
- Either sign disables the provider and sets a PROVIDER kill switch, a security event and a CRITICAL alert.
- A32 (`workers/tubeforge_auditors/a32_cost.py`, every 15 min) covers:
  - threshold alerts at 70/90/100 % for provider limits, YouTube buckets and paid budgets (once per threshold and period);
  - re-verify reminders after 90 days;
  - the statement check on the 1st of each month.
- Each A32 scan is logged as an `agent_runs` row.

## 6. Dashboard (page 26) content
- Banner: "This month: $0.00 spent · 0 paid providers enabled" (green), or the paid totals (amber or red).
- Per provider: tier, enabled, licence, commercial use, data-use (trains on data?), limits vs used (day/month), next reset (PT/PKT), verified date, re-verify due.
- YouTube quota: 3 buckets, used/held/limit, reset time PT + PKT, 7-day forecast.
- Budgets: stock and any paid provider caps.
- Disk usage on D: per channel, intermediate files eligible for cleanup.

## 7. Free-tier check (required in every roadmap phase)
Each phase in IMPLEMENTATION_ROADMAP ends with:
> **Free-tier check:** "This phase introduces no paid dependency: ✔" plus a list of any new external services (tier, licence, verification).
CI enforces part of this: a new dependency licence scan (pip-licenses / license-checker) fails on unapproved licences (AGPL in network-facing code, non-commercial), and new outbound hosts must be registered in the allowlist.

## 8. Acceptance tests (Phase 5)
- **Provider pauses at its limit:** limit 3 requests/day → the 4th call returns LIMIT, the task → WAITING_QUOTA, the notification is created, and the fallback provider is used if configured.
- Tier P provider with step < 2 → the Gateway refuses.
- Step 2 within 60 s of step 1 → refused.
- Stock confirm with an exhausted budget → 422 `BUDGET_EXCEEDED`.
- Simulated paid-indicator response → provider kill switch on + CRITICAL notification.
- Grep test: no billing or payment API client in dependencies or code.
