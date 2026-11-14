# Video Production Specification

**Version:** 1.0 (approved at C5, 2026-11-08) · **Date:** 2026-11-08
**Agents:** A11–A18, A20 · **ADRs:** 0010 (visuals), 0011 (FFmpeg), 0019 (voice clone), 0020 (stock), 0021 (external editors)

## 1. Project contents (every video project)
| Item | Stored in |
|---|---|
| Research brief + sources + fact-check | `research_briefs`, `source_documents`, `fact_check_claims` |
| Script (versioned), hook | `script_versions` |
| Owner value-add record | `owner_value_add` |
| Storyboard, scenes, visual instructions | `storyboards`, `scenes` |
| Visual assets with rights | `media_assets` + `asset_rights` |
| Narration (owner, clone or TTS) | `narration_segments` |
| Music/SFX with rights | `media_assets` (AUDIO_MUSIC/SFX) + rights |
| Timeline JSON (versioned) | `timeline_versions` |
| Captions | `caption_tracks` |
| Final render + QC report | `render_jobs`, `media_assets` |
| ≥ 3 thumbnails | `thumbnails` |
| SEO package + disclosure | `seo_packages`, `disclosure_assessments` |
| Audit reports | `audit_reports` |
| External edit sessions (optional) | `external_edit_sessions` |

## 1a. Script & retention craft (owner requirement at C5)
| Element | Rule | Agent | Checked by |
|---|---|---|---|
| Packaging promise | Title idea + thumbnail text + one-sentence promise drafted with the idea; the contract for intro, thumbnail and title | A08 (draft), owner (approve) | A22 PROMISE_NOT_DELIVERED |
| Promise in intro | Addressed within the first 15 s (Shorts 3 s) and paid off in the body | A11 | Validator + A22 (on the final render transcript) |
| Opening hook | 10–15 s (≈ 25–40 words) long-form; 1–3 s Shorts; techniques: surprising fact, question, stakes, cold-open story, bold true claim, before/after, visual reveal | A11, A12 (hook scene with the strongest visual) | Validator |
| Mid-video re-hooks | At ≈ 25/50/75 % and every 60–120 s in videos > 8 min; open loop, pattern interrupt, twist, progress marker, mini-cliffhanger, preview | A11 (words), A12/A13 (visual pattern interrupt) | Validator |
| Curiosity & suspense | Only where honest and appropriate; every open loop closed | A11 | Validator + A22 OPEN_LOOP_UNCLOSED / FAKE_SUSPENSE |
| Story structure | Setup → tension → exploration → reveal → payoff → next step | A11 | Owner review |
| Human voice | Conversational, varied sentences, rhetorical questions, emotional beats, callbacks, no AI filler phrases, owner stories in `[[OWNER: …]]` slots | A11 + owner | Banned-phrase scan; owner rating |
| Retention data loop | After publish, A27 compares audience-retention dips (Analytics, own channel) to hook/re-hook positions and suggests improvements | A27 | Owner accepts |

## 1b. Craft validators and value-add score (implemented in Phase 7, `tubeforge/content/`)
**Craft validators** (`content/craft.py`) run on every script version, from the agent or the owner. Durations are measured from the words at the channel's speaking rate (default 150 wpm), never taken from the model.

| Code | Rule | Severity |
|---|---|---|
| HOOK_LENGTH | Long-form hook 10–15 s; Short hook ≤ 10 words (1–3 s) | ERROR |
| HOOK_GREETING | No greeting ("hi", "hello", "welcome") before the hook | ERROR |
| PROMISE_MISSING / PROMISE_LATE | Packaging promise addressed by 15 s (Shorts 3 s) | ERROR |
| REHOOK_MISSING | Long-form re-hooks in the 20–30 %, 45–55 % and 70–80 % bands | ERROR |
| REHOOK_SPARSE | Videos over 8 min: no gap over 120 s (+10 %) without a re-hook | WARNING |
| OPEN_LOOP_UNCLOSED | Every open loop closed in a later, existing section | ERROR |
| BANNED_PHRASE | AI filler and pressure phrases, plus the channel's recent script phrases | ERROR |
| FORBIDDEN_PROMISE | Forbidden-phrase rules (no promises of money, views or virality) | ERROR |
| DURATION / SHORT_TOO_LONG | Within ±10 % of the target; Shorts ≤ 180 s | ERROR |
| OWNER_SLOTS | ≥ 2 `[[OWNER: …]]` slots long-form, ≥ 1 Short | ERROR |
| FACT_REF_UNKNOWN | Every `fact_refs` id is a claim of the approved brief | ERROR |

