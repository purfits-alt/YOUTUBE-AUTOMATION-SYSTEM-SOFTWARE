# ADR-0019: Owner voice recording and owner-only voice cloning

**Status:** Accepted (owner request at C2, 2026-11-08) · **Date:** 2026-11-08 · **Deciders:** Owner, Claude Code

## Context
The owner asked for an option to record their own voice **and** to clone it, so that narration in their voice can be generated without recording every line. Verified on 2026-11-08:
- **YouTube policy:** the official "Disclosing altered or synthetic content" help page lists "*Cloning one's own voice to create voice overs or dubs*" among the examples that **creators don't have to disclose** ([YouTube Help 14328491](https://support.google.com/youtube/answer/14328491)). Cloning *someone else's* voice is a disclosure case and is forbidden in TubeForge (NG-4).
- **OpenVoice V2** (MyShell): "Starting from April 2024, both V2 and V1 are released under MIT License. Free for commercial use." It has a tone-colour converter that is independent of language. Native base languages: EN, ES, FR, ZH, JA, KO.
- **Chatterbox Multilingual V3** (Resemble AI): MIT licence. 0.5B parameters. Zero-shot cloning in 23 languages, **including EN, ES, FR, DE and Hindi, but not Urdu**. A built-in PerTh audio watermark. The repository is archived (no support or updates).
- H-LITE has 8 GB RAM and no GPU. Model fine-tuning (e.g. training a Piper voice) is not realistic on CPU.

## Options considered
1. **OpenVoice V2 tone-colour conversion applied to Kokoro/Piper output** (light, all 5 languages).
2. **Chatterbox Multilingual V3 zero-shot cloning** (better likeness, slower on CPU, no Urdu, archived).
3. Train a custom Piper voice on the owner's recordings (needs a GPU; deferred to H1+).
4. Paid cloud cloning (e.g. ElevenLabs) — Tier P, disabled.

## Decision
Voice options in the Voiceover Studio, in order of preference:

| Rank | Option | Engine | Languages | H-LITE speed |
|---|---|---|---|---|
| 1 | **Owner records narration** | Browser recorder, noise reduction, per-scene retakes | All | Real time |
| 2 | **Owner voice clone, "converter" mode** (default clone engine) | Kokoro/Piper TTS → **OpenVoice V2 tone-colour converter** with the owner's voice profile | EN, ES, FR, DE, UR | Moderate |
| 3 | **Owner voice clone, "zero-shot" mode** (optional) | **Chatterbox Multilingual V3** | EN, ES, FR, DE (no UR) | Slow (batch / overnight) |
| 4 | Stock TTS voice | Kokoro / Piper (licence-gated) | Per voice | Fast |
| — | Paid cloud cloning | Adapter only, Tier P, disabled | — | — |

**Anti-misuse and consent controls (mandatory):**
- **Owner only.** A voice profile can only be built from audio **recorded live inside TubeForge**. File upload of reference audio is not allowed, which blocks cloning third parties from downloaded audio.
- **Consent recording.** The owner reads a consent statement that includes a random one-time code shown on screen. The system checks the code with STT and checks that the consent audio and the training samples are the same speaker (speaker-embedding similarity above a threshold). The consent record (text, code, audio hash, timestamp) is stored.
- **Storage.** Voice profiles (embeddings and samples) are biometric-like data. They are encrypted at rest (ADR-0012), never exported, never sent to cloud providers, and deletable with one click (which also deletes derived audio caches).
- **Labelling.** Every generated clip is tagged `voice_source = owner_clone` in its rights record. Chatterbox output also carries its built-in watermark.
- **Disclosure.** Using the owner's *own* cloned voice does **not** by itself set `containsSyntheticMedia = true` (per YouTube's guidance). The AI-disclosure assessment records this reason with the help-page link. Other realistic synthetic elements are still assessed separately.
- **Originality scoring** (F3): owner-recorded voice > owner clone > stock TTS. A clone does not replace the need for the owner's own insights and value-add.

## Free-tier status
All local and free. ✔ The paid cloud cloning adapter is disabled (Tier P).

## Licences
OpenVoice V1/V2: MIT (verified in the README, 2026-11-08). Chatterbox: MIT (code verified in LICENSE). **Model-weight licences on Hugging Face are re-checked in the Phase 8 spike** before enabling. Kokoro: Apache-2.0. Piper voices: per voice.

## Consequences
- Adds an encrypted `voice_profiles` table and a `voice_consents` table (Step 0.5 DB schema).
- Clone quality on CPU must be measured in Phase 8. If OpenVoice quality is poor in a language, that language falls back to owner recording or stock TTS.
- Chatterbox is archived, so it is pinned by hash and treated as frozen. If it breaks, the converter mode still works.

## References
- `docs/FREE_TIER_PROVIDER_MATRIX.md` §3.3a · `docs/PRODUCT_REQUIREMENTS.md` US-5.3
