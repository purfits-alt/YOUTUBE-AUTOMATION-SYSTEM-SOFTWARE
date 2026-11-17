# ADR-0030: Which free AI models TubeForge uses (admission rules) and Gemma 4

**Status:** Accepted (owner request, 2026-11-17) · **Date:** 2026-11-17 · **Deciders:** Owner, build agent

## Context
- **The failure:** a blueprint failed when the first model's answer was cut off, and the Gateway gave up instead of trying the other free models.
- **The owner's request:** "add free models that are authentic and give real answers according to our rules and the policies of Google, YouTube and AdSense".

## Decision
**Admission rules.** A model joins TubeForge's chains only if it meets all of these:
1. **Free with no billing.** No card on file and no trial that turns paid; Tier P stays off (two-step activation).
2. **Production status.** Not a "preview / evaluation only" or "prototyping only" model.
3. **Commercial use of outputs allowed** by the model licence and the provider's terms.
4. **Acceptable data use.** It is recorded in `provider_registry.data_use_training`. Free Gemini and Gemma may use content to improve Google products. That is accepted, and the owner sends no secrets in prompts.
5. **Reached only through an existing allowlisted host and adapter**, or through a new adapter added with its own review.

**Truthfulness and policy are not left to the model.** Every model's answer goes through the same code checks:
- JSON schemas;
- the forbidden-phrase scan (no promises of views, money or monetisation);
- the evidence rules and the A10 fact check against sources;
- the script craft checks;
- the auditors (Phase 11: YouTube monetisation and inauthentic-content policy, AdSense-friendly content);
- the owner's approvals.

A model that answers badly is skipped for the next one (Gateway fallback).

**Admitted on 2026-11-17** (checked on the official pages):
- **Gemini API free tier:** Gemini 3.8 Flash, 3.6 Flash, 3.5 Flash-Lite and 3.1 Flash-Lite (already registered), plus **Gemma 4** `gemma-4-31b-it` and `gemma-4-26b-a4b-it`.
  - Gemma 4 is "Free of charge" with no paid tier.
  - Its weights are under **Apache 2.0** (model card), and Google claims no rights in outputs.
  - It uses the same key, host and terms as Gemini. JSON mode is not documented for Gemma, so it gets the JSON-only prompt and the Gateway's checks.
- **Groq free plan:** `openai/gpt-oss-120b` and `openai/gpt-oss-20b` (production; Apache-2.0 weights).
- **Local:** Qwen2.5-1.5B-Instruct via Ollama (Apache-2.0).

**Not admitted:**
| Model or provider | Rule it fails |
|---|---|
| Groq `qwen/qwen3.8-27b` | Rule 2: a preview model, "for evaluation purposes only and should not be used in production" |
| Mistral | Rule 1: free API access withdrawn in late 2026 |
| Cerebras | Rule 1: a trial needing a payment method |
| OpenRouter `:free` models | Rule 4: several free routes go to providers that may train on prompts; 50 requests/day |
| GitHub Models | Rule 2: prototyping only, production use not allowed |

They are re-checked when their terms change.

**Chains (migration 0014).** Every free model is in every default chain, the stronger models first for reasoning work and the lighter models first for light work, with the local model always last. Chains the owner edited are kept.

**One key per provider.** A model added after the owner entered a provider's key uses that key.

## Consequences
- Jobs keep going when one model is busy, out of daily quota or answers badly.
- Answer quality varies by model; the code checks and the owner's reviews catch weak answers.
- Free-tier data use is unchanged from before. The Cost & Usage page shows every model with its licence and data-use flag.
