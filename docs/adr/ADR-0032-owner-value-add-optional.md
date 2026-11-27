# ADR-0032: The owner's own value is optional; empty owner parts never reach the voice-over

**Status:** Accepted (owner decision 2026-11-27) · **Date:** 2026-11-27 · **Deciders:** Owner

## Context
- The owner shared the approved PurfitsWellnessHub script ("How Late Meals Impact Deep Sleep and Recovery"). It still contained two `[[OWNER: …]]` prompts and had already reached the Storyboard inbox.
- Approval checked the separate "Your own value" fields but not the prompts inside the script text. Left unchanged, the voice-over would have read "OWNER: Share your experience…" aloud.
- The owner then decided: *"build my add value as optional (TubeForge never needs my addition, but optionally it is available)"*. They also asked for **3 AI suggestions** per owner part, from Gemini first, to pick from, while keeping the free-text box.

## Decision
1. **Value-add fields are optional.** The `owner_value_add` guard's default minimum (`min_value_add_fields`) is now 0, down from 1. The owner can still set a minimum in the orchestrator settings.
2. **Owner parts are optional; raw prompts are never spoken.**
   - After every A11 draft, `scripts.lift_owner_slots` takes empty `[[OWNER: …]]` places out of the spoken text and keeps their prompts in `owner_slots` as optional suggestions. The draft is complete without the owner.
   - The new guard **`owner_slots_filled`** on SCRIPT_REVIEW → STORYBOARDING refuses a script that still contains a raw `[[OWNER: …]]`. Its message names the one-click fix.
3. **Script Studio › "Your parts (optional)"** lists each empty part:
   - the owner writes their words or picks a suggestion;
   - **Put my words in** saves a new version;
   - **Remove my empty parts** takes them out, keeping the prompts as suggestions.
4. **3 suggestions per part (A11, second prompt `A11_OWNER_PARTS` v1.0, job `content.part_options`).** They come through the Gateway's free chain, Gemini first, within A11's own limits. To stay honest and within YouTube's authenticity rules, A11 never writes an experience as the owner's own. The three kinds are:
   - **Your sentence (FILL_IN):** first person, but every personal detail is a `___` blank. It cannot be inserted until the blanks are filled.
   - **Ask viewers (QUESTION):** not first person, ends with "?".
   - **General line (NEUTRAL):** not first person, only facts from the brief.

   Code drops any option that breaks these rules or contains a forbidden phrase. A saved owner version is fact-checked by A10 as usual.
5. **Reopen.** The new owner edge STORYBOARDING → SCRIPT_REVIEW (`reopen-script`) brings an approved script back for changes. Example: the shared script, to fill or remove its parts before the storyboard (Phase 8 step B).

## Consequences
- Scripts can be approved without the owner's words. Originality, which YouTube rewards for monetisation, then depends on the script and later on the auditors (Phase 11 quality and originality checks). The UI keeps saying that the owner's own experience is the strongest addition.
- The craft check still requires owner places (≥ 2 long-form, ≥ 1 Short). They now live as suggestions, so a lifted draft passes.
- Free-tier check: no new dependency or paid service ✔ (the suggestions use the existing free Gateway chain).
