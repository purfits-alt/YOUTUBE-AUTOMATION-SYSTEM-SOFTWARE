# ADR-0031: Live pipeline progress in the database, read by polling

**Status:** Accepted (owner request 2026-11-18) · **Date:** 2026-11-18 · **Deciders:** Owner (request), build agent (design)

## Context
The owner reported: "there is no proper pipeline for the workflow of the whole system. If one runs its action, it stays in work in progress, not shown how much % is completed. After completion it should move to the next station automatically, and show what is coming next."

What existed:
- Stations already move on by themselves. The orchestrator engine moves a project to review when a job finishes, and approving queues the next job.
- Nothing showed how far a running job was, what came next, or that a job had stopped. A failed research or script job left the project "in work" with no sign. A failed script job had no way to run it again.
- The specs name a `job.progress` event `{job_id, kind, entity_id, pct, stage, eta_s}` (BACKEND_SPECIFICATION §2). But the event bus lives inside the API process, and jobs run in separate worker processes, so workers cannot publish to it.

## Options considered
1. **A `job_progress` table written by workers, read by the API, which the web polls (chosen).** Each progress write is its own short transaction, so the owner sees it while the job's main transaction is still open. It survives restarts and needs no new service.
2. Postgres `LISTEN/NOTIFY` from workers to the API's event bus, then SSE. Live, but nothing is stored: after a restart or a missed message the page cannot tell where a job is, and the API would need a listener task. It can be added later on top of option 1.
3. Procrastinate's own job table only. It tells "todo/doing/done", but not the percentage, the stage or the reason a job stopped.

## Decision
- **Table** `job_progress` (DATABASE_SCHEMA §9, migration 0015):
  - one row per tracked job: QUEUED → RUNNING → DONE, FAILED (with the reason) or WAITING (free-tier limit or Emergency Stop);
  - `pct` 0–100 and `stage` in plain words.
- **Queuing.** `tubeforge.queue.defer_in_transaction` adds the QUEUED row in the same transaction as the job.
- **Running.** `tubeforge.progress.track` wraps the worker job. Pipeline code calls `progress.report(pct, stage)`, which does nothing outside a tracked job. The tracked jobs are research, script, fact check, ideas, discovery and blueprint.
  - A job that ends without finishing is marked FAILED when the job runs again.
  - `pct` reaches 100 only when the job is done.
- **API.**
  - `GET /api/v1/pipeline` returns the stations, each project's station, activity, live progress and next station, and recent jobs that are not tied to a project. It also returns `refresh_s`: 3 s while something runs, 20 s otherwise.
  - `ProjectOut.progress` carries the live job of the project's current station.
- **Hints.**
  - A job still queued after 2 minutes gets a hint to check that TubeForge is running.
  - A running job with no news for 10 minutes is shown as STALLED, with a hint to restart.
  - Time left is the average of the last 10 finished runs of the same job.
- **Stations.** Stations of later phases are shown and marked with the phase they arrive in. Owner stations (check the research, approve the script, approve publishing) still wait for the owner. Progress rows never change workflow state.
- **State board** (owner request 2026-11-18, same day): each station's card shows its **Inbox** (arrived, not started; "from <previous station>"), **In progress** (with "need attention" for stopped, stalled or blocked work), **Complete** (videos past this station) and **Forwarded** ("to <next station>", videos now at the next station). Everything is computed from where each video is now, so the board can never disagree with the workflow state.
- **Retention.** Finished progress rows are deleted after 30 days (`mnt.retention.purge_job_progress`, daily).
- **Write again.** `retry-script` is a new project command (SCRIPTING, no state change), the counterpart of `retry-research`.

## Consequences
- The owner sees one production line on the **Pipeline** page, and a live bar in Script Studio and on the projects list.
- Polling costs one small query every 3 seconds while a job runs, which is negligible on the owner's PC. `job.progress` over SSE can be added later on the same table.
- Free-tier check: no new dependency or service ✔.
