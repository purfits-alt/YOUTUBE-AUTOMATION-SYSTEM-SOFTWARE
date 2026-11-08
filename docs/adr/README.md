# Architecture Decision Records

| ADR | Title | Status |
|---|---|---|
| [ADR-0001](ADR-0001-native-windows-install.md) | Native Windows install as the primary deployment | Accepted |
| [ADR-0002](ADR-0002-backend-fastapi.md) | Backend: Python FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic | Accepted |
| [ADR-0003](ADR-0003-postgresql.md) | Database: PostgreSQL for all environments | Accepted |
| [ADR-0004](ADR-0004-task-queue-procrastinate.md) | Task queue: Procrastinate (PostgreSQL-backed) | Accepted |
| [ADR-0005](ADR-0005-custom-state-machine.md) | Orchestration: custom state machine persisted in PostgreSQL | Accepted |
| [ADR-0006](ADR-0006-frontend-vite-react.md) | Frontend: Vite + React + TypeScript SPA served by FastAPI | Accepted |
| [ADR-0007](ADR-0007-llm-gateway-strategy.md) | LLM strategy: Gateway with Gemini free tier → Groq free tier → local Ollama | Accepted |
| [ADR-0008](ADR-0008-tts-strategy.md) | Text-to-speech: owner voice first, then Kokoro / Piper with per-voice licence gate | Accepted |
| [ADR-0009](ADR-0009-stt-faster-whisper.md) | Speech-to-text and captions: faster-whisper (local) | Accepted |
| [ADR-0010](ADR-0010-visuals-non-generative-default.md) | Visuals: non-generative by default; generative image adapter disabled | Accepted |
| [ADR-0011](ADR-0011-ffmpeg-timeline-compiler.md) | Video engine: FFmpeg driven by a timeline-JSON compiler | Accepted |
| [ADR-0012](ADR-0012-secrets-encryption.md) | Secrets: AES-256-GCM envelope encryption, master key in Windows Credential Manager | Accepted |
| [ADR-0013](ADR-0013-owner-auth.md) | Owner authentication: local accounts, Argon2id, optional TOTP | Accepted |
| [ADR-0014](ADR-0014-notifications.md) | Notifications: in-app SSE + Telegram; SMTP optional; WhatsApp disabled | Accepted |
| [ADR-0015](ADR-0015-research-data-policy.md) | Research data policy: comply with the YouTube 'Data Aggregation' rule | Accepted |
| [ADR-0016](ADR-0016-publishing-safety.md) | Publishing safety after the 2 Nov 2026 change: explicit privacy, private by default | Accepted |
| [ADR-0017](ADR-0017-testing-ci.md) | Testing and CI: pytest, Vitest, Playwright, GitHub Actions | Accepted |
| [ADR-0018](ADR-0018-repo-tooling.md) | Monorepo layout and tooling | Accepted |
| [ADR-0019](ADR-0019-owner-voice-cloning.md) | Owner voice recording and owner-only voice cloning | Accepted |
| [ADR-0020](ADR-0020-stock-media-providers.md) | Optional stock video and image providers (free and paid) | Accepted |
| [ADR-0021](ADR-0021-optional-external-editors.md) | Optional external editors for video and thumbnails | Accepted |
| [ADR-0022](ADR-0022-project-licence-mit.md) | Project licence: MIT | Accepted |
