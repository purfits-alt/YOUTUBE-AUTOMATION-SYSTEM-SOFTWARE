# ADR-0026: Call the YouTube and Google OAuth REST endpoints with httpx

**Status:** Accepted (implementation decision, Phase 4; reported in the Phase 4 report) · **Date:** 2026-11-08 · **Deciders:** Build agent, confirmed at phase approval

## Context
YOUTUBE_API_INTEGRATION §4 named `google-api-python-client` + `google-auth` + `google-auth-oauthlib` for the YouTube integration. While building Phase 4 the needs turned out to be small and very specific:
- PKCE loopback OAuth with our own `state` storage, encrypted code verifier and refresh token (OAUTH_SECURITY §4);
- a resumable upload engine that **persists the session URI and confirmed offset itself** and resumes with `Content-Range: bytes */total` (§6), which `MediaFileUpload` hides inside its own object;
- every request metered in our quota ledger and classified by our error table (§7–§8);
- tests that never touch Google.

The Google client libraries are synchronous, build methods from a discovery document at runtime (no static types for mypy `--strict`), pull in `httplib2`, and would need wrapping at every point above anyway.

## Options considered
1. **httpx + the documented REST endpoints** (chosen): a few hundred lines, fully typed, one HTTP stack for the whole backend, `httpx.MockTransport` for tests.
2. Google client libraries as planned: more code to wrap, untyped, extra transitive dependencies.
3. Google libraries for OAuth only + httpx for the API: two HTTP stacks for no gain.

## Decision
- `httpx` (BSD-3-Clause) becomes a runtime dependency; the Google client libraries are **not** added.
- `SafeYouTubeClient` (`youtube/client.py`) owns the httpx client, allows only `www.googleapis.com` and `youtube.googleapis.com`, meters every metered request in `quota_ledger` (even failed ones) and raises classified `YouTubeApiError`s. `oauth.py` talks to `accounts.google.com` / `oauth2.googleapis.com` the same way.
- Resumable uploads use the documented protocol directly (`uploadType=resumable`, 8 MiB chunks, offset query).
- `tzdata` (Apache-2.0) is added so `zoneinfo` works on Windows (PT quota day, owner time zone).

## Consequences
- Less code and fewer dependencies; behaviour is visible and tested in our own code.
- We must follow Google's REST documentation ourselves when it changes (the platform-fact table §1 is re-verified each phase that touches YouTube).

## Free-tier status
Introduces no paid dependency ✔ (httpx BSD-3-Clause, tzdata Apache-2.0).
