# ADR-0028: Product site at `tubeforge.semrs.com` (web address only)

**Status:** Accepted (owner decision, 2026-11-14) · **Date:** 2026-11-14 · **Deciders:** Owner

## Context
The owner plans to sell TubeForge, possibly as white-label software. They own the semrs.com brand and created the subdomain `tubeforge.semrs.com` on their existing Hostinger hosting for it.

CLAUDE.md says TubeForge is a standalone project: it must never use, copy or connect to SEMRS OS or any other product's code, database, auth, APIs, agents, notifications, infrastructure or deployment. The owner's latest instruction ranks above that rule. This ADR records the exception and keeps it narrow.

## Decision
- `tubeforge.semrs.com` is TubeForge's **public product site**. It is static pages only: product page, waitlist, guides, privacy policy and terms.
- It is hosted on the owner's existing Hostinger plan for semrs.com, so it needs no new paid service.
- What the exception allows: the **web address and static web hosting**, nothing else.
- **Live demo at `/demo/`** (owner request, 2026-11-14): the dashboard built with `pnpm build:demo`. Every Phase 1–6 page answers from sample data in the visitor's browser (MSW), with no server, no real logins, no live connection to a server, and nothing saved or sent. A banner says so.
- Still forbidden:
  - The TubeForge app, its API, database, logins or any customer or channel data on that hosting, or in any SEMRS system.
  - SEMRS OS code, accounts, auth, APIs, agents or notifications in TubeForge.
  - Analytics or trackers from SEMRS on the site, unless the owner decides so separately.
- TubeForge itself keeps running on the owner's PC (local-first).
- A later hosted service (SaaS) would need its own ADR, with separate hosting.
- Open, for the owner to decide:
  - the selling model: self-hosted white-label (recommended) or SaaS;
  - the licence for future versions: the repository is public under MIT today.

## Consequences
- The privacy and terms pages can move from GitHub Pages to `tubeforge.semrs.com/privacy` and `/terms`. The Google OAuth consent screen then points to the new links.
- HTTPS is required: a free SSL certificate on Hostinger.
- The CLAUDE.md standalone rule now names this exception.

## Free-tier status
Introduces no paid dependency ✔ (uses the owner's existing hosting plan and free SSL).
