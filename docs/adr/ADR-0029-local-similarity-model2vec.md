# ADR-0029: Local similarity — model2vec static embeddings (potion-multilingual-128M)

**Status:** Accepted (implementation decision, Phase 7 step A; reported in the Phase 7 report) · **Date:** 2026-11-14 · **Deciders:** Build agent, confirmed at phase approval

## Context
Phase 7 needs "similarity service (local embeddings)" for several checks:
- an idea is a duplicate at ≥ 0.85 (WORKFLOW_STATE_MACHINE §2);
- a variation of the owner's own video must be ≤ 0.70 similar to it (US-4.6);
- a script similar to recent videos gets a warning above 0.85 and a critical finding above 0.92 (AUDIT_AND_POLICY_SPEC).

The model must:
- run on the owner's 8 GB H-LITE PC without a GPU;
- be free with a commercial-OK licence;
- cover the channel languages: en, es, fr, de, ur.

Nothing may leave the PC.

## Options considered
1. **model2vec (MIT) + minishlab/potion-multilingual-128M (MIT)** (chosen).
   - Static embeddings: a token lookup plus pooling. They run on the CPU with numpy, with no neural runtime.
   - Multilingual.
   - Size: about 512 MB on disk, and about 256 MB in memory when loaded at half precision.
2. fastembed (Apache-2.0) with an ONNX transformer model. Better quality, but it needs onnxruntime, and it is slower on H-LITE.
3. sentence-transformers. It needs PyTorch (more than 1 GB) and is too heavy for H-LITE.
4. An Ollama embedding model (e.g. nomic-embed-text). It needs Ollama installed and running, which the owner does not have.
5. Character trigrams only. No model, but they miss paraphrases ("How I budget as a student" vs "My student budget explained" scores 0.49).

## Decision
- `tubeforge.content.similarity` offers `pairwise`, `against`, `nearest` and `too_similar_pairs`, with two methods on the same 0–1 cosine scale:
  - **model2vec** when the model is installed;
  - **trigram** otherwise (fresh installs, CI, a failed download). Nothing breaks without the model.
- The model is downloaded once by `tubeforge-admin fetch-models`, which `tubeforge.ps1 setup` runs. A failed download only warns.
  - Revision pinned: `73908c3438cf03b6a01bcb9611d62b23d0726f08`.
  - SHA-256 checked for `model.safetensors` and `tokenizer.json`; sizes checked for the rest.
  - HTTPS only, and only to `huggingface.co` and its CDN (`*.hf.co`) via redirects.
  - Files are stored in `<data>/models/potion-multilingual-128M`.
  - This is a setup-time download, like `ollama pull` (ADR-0027). It is not part of the research fetcher.
- The model is loaded lazily, once, at float16.
- The thresholds stay configurable. `idea_similarity_threshold` is an orchestrator option (default 0.85).
- `tubeforge-admin similarity-check` prints the scores of fixed example pairs (duplicates, paraphrases, related and unrelated topics, Urdu and Spanish), so the thresholds can be checked on the owner's PC.

## Consequences
- The build machine's network blocks the Hugging Face CDN, so the model's scores were not measured there. The thresholds are confirmed on the owner's PC with `similarity-check` during the Phase 7 demo. Unit tests use the trigram method and a fake encoder.
- Static embeddings are weaker than transformer embeddings for subtle paraphrases. That is good enough for duplicate and variation guards, and the owner can override with a reason.

## Free-tier status
Introduces no paid dependency ✔ (model2vec MIT, model MIT, runs locally).
