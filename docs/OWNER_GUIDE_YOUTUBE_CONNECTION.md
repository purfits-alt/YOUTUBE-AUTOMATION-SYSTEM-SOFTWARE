# Owner guide — connect your test channel to TubeForge (Phase 4)

**Time:** about 30 minutes, once. **Cost:** nothing. You never add a billing account or a card.
**You need:** your Windows PC with TubeForge running (`tubeforge.ps1 start`), and a Google account.

TubeForge shows these same 10 steps under **Channels › Add channel › setup**, with a link to Google's
own help page for each one. This guide adds the exact clicks. Google changes its menus now and then.
If a button has moved, search the page for the words in **bold**.

---

## Step 1 — Google account
Use a Google account you control. A separate account for testing keeps your main account tidy.

## Step 2 — YouTube channel (your test channel)
In YouTube, open your profile picture › **Create a channel**. Name it, for example, "My Test Channel".
TubeForge only ever uploads **private** videos to it in this phase.

## Step 3 — Verify the channel by phone
Go to youtube.com/verify and verify with your phone number. This unlocks custom thumbnails
and videos longer than 15 minutes.

## Step 4 — Google Cloud project (no billing)
1. Open **console.cloud.google.com** and sign in with the same Google account.
2. Click the project picker at the top › **New project**. Name it `tubeforge-youtube` › **Create**.
3. If Google ever asks you to add billing or start a free trial, **close that screen**. TubeForge never needs it.
4. Write down the **Project ID** (for example, `tubeforge-youtube-123456`).

## Step 5 — Turn on the YouTube APIs
In the same project: **APIs & Services › Library**. Search for and **Enable**:
- **YouTube Data API v3**
- **YouTube Analytics API** (used from Phase 13)

## Step 6 — OAuth consent screen
**APIs & Services › OAuth consent screen** (newer consoles call it **Google Auth Platform**).
1. User type: **External**. App name: **TubeForge (personal)**. Support e-mail: your e-mail.
2. App home page and privacy policy: the GitHub Pages links from step 8. You can come back and add them after step 8.
3. **Audience › Test users › Add users**: add your own Google account.
4. Leave the publishing status on **Testing** for now. In Testing mode, Google ends the sign-in after
   **7 days**. TubeForge warns you a day before, and reconnecting takes about 30 seconds.

## Step 7 — OAuth client (Desktop app)
1. **APIs & Services › Credentials › Create credentials › OAuth client ID**.
2. Application type: **Desktop app**. Name: `TubeForge desktop` › **Create**.
3. Copy the **Client ID** (it ends in `.apps.googleusercontent.com`) and the **Client secret**.
4. In TubeForge, step 7 of the setup: paste them, plus the Project ID from step 4 › **Save OAuth client**.
   They are stored encrypted on your PC. Never paste them into chat or into a file in the repository.

## Step 8 — Privacy policy on GitHub Pages
Google needs a public privacy policy for the consent screen.
1. In GitHub, open the repository › `site/privacy.html` › edit (pencil icon). Replace
   **[OWNER NAME]**, **[CONTACT E-MAIL]** and **[DATE]**. For AI providers, keep "None" for now.
   Do the same in `site/terms.html`. Commit to `main`.
   *Note: this page is public, so the name and e-mail you enter are visible to anyone.*
2. Repository **Settings › Pages › Build and deployment › Source: GitHub Actions** (one time).
3. The **pages** workflow publishes the site in about a minute. Your links are:
   - `https://purfits-alt.github.io/YOUTUBE-AUTOMATION-SYSTEM-SOFTWARE/privacy.html`
   - `https://purfits-alt.github.io/YOUTUBE-AUTOMATION-SYSTEM-SOFTWARE/terms.html`
4. Paste the privacy link into TubeForge step 8 › **Save**, and into the consent screen (step 6).

## Step 9 — Connect with Google
1. In TubeForge, step 9 › **Connect with Google**.
2. Choose the test channel's Google account. Google may show **"Google hasn't verified this app"**.
   That is expected for your own personal app: **Continue**.
3. **Tick every box** (upload videos, see your YouTube account) › **Continue**.
4. You land on a TubeForge page that says **Connected to Google** › **Return to TubeForge**.
5. TubeForge shows the channel you signed in to. If it is your test channel › **Yes, this is my channel**.
   The channel is now **Connected** and **private-only**.

## Step 10 — Private test upload
1. Step 10 › **Run test private upload**. The progress bar fills within a few seconds.
2. **Open in YouTube Studio**: you see a private 5-second video, "TubeForge test upload (private)".
3. You can delete it in YouTube Studio afterwards. TubeForge never deletes YouTube content.

When steps 8 and 10 are done, the channel becomes **Active**.

---

## Afterwards
- **Quota:** each upload uses 1 of the 100 daily upload calls. The top bar shows the shared quota,
  which resets at **13:00 PKT** in winter and **12:00 PKT** in summer.
- **Disconnect:** Channels › the channel › Disconnect. This revokes access at Google and deletes the stored
  YouTube data within 7 days. You can also remove access in your Google account under
  **Security › Third-party apps**.
- **In production (optional):** in the consent screen, **Publish app** removes the 7-day expiry. Google may keep
  showing your own account the "unverified app" screen, which you can accept for personal use. Verification
  is only needed if other people would use your app, and they won't.

## Report back
Send me (Claude) what you saw in steps 9 and 10, or any error text. **Do not send the client secret.**
I record the result of the manual test in `PROJECT_PROGRESS.md`.
