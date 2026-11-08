# ADR-0021: Optional external editors for video and thumbnails (Canva, CapCut, InShot, Filmora, …)

**Status:** Accepted (owner request during Step 0.5, 2026-11-08) · **Date:** 2026-11-08 · **Deciders:** Owner, Claude Code

## Context
The owner wants TubeForge's **own built-in editor to stay the default**, with an **optional** choice in the dashboard to edit a video or thumbnail in an external app: Canva, InShot, CapCut, Filmora, "and any other". Findings (2026-11-08, mostly secondary sources, re-verify in Phase 9/10):
- **CapCut:** no official public editing or export API (export is manual in the app). Its built-in music and effects library is reported as **not cleared for monetised YouTube** on the free tier, and it reportedly causes Content ID claims.
- **Canva:** the Connect API exists, but key parts are enterprise or preview. Canva's **Popular Music** cannot be used in monetised content by free users. Designs mixing free and Pro content follow the stricter (Pro) licence.
- **Filmora:** the free version **adds a watermark** on export (official Wondershare support). Removing it needs a paid plan.
- **InShot:** mobile app only, no API.
- Other common choices: DaVinci Resolve (free), Kdenlive, Shotcut, OpenShot (open source), GIMP, Krita, Photopea (web), Adobe Express, Premiere Pro, Photoshop.

## Decision
**Built-in editors stay the default and the only automated path.** The built-in Video Studio (FFmpeg timeline, ADR-0011) and Thumbnail Creator are always used unless the owner picks something else.

**Optional "Edit with…" picker** in Video Studio (page 13) and Thumbnail Creator (page 16), plus an "External editors" section in Settings (page 31):

| Editor | Type | Video | Thumbnail | Launch method |
|---|---|---|---|---|
| Built-in (default) | TubeForge | ✔ | ✔ | — |
| Canva | Web | ✔ | ✔ | Opens `canva.com` in the browser |
| CapCut | Desktop / web / mobile | ✔ | ✔ | Desktop exe path or web URL |
| InShot | Mobile | ✔ | ✔ | Manual: copy files to phone |
| Filmora | Desktop | ✔ | ✔ | exe path |
| DaVinci Resolve | Desktop (free) | ✔ | — | exe path |
| Kdenlive / Shotcut / OpenShot | Desktop (open source) | ✔ | — | exe path |
| GIMP / Krita | Desktop (open source) | — | ✔ | exe path |
| Photopea / Adobe Express | Web | — | ✔ | URL |
| Premiere Pro / Photoshop | Desktop (paid, owner's licence) | ✔ | ✔ | exe path |
| **Other (custom)** | any | ✔ | ✔ | Owner enters name + exe path or URL |

All editors are **disabled until the owner enables them** in Settings. Paid apps are the owner's own subscriptions. TubeForge never pays and never stores their credentials.

**How it works: a round trip, no API needed**
1. **Hand-off.** The owner picks "Edit with X". TubeForge creates a hand-off folder `D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE\data\handoff\<project>\<session>\` containing:
   - video: the current final render (or a high-quality intermediate), the separate narration, music and visual source files, captions (SRT) and a `README.txt` with specs (resolution, fps, loudness target, max Shorts length);
   - thumbnail: the selected base image, overlay text, brand colours and fonts, required size.

   It opens the folder in Explorer and launches the app (exe path or URL). For mobile apps such as InShot, it shows "copy these files to your phone". The project goes to `EXTERNAL_EDITING`.
2. **Edit.** The owner edits in the external app.
3. **Re-import.** The owner drops the exported file into the session's `return\` folder (watched) or uploads it in the dashboard. A **declaration form is mandatory**:
   - Which app and plan (free/paid)?
   - Did you add any assets from the app's library (templates, stock, **music**, effects, fonts, AI voices or AI images)? If yes, list them with their licence.
   - Any AI-generated realistic content added? (feeds the `containsSyntheticMedia` assessment)
4. **Checks.** The re-imported file becomes a new asset (`origin = EXTERNAL_EDIT`) and runs through **the same gates as a built-in render**:
   - ffprobe QC
   - watermark detection for known free-tier watermarks (best-effort warning)
   - rights audit
   - originality and policy audits
   - thumbnail checks

   The previous approval is **invalidated** (content hash changed), so the owner approves the new version.

**Licence guard rails (built into the declaration form and audits):**
- CapCut library music and effects and Canva Popular Music are flagged **"not for monetised YouTube"** by default (rights record `commercial_use_allowed = false` unless the owner attaches licence proof). The copyright audit blocks them on monetised channels.
- Canva Pro, CapCut Pro and similar items need the owner to confirm an active paid plan, with optional proof.
- Watermarked exports produce a WARNING finding ("free-plan watermark detected — export without watermark or accept").

**Reproducibility:** an externally edited master is stored alongside (not instead of) the built-in timeline. The project records `master_source = EXTERNAL_EDIT`, and the timeline JSON is marked "superseded by external edit". The owner can go back to the built-in cut at any time.

## Free-tier status
Optional and off by default. ✔ TubeForge adds no paid dependency. Any paid editor plan is the owner's own choice and is outside TubeForge billing.

## Consequences
- Data: tables `external_editors` (registry: code, name, kind, supports_video, supports_thumbnail, launch_type EXE|URL|MANUAL, exe_path, url, enabled, notes) and `external_edit_sessions` (project, subject VIDEO|THUMBNAIL, editor_code, handoff_path, state, returned_asset_id, declaration jsonb, started_at, returned_at).
- New Video Project state `EXTERNAL_EDITING` and a thumbnail sub-flow (WORKFLOW_STATE_MACHINE §3a).
- Folder watcher in the light worker (polling every 5 s, Windows-safe). Launching an exe uses an argv list with the hand-off folder path.
- No automation of any external app's UI (respects their terms and keeps TubeForge stable).
