# ADR-0015: Research data policy: comply with the YouTube 'Data Aggregation' rule

**Status:** Accepted (owner approved at C2, 2026-11-08) · **Date:** 2026-11-08 · **Deciders:** Owner, Claude Code

## Context
Verified 2026-11-08, Developer Policies: 'Do not aggregate API Data except … channels under the same content owner' and 'Do not … use API Data … to gain insights into YouTube's usage, revenue, or any other aspects of YouTube's business.' Non-authorized data may be stored ≤ 30 days. This conflicts with master prompt §8 ideas such as cross-channel competitor pattern scoring.

## Options considered
1. Conservative: no cross-channel aggregation of YouTube API data (chosen)
2. Brief as written (aggregate competitor metadata)
3. Skip competitor research entirely

## Decision
(1) **Niche Opportunity Score** uses *non-YouTube* permitted sources (Wikipedia pageviews API, RSS/news, Google Trends API alpha if the owner is accepted, owner knowledge, our own channels' Analytics) plus LLM reasoning. It does **not** compute statistics across YouTube channels. (2) **Competitor research** = the owner names a channel or video, and the system shows that item's public metadata *individually* (no cross-channel stats, no ranking tables built from YouTube data), cached ≤ 30 days, then deleted or refreshed. (3) **Own-channel analytics** may be aggregated (same content owner). (4) Any feature that might count as aggregation is marked `REQUIRES OWNER APPROVAL` and listed in COMPLIANCE_CHECKLIST.

## Free-tier status
Free. ✔ Also saves search.list quota (100/day).

## Licences
YouTube API Services Terms + Developer Policies.

## Consequences
- Niche discovery relies less on YouTube numbers. Evidence comes from other permitted sources.
- Lower risk of API access revocation.
- The owner may ask Google for clarification (optional).

## References
- `docs/TECH_STACK_EVALUATION.md`
- `docs/FREE_TIER_PROVIDER_MATRIX.md`
