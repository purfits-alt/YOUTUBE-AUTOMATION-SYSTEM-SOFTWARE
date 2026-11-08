# ADR-0025: Channel Trending — own-channel outliers and replicating own winners

**Status:** Accepted (owner decision, 2026-11-08) · **Date:** 2026-11-08 · **Deciders:** Owner

## Context
The owner asked for a Trending area in Channels with **Outliers**, **Replicate / "milky" videos** and **New Ideas**. Common YouTube tools find outliers by ranking *other* channels' videos, which conflicts with the YouTube Developer Policies' data-aggregation rule that ADR-0015 follows. Repeating a winning video too closely also risks YouTube's reused / inauthentic content rules (F3).

## Options considered
1. **Own channels only** (chosen): outliers from the owner's own YouTube Analytics; variations only of the owner's own videos.
2. Own channels + one-at-a-time public lookup of another video (no ranking).
3. Rank other channels' videos (rejected: breaks ADR-0015, risks API access).

## Decision
- **Outliers:** an own video whose views at age N days are ≥ 2× the channel median at the same age (last 30 videos of the same format); ≥ 5× = big outlier. Own analytics only (same content owner, allowed by ADR-0015 §3).
- **Replicate / Milk:** A08 Idea Generation gets a *variation mode* (Part 2, new angle, update, Short from long, long from Short, series) for the owner's own winners. Results are ordinary ideas (`source = REPLICATE`, linked to the source video) and go through the normal pipeline, approvals and auditors.
- **Originality guard:** a variation must be ≤ 0.70 similar to its source (owner-adjustable) and carry an owner value-add prompt; near copies are refused (`422 TOO_SIMILAR`).
- **New Ideas:** the newest A08 suggestions with their reason (trend, or pattern of an own outlier).
- Screens with sample data now (Page 32, Channel Trending); real data in Phase 7 (ideas, variation mode) and Phase 13 (analytics, outliers).

## Free-tier status
Free. Introduces no paid dependency ✔ (uses own YouTube Analytics quota and the existing free LLM chain).

## Licences
YouTube API Services Terms + Developer Policies (own-channel data).

## Consequences
- No cross-channel statistics; "outliers" are always relative to the owner's own channel.
- Schema: `video_ideas.source` gains `REPLICATE`, plus `based_on_youtube_video_id`, `variation_kind`, `similarity_to_source`.
- New endpoints: `GET /channels/{id}/outliers`, `GET /channels/{id}/replicate`, `POST /channels/{id}/ideas/replicate`.

## References
- ADR-0015, US-4.6, FRONTEND_SPECIFICATION §32, AI_AGENT_ARCHITECTURE A08
