# Thumbnail & SEO Specification

**Version:** 1.0 (approved at C5, 2026-11-08) · **Date:** 2026-11-08
**Agents:** A18 Thumbnail Design, A19 YouTube SEO (+ disclosure assessment), A22 Policy Auditor (misleading checks)
**Verified sources (2026-11-08):** [Custom thumbnails help](https://support.google.com/youtube/answer/72431) · [thumbnails.set](https://developers.google.com/youtube/v3/docs/thumbnails/set) · [videos resource](https://developers.google.com/youtube/v3/docs/videos) · [Altered/synthetic disclosure help](https://support.google.com/youtube/answer/14328491)

## 1. Thumbnails

### 1.1 Technical requirements
| Item | Long-form video | Short | Source |
|---|---|---|---|
| Aspect ratio | 16:9 | 9:16 | Help 72431 |
| Recommended resolution | **3840 × 2160** | **2160 × 3840** | Help 72431 |
| Minimum | width ≥ 640 px | height ≥ 640 px | Help 72431 |
| API file limit | ≤ **50 MB**, JPEG or PNG | same (Shorts via API after processing completes, `shortsAspectRatio`) | thumbnails.set, revision history Sep/Nov 2026 |
| TubeForge export | JPEG quality 90, sRGB, 3840×2160 (falls back to 1920×1080 if the source is smaller; never upscales beyond 2× source) | 2160×3840 | — |
| Channel requirement | Channel must be verified for custom thumbnails | same | Help 72431 |

### 1.2 Generation (A18 + composer)
0. **Promise consistency:** overlay text and title express the approved **packaging promise**, which the script delivers in its first 15 s (Shorts 3 s). If the owner picks a thumbnail or title with a different promise, the orchestrator asks whether A11 should update the intro. Approval is blocked until the promise and intro match (A22 PROMISE_NOT_DELIVERED).
1. A18 proposes 3–5 concepts (AGENT_PROMPTS A18) with an honesty check.
2. The composer renders each concept:
   - **Base:** a frame from the owner's own render (frame-sharpness score ≥ threshold), an owner photo, or a procedural background.
   - **Overlay text:** ≤ 5 words, brand headline font, stroke or shadow for contrast, RTL shaping for Urdu (HarfBuzz via Pillow raqm).
   - **Layout:** one of LEFT_TEXT / RIGHT_TEXT / CENTER / SPLIT with safe margins (5 %).
3. The owner can also upload a thumbnail, or edit in an external app (ADR-0021). Either way it goes through the same checks.

### 1.3 Checks (all must pass, or show a warning, before selection)
| Check | Method | Pass rule |
|---|---|---|
| Dimensions and aspect | Pillow | Exact aspect ±1 %, min size met |
| File size and format | stat / mime | ≤ 50 MB, JPEG or PNG |
| Text contrast | WCAG contrast of text vs local background | ≥ 4.5 : 1 |
| Small-size readability | Downscale to 168×94 (mobile list size) and 320×180. Measure text height in px and edge contrast. | Text cap height ≥ 9 px at 168×94; warning below |
| Text amount | Word count | ≤ 5 words recommended (warning > 6) |
| Faces/people (if used) | Must be the owner (owner photo) or none | Owner declaration |
| Misleading presentation | A22 classifier: overlay text vs script/title claims; fake UI elements (play buttons, "LIVE" badges, notification icons) by template blacklist | No CRITICAL finding |
| Competitor imagery | Only owner, procedural or licensed sources (rights record) | Rights OK |
| Safe areas (Shorts) | Key text within the middle 70 % vertically | Warning |

### 1.4 Comparison & selection
Side-by-side view at full size, 320×180 and 168×94, in light and dark backgrounds. The owner selects one (`thumbnails.selected`). The selection is part of the upload approval hash.

## 2. SEO package (A19)

### 2.1 Field rules (verified API limits + TubeForge rules)
| Field | API limit (verified) | TubeForge rule |
|---|---|---|
| Title | ≤ **100 characters**, no `<` or `>` | 3–5 options. Recommended ≤ 70 chars. No ALL-CAPS words except acronyms. No misleading claims. Primary keyword naturally near the start. |
| Description | ≤ **5000 bytes**, no `<` or `>` | First 2 lines summarise. Then chapters, sources (factual videos), attribution lines from rights records (required), a short "about the channel" line. Byte counter in the UI. |
| Tags | ≤ **500 characters** total; commas count; tags with spaces count their quotes | 5–15 relevant tags. Never irrelevant or competitor-brand tags. |
| Hashtags | — | ≤ 3 recommended (shown above the title by YouTube); ≤ 15 max |
| Chapters | (YouTube rule, enforced in description text) | First at 0:00. ≥ 3 chapters. Each ≥ 10 s. Ascending. Validated against the **final** render duration. Long-form only. |
| Category | `snippet.categoryId` | From `videoCategories.list` (cached), owner-confirmable |
| Default language / audio language | `snippet.defaultLanguage`, `defaultAudioLanguage` | = channel content language |
| Playlists | via `playlistItems.insert` (needs force-ssl) | Suggestions by pillar. The owner picks. |
| Made for kids | `status.selfDeclaredMadeForKids` | **Owner decides explicitly.** No default. A19 only provides a hint. Upload is blocked while it's NULL. |
| Synthetic content | `status.containsSyntheticMedia` | Disclosure assessment (§3). Owner confirms. Always sent explicitly. |
| Privacy / publishAt | `status.privacyStatus`, `status.publishAt` | Chosen in the approval (ADR-0016). `publishAt` ≥ now + 15 min, private only. |

### 2.2 Honesty / misleading-metadata check (A22 + rules)
- Every title and thumbnail claim must be supported by the script (claim overlap check). Numbers in the title must appear in the script or brief.
- A blacklist of deceptive patterns: "(NOT CLICKBAIT)", fake "LIVE", "100% guaranteed", "you won't believe", fake giveaways, impersonating another creator or brand.
- Description must not contain links the owner hasn't approved, or affiliate links without a disclosure line.

### 2.3 Localisation (optional)
For multilingual channels, `localizations` (title and description per language) can be produced by A19 and owner-reviewed. Translation alone is not counted as owner value-add (F3).

## 3. AI-disclosure assessment (`containsSyntheticMedia`)
Inputs:
- asset origins in the final cut (TTS, OWNER_CLONE, PROCEDURAL, AI_IMAGE, STOCK, OWNER_*, EXTERNAL_EDIT);
- the external-edit declaration of AI content;
- script flags (depicting real people).

| Element | Default assessment | Basis |
|---|---|---|
| Owner's own voice clone | Not a disclosure trigger | Help 14328491 ("Cloning one's own voice to create voice overs or dubs") |
| TTS narration (non-cloned generic voice) | Not a trigger by itself (not depicting a real person) | A/S definition is about realism and real people or events |
| Motion graphics, animation, charts, kinetic text | Not a trigger (clearly unrealistic) | Help 14328491 |
| Colour, beauty, blur filters; audio repair; upscaling | Not a trigger | Help 14328491 |
| Realistic AI image or video of a real person, event or place, or a realistic scene that didn't happen | **Trigger → true** | Revision history 30 Oct 2024; Help 14328491 |
| Voice clone of anyone else | Forbidden in TubeForge (NG-4) | — |
| External edit with declared "AI realistic content" | **Trigger → true** unless the owner explains otherwise | Declaration |

Output: `recommended_value` + per-element reasons + rule references. The owner confirms or changes it (the change is logged). The confirmed value is sent on upload. If realistic synthetic content is present and the owner sets `false`, the Policy Auditor raises **CRITICAL DISCLOSURE_MISSING** (overridable only with a reason).

## 4. Acceptance tests (Phase 10)
- Title 101 chars → 422. Description of 5001 bytes (Urdu text with 1700 chars) → 422.
- Tag list where "Foo Baz" counts as 9 chars → the counter matches the API rule.
- Chapters: missing 0:00 / < 10 s / beyond duration → validation errors.
- Thumbnail fixtures: low contrast, tiny text, wrong aspect, > 50 MB → detected.
- Disclosure fixtures (15 cases) → expected `recommended_value`.
- Upload preflight refuses a NULL made-for-kids decision (I-6).