An agent draft with ERROR findings gets one repair call. For owner edits the findings are shown in Script Studio.

**Owner value-add score (0–100)** (`content/value_add.py`): it measures what the owner adds that AI cannot.
- Points: own experience 25, own opinion 20, own data 20, own examples 15 (each text counts from 30 characters); own footage 12, own photos 8.
- Voice is scored in the originality score, not here.
- The SCRIPT_REVIEW → STORYBOARDING guard needs at least `min_value_add_fields` filled fields (default 1).

## 2. Render profiles (defaults; per project in `render_profile`)

| Profile | Resolution | FPS | Video codec | Audio | Loudness target | Notes |
|---|---|---|---|---|---|---|
| LONG_1080 (default) | 1920×1080 | 30 | H.264 High, CRF 20, preset `faster` (H-LITE) | AAC-LC 48 kHz stereo 192 kbps | −14 LUFS integrated, true peak ≤ −1 dBTP, LRA ≤ 11 | Night render window |
| LONG_720 (fast) | 1280×720 | 30 | H.264 CRF 21 `veryfast` | same | same | For slow PCs |
| SHORT_1080 | 1080×1920 | 30 | H.264 CRF 20 `faster` | same | same | Duration ≤ 180 s (Y9). Captions burned in by default. |
| PROXY | ½ of the target resolution | 30 | H.264 CRF 28 `ultrafast` | AAC 96 kbps | not normalised | Preview only |

The −14 LUFS figure is a widely used target for online video. YouTube applies its own normalisation, so the value is configurable (`render_profile.loudness_lufs`) and is not presented as a YouTube requirement.

## 3. Timeline JSON (`packages/shared/schemas/timeline.json`, schema version 1)
```json
{
  "schema_version": "1",
  "canvas": {"width": 1920, "height": 1080, "fps": 30, "background": "#000000"},
  "duration_s": 612.4,
  "tracks": [
    {"id": "video", "type": "video", "clips": [
      {"id": "c1", "asset_id": "…", "in_s": 0, "out_s": 6.5, "start_s": 0,
       "effects": [{"type": "ken_burns", "from": {"x":0,"y":0,"zoom":1.0}, "to": {"x":0.1,"y":0.05,"zoom":1.15}}],
       "transition_in": {"type": "fade", "duration_s": 0.4}}]},
    {"id": "overlay", "type": "graphics", "clips": [
      {"id": "t1", "template_id": "kinetic_title_v2", "params": {"text": "…", "font": "Inter", "color": "#FDE68A"}, "start_s": 0.5, "duration_s": 3}]},
    {"id": "narration", "type": "audio", "clips": [{"id": "n1", "asset_id": "…", "start_s": 0.3, "gain_db": 0}]},
    {"id": "music", "type": "audio", "clips": [{"id": "m1", "asset_id": "…", "start_s": 0, "gain_db": -18, "duck_under": "narration", "duck_db": -10}]},
    {"id": "captions", "type": "captions", "caption_track_id": "…", "burn_in": false}
  ]
}
```
Validation: every `asset_id` exists **and has a rights record allowed for the channel**, clip times are within asset durations, no overlaps on single-lane tracks, and the total duration fits the format.

## 4. Pipeline stages

| Stage | Agent | What happens | Output |
|---|---|---|---|
| Script | A11 (+A10) | Draft with owner slots, fact refs, anti-template phrase list | script_versions |
| Owner value-add | Owner | Fill opinion, experience, data, examples. Choose voice source. | owner_value_add (score) |
| Storyboard | A12 | Scenes with verbatim narration and durations | scenes |
| Visual plan | A13 | Treatment per scene (template, chart, kinetic text, owner media, stock suggestion) | visual plan |
| Visual assets | A14 + owner | Procedural renders; owner uploads; stock imports (owner-selected) | media_assets + rights |
| Voiceover | A15 | Owner recording → noise reduction (RNNoise/ffmpeg `afftdn`) + loudness. Clone: Kokoro/Piper → OpenVoice converter, or Chatterbox zero-shot. TTS: licensed voice. | narration_segments |
| Assembly | A16 | Timeline JSON + proxy render | timeline_versions, PROXY render |
| Rough-cut review | Owner | Approve, request changes, or **Edit with… (optional external editor)** | approval |
| Final render | A17 | Segmented render (≈ 60 s segments, long-form), concat, loudnorm 2-pass, QC | FINAL render |
| Captions | A20 | Script-aligned SRT/VTT; Shorts burn-in | caption_tracks |
| Packaging | A18, A19 | Thumbnails, SEO, disclosure | thumbnails, seo_packages |

