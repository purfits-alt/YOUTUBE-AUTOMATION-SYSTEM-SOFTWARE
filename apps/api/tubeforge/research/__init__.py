"""Research sources (CHANNEL_DISCOVERY_SPEC §1, OAUTH_SECURITY §6–7, ADR-0015).

Every outbound research request goes through :class:`tubeforge.research.fetcher.ResearchFetcher`:
an allowlist per registered source, an SSRF guard, size and time caps, and sanitising. Fetched
content is untrusted. It is stored as plain text in ``source_documents`` and reaches prompts only
inside ``<untrusted_source>`` blocks.
"""
