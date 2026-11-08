# ADR-0020: Optional stock video and image providers (free and paid)

**Status:** Accepted (owner request at C2, 2026-11-08) · **Date:** 2026-11-08 · **Deciders:** Owner, Claude Code

## Context
The owner asked for a place for **stock video and images**, including **paid** stock sites, as an **optional** feature. Constraints: zero-cost default (§3 of the brief), rights records for every asset, and YPP "reused content" risk. Findings (2026-11-08, secondary sources, to be verified from official terms in the Phase 8 spike):
- **Pexels** and **Pixabay** have free APIs. Their licences allow commercial use but forbid selling or redistributing content "standalone" or with little change, and forbid scraping or bulk collection (including for ML). Attribution is requested. Pixabay's API terms reportedly require caching responses for 24 h and forbid mass downloads.
- **Paid providers** (Shutterstock, Adobe Stock, Storyblocks, Pond5, Getty/iStock): **API access is mostly enterprise or "contact sales"**. Consumer subscriptions are bought on the provider's website. Envato Elements has no general public API for downloads.
- YPP: videos built mostly from stock footage with little original commentary risk the **reused / inauthentic** policies (F3).

## Options considered
1. **Three-path design: manual import + optional free API adapters + optional paid API adapters** (chosen).
2. Free APIs only.
3. No stock media.

## Decision

### Path A — Manual licensed import (works with ANY site, free or paid) — always available
The owner buys or downloads the asset on the provider's own website with their own account, then imports it into the **Asset Library** with:
- the file
- provider name and asset ID or URL
- licence type (standard, extended, editorial-only, CC0, royalty-free subscription, …)
- licence proof (receipt or licence PDF / screenshot)
- purchase date, cost and currency (optional)
- the account used

TubeForge never handles payment. This is the **recommended path for paid stock**, because most paid APIs require enterprise contracts.

### Path B — Free stock API adapters (Tier F) — optional, OFF by default
**Pexels** and **Pixabay** adapters. The owner pastes their own free API key (stored encrypted). Search and preview in the Asset Library, with download on explicit owner selection only (no bulk download). Licence, attribution text and the source URL are auto-filled into the rights record. Request limits and caching rules come from the provider's API terms, verified before enabling.

### Path C — Paid stock API adapters (Tier P) — optional, DISABLED by default
Adapter slots for **Shutterstock, Adobe Stock, Storyblocks, Pond5, Getty/iStock** behind one `StockProvider` interface (`search`, `preview`, `quote_licence`, `licence_and_download`). Rules:
- Enabled only through the **two-step paid-provider activation** (US-12.3), per provider.
- **Every licence purchase shows the price and needs a separate owner confirmation**. There is no bulk or automatic purchasing, and agents can never buy.
- An owner-set **monthly stock budget cap** (default **0 = purchases impossible**). Purchases are logged in the Cost & Usage dashboard.
- No payment card is stored in TubeForge. Purchases use the owner's account and credits at the provider.
- Implemented only when the owner has an actual API contract or key for a provider. Until then the slot exists as an interface with a "not configured" state.

### Rules for all stock assets
- **No rights record → cannot enter a render** (existing rule).
- **Editorial-only** licences are blocked for monetised channels. Licences that forbid YouTube or commercial use are blocked.
- The **Originality Auditor** measures the stock share of runtime and warns when stock footage exceeds a threshold (default 60 % of runtime) without owner commentary or narration (reused-content risk).
- Licence proof is kept for **Content ID dispute** support.
- Agents may *suggest* search terms. Only the owner selects, downloads or buys.

## Free-tier status
Path A: free (the owner pays the site directly, outside TubeForge). Path B: free tier ✔. Path C: **paid, disabled, budget cap 0 by default** ✔.

## Licences
Per asset, recorded in the rights record. Provider API terms are recorded in the Provider Registry.

## Consequences
- New tables (Step 0.5): `stock_providers` (registry rows), `asset_licences` (extends asset rights with provider asset ID, licence type, proof file, cost), `stock_budget` (monthly cap and spend).
- New UI: "Stock" tab in the Asset Library (search, import, licence form), stock budget card in the Cost & Usage Manager.
- Phase 8 includes a spike that verifies the official Pexels and Pixabay API terms (hosts to be allowlisted then).