## 5. Visual styles available on H-LITE (procedural template registry v1)
`kinetic_title`, `lower_third`, `bullet_reveal`, `quote_card`, `bar_chart`, `line_chart`, `pie_chart`, `number_counter`, `map_highlight` (public-domain base maps only), `timeline_steps`, `split_compare`, `ken_burns_photo`, `screen_recording_frame`, `owner_cam_frame`, `progress_bar`, `subscribe_reminder_soft` (no fake buttons).
Rules: any one template ≤ 40 % of a video's scenes, and the template sequence must differ from the last 5 videos (A13 check). The goal is variety, to avoid the "template look" (F3).

## 6. Voice options (ADR-0019)

| Option | When | Quality / speed on H-LITE |
|---|---|---|
| Owner recording | Always available (recommended) | Best originality. Real time. |
| Owner clone, converter | Owner profile READY; any of the 5 languages | Moderate; ≈ 1–3× real time (measure in Phase 8) |
| Owner clone, zero-shot | READY profile; EN/ES/FR/DE | Slow; batch at night |
| TTS (Kokoro EN/ES/FR, Piper DE/UR) | Commercial-OK voices only for monetised channels | Fast |

Recording guidance shown in the Voiceover Studio: a quiet room, 15–20 cm from the mic, record each scene separately, −12 dBFS peaks, and a 3-s room-tone capture for noise reduction.

## 7. Music & SFX
Sources:
- the owner's own music;
- the **YouTube Audio Library** (the owner downloads tracks manually in Studio and records the licence, including attribution if required);
- CC0 sources;
- procedurally generated beds;
- stock imports with a licence.

**Not allowed by default:** CapCut library music, Canva Popular Music (ADR-0021), and any track without a rights record. Music ducks under narration by 10 dB.

## 8. Quality control (A23, after every FINAL render and on re-imported external edits)

| Check | Tool | Threshold |
|---|---|---|
| Container, streams | ffprobe | 1 video + 1 audio stream; codec as profile |
| Duration | ffprobe | Matches timeline ±0.1 s (external edit: within the declared format limits) |
| Resolution / FPS | ffprobe | As profile |
| Loudness | `ebur128` | Integrated within target ±1 LU; true peak ≤ −1 dBTP |
| Black frames | `blackdetect=d=2:pix_th=0.10` | No unplanned run > 2 s |
| Frozen frames | `freezedetect=n=-60dB:d=3` | No unplanned run > 3 s (excluding intended stills) |
| Silence | `silencedetect=n=-50dB:d=3` | No gap > 3 s outside intended pauses |
| A/V sync | narration start offsets vs timeline | ≤ 80 ms drift |
| Captions | cue times vs narration alignment | ≤ 200 ms |
| Shorts | aspect 9:16 or 1:1, ≤ 180 s | hard |
| Watermark (external edits) | template match on known free-plan watermarks (best effort) | warning |

## 9. Shorts specifics
- From an idea (SHORT format) or **cut from the owner's own long-form** (parent_project_id). Never from third-party videos.
- Hook within the first 2 s, burned-in captions, safe areas (top 10 %, bottom 20 % kept clear of key text).
- The repetition guard compares against the channel's last 20 Shorts (script similarity + template sequence).

## 10. External editors (optional, ADR-0021)
Hand-off folder → owner edits in any enabled app → re-import with a declaration → same QC, rights, policy and thumbnail gates → new approval. The built-in cut is always kept.

## 11. Performance expectations on H-LITE (to be measured in Phase 9 and recorded here)
| Job | Estimate (unverified) |
|---|---|
| 10-min long-form FINAL 1080p30 render | 30–90 min (CPU-dependent) — night window |
| Proxy (540p) | 5–15 min |
| TTS 10 min narration (Kokoro) | 5–15 min |
| Voice-clone converter 10 min | 15–40 min |
| Captions alignment 10 min | 5–10 min |
These numbers are placeholders until benchmarks run on the owner's PC. The UI shows measured ETAs.

## 12. Acceptance tests (Phases 8–9)
- The same timeline rendered twice gives the same duration, streams and resolution (determinism).
- A timeline containing an asset without rights → save is refused (`RIGHTS_MISSING`).
- Loudness of a fixture render lands within ±1 LU of target.
- Defect fixtures (black, freeze, silence, wrong aspect) are each detected.
- A Short > 180 s → QC hard fail.
- A narration with source OWNER_CLONE fails without a READY consent record.
