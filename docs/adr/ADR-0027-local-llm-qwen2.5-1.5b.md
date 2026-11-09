# ADR-0027: Local LLM fallback — Qwen2.5-1.5B-Instruct on Ollama

**Status:** Accepted (implementation decision, Phase 5; reported in the Phase 5 report) · **Date:** 2026-11-09 · **Deciders:** Build agent, confirmed at phase approval

## Context
The roadmap asks for an Ollama model that is small enough for the owner's 8 GB PC (H-LITE: about 1.5–2.5 GB for the model), with an Apache-2.0 or MIT licence so the output can be used on monetised channels (FREE_TIER_PROVIDER_MATRIX §3.2). The model is the last step of every provider chain: it keeps work going when the free cloud tiers are at their limits, and it is the only provider allowed for **local-only** channels.

## Options considered
1. **Qwen2.5-1.5B-Instruct** (chosen). The licence is **Apache-2.0** (model card metadata, checked 2026-11-09). It is about 1 GB at Q4, multilingual (EN/ES/FR/DE, basic UR) and can produce JSON.
2. Qwen2.5-3B-Instruct: better quality, but the licence is **qwen-research** (not for commercial use). Rejected.
3. Llama 3.2 1B/3B: the Llama Community License is not an approved licence (ADR-0018 licence gate). Rejected.
4. Gemma (1B): the Gemma terms are not on the approved list. Rejected.

## Decision
- The registry row is `ollama:qwen2.5:1.5b`, Tier L, licence Apache-2.0, `commercial_use = YES`, `data_use_training = false` (nothing leaves the PC).
- It is the last step of every default chain in `gateway/core.py`.
- The owner installs it with `ollama pull qwen2.5:1.5b`.
- The Ollama tag could not be verified from the build machine, because `ollama.com` was unreachable. The owner's first pull confirms it.

## Consequences
- Local answers are weaker than Gemini or Groq. The gateway uses the model only when a cloud provider is at its limit, fails, or is blocked by policy. The task's schema validation and its one repair attempt still apply.
- RAM: about 1–1.5 GB while loaded. Ollama unloads idle models, which fits the H-LITE budget.

## Free-tier status
Introduces no paid dependency ✔ (Ollama MIT, Qwen2.5-1.5B Apache-2.0).
