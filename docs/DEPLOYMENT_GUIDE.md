# Deployment Guide (Windows, native install)

**Version:** 1.0 (approved at C6, 2026-11-08) · **Date:** 2026-11-08
**Status:** Plan. The exact commands are finalised and **verified on a clean machine in Phase 15**. Steps marked 🛠 are created during the build phases.
**Target:** Windows 10 (22H2) / 11, 8 GB RAM, no GPU · **Install root:** `D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE` (changeable) · **Cost:** €0

## 1. Before you start (owner checklist)
| # | Item | Why | Cost |
|---|---|---|---|
| 1 | Windows 10 **22H2** + enrol in **Windows 10 Consumer ESU** (free option) or upgrade to Windows 11 | Security updates (ESU reportedly to Oct 2027) | Free |
| 2 | ≥ 60 GB free on **D:** | Models, renders, database | — |
| 3 | A Google account for a **test channel** and one for the real channel | Safe testing | Free |
| 4 | A Google Cloud project **without billing** (YouTube) and one for Gemini (also **no billing**) | API access, zero cost | Free |
| 5 | A Telegram account (for notifications) | Alerts | Free |
| 6 | A USB stick or second drive | Backup of the key file | — |

## 2. Install (🛠 `tubeforge.ps1 setup` automates most steps)
1. **Download** the release zip (or `git clone`) into `D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE\app\`.
2. Open **PowerShell as your user** (not admin, unless a step asks) and run:
   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   & "D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE\app\infra\windows\tubeforge.ps1" doctor
   ```
   `doctor` checks: Windows build, RAM, D: free space, time sync, PowerShell version, existing installs.
3. **PostgreSQL 16:** the installer from postgresql.org (EDB). Program files go on C: (~300 MB). **Data directory:** `D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE\pgdata`, port 5432, listen on localhost only. Choose a strong postgres password (`setup` stores it encrypted). 🛠 `setup` can run the installer silently with these options.
4. **Python & tools:** `setup` installs **uv** (user-level), which installs Python 3.12 into `app\.python\` and creates the venv. All caches are redirected to `D:\…\app\.cache`.
5. **FFmpeg:** `setup` downloads a pinned, hash-verified Windows build into `tools\` (LGPL/GPL build, used as an external program).
6. **Models** (prompted downloads, hash-checked) into `models\`: Kokoro-82M (Apache-2.0), Piper voices you choose (licences shown), faster-whisper small (int8), OpenVoice V2 (optional), Chatterbox (optional, large). Ollama is optional (`OLLAMA_MODELS` set to `models\ollama`).
7. **Database:** `setup` creates DB `tubeforge` and its login role `tubeforge` (password kept in `%APPDATA%\postgresql\pgpass.conf`), then runs migrations (all tables, roles/permissions seed). Separate auditor/read-only DB roles (`tf_auditor`, `tf_readonly`) arrive with the auditors in Phase 11; until then append-only tables are protected by triggers.
8. **Master key:** `setup` creates the master key in **Windows Credential Manager** (`TubeForge / master-key-v1`).
9. **Owner account:** `setup` asks for e-mail, display name and password (≥ 12 chars, hard to guess; typed twice, hidden). Enable 2FA later in Settings (recommended). Forgot the password: `tubeforge.ps1 reset-password` (on this PC only; signs out every session).
10. **Desktop shortcut:** `TubeForge.lnk` → `tubeforge.ps1 start` + opens `http://127.0.0.1:8765`.

## 3. First-run configuration (in the dashboard)
1. Settings › General: timezone Asia/Karachi (default), quiet hours, night render window (01:00–07:00), disk budget.
2. Channels › Add channel → **Onboarding** (10 steps): create the test channel, verify by phone, Google Cloud project (**no billing**), enable YouTube Data API v3 + Analytics API, OAuth consent screen (External, add yourself as test user), OAuth **Desktop** client, privacy policy on GitHub Pages, Connect, test private upload.
3. Cost & Usage › providers: paste your **Gemini API key** (from a no-billing project) and enter the free limits shown in AI Studio. Add **Groq** (optional) the same way. Leave Tier P providers disabled.
4. Notifications › Telegram: create a bot with @BotFather, paste the token, send `/start` to your bot, confirm the code.
5. Settings › Storage & backups: run the first backup and **export the key file** to a USB stick (passphrase ≥ 12 chars).

## 4. Daily use
- Start: double-click **TubeForge** on the desktop. Stop: `tubeforge.ps1 stop` (or the tray/menu option 🛠).
- Leave the PC on overnight when long renders are queued (night window).
- If a Testing-mode OAuth token is about to expire (7 days), click **Re-authorise** in the banner.

## 5. Moving the OAuth app to "In production" (optional, recommended after Phase 4)
Removes the 7-day token expiry. In Google Cloud Console › OAuth consent screen › Publish app. Because the YouTube scopes are sensitive, Google may show your own account an "unverified app" screen, which you can accept for your personal use. Full verification is only needed for other users (re-checked in Phase 4; marked 🟡).

## 6. Updates
`tubeforge.ps1 update`: stop → backup → pull release → `uv sync` → migrate → start. It rolls back automatically if migrations fail (restores the pre-update DB dump).

## 7. Backup & restore
- Automatic daily backup 03:00 PKT: DB dump (`pg_dump -Fc`) + encrypted secrets export into `data\backups\` (keep 14 daily, 8 weekly). Media backup is manual (masters folder copy).
- Restore: `tubeforge.ps1 restore <backup> --key-file <usb>\tubeforge.key` → prompts for the passphrase.
- A restore test runs monthly (reminder) on a scratch database.

## 8. Linux / developer setup
`infra/compose/docker-compose.dev.yml` (Postgres 16 + API + workers + Vite dev server), `uv sync`, `pnpm install`, `pre-commit install`. Used by CI and contributors, not on the owner's PC.

## 9. Uninstall
`tubeforge.ps1 uninstall`: revokes OAuth tokens (optional), deletes the API data per DP-4, removes the master key from Credential Manager, and leaves `data\` in place unless `--purge` is given.

## 10. Troubleshooting (runbooks in Phase 16)
| Symptom | Fix |
|---|---|
| Dashboard won't open | `tubeforge.ps1 status`; check the PostgreSQL service; `doctor` |
| "Needs re-authorisation" | Click Re-authorise; if it repeats every 7 days, consider §5 |
| Quota wait | Wait for the reset (shown in PKT) or reduce research searches |
| Provider limit reached | The fallback provider runs or the task waits; adjust limits in Cost & Usage |
| Render very slow | Use LONG_720, the night window, close other apps; check RAM in System health |
| Disk low on D: | Asset Library › cleanup intermediates; move old masters to another drive |
