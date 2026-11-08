# Architecture Decision Records

| ADR | Title | Status |
|---|---|---|
| [ADR-0001](ADR-0001-native-windows-install.md) | Native Windows install as the primary deployment | Proposed |
| [ADR-0002](ADR-0002-backend-fastapi.md) | Backend: Python FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic | Proposed |
| [ADR-0003](ADR-0003-postgresql.md) | Database: PostgreSQL for all environments | Proposed |
| [ADR-0004](ADR-0004-task-queue-procrastinate.md) | Task queue: Procrastinate (PostgreSQL-backed) | Proposed |
| [ADR-0005](ADR-0005-custom-state-machine.md) | Orchestration: custom state machine persisted in PostgreSQL | Proposed |
| [ADR-0006](ADR-0006-frontend-vite-react.md) | Frontend: Vite + React + TypeScript SPA served by FastAPI | Proposed |
| [ADR-0007](ADR-0007-llm-gateway-strategy.md) | LLM strategy: Gateway with Gemini free tier → Groq free tier → local Ollama | Proposed |
| [ADR-0008](ADR-0008-tts-strategy.md) | Text-to-speech: owner voice first, then Kokoro / Piper with per-voice licence gate | Proposed |
| [ADR-0009](ADR-0009-stt-faster-whisper.md) | Speech-to-text and captions: faster-whisper (local) | Proposed |
| [ADR-0010](ADR-0010-visuals-non-generative-default.md) | Visuals: non-generative by default; generative image adapter disabled | Proposed |
| [ADR-0011](ADR-0011-ffmpeg-timeline-compiler.md) | Video engine: FFmpeg driven by a timeline-JSON compiler | Proposed |
| [ADR-0012](ADR-0012-secrets-encryption.md) | Secrets: AES-256-GCM envelope encryption, master key in Windows Credential Manager | Proposed |
| [ADR-0013](ADR-0013-owner-auth.md) | Owner authentication: local accounts, Argon2id, optional TOTP | Proposed |
| [ADR-0014](ADR-0014-notifications.md) | Notifications: in-app SSE + Telegram; SMTP optional; WhatsApp disabled | Proposed |
| [ADR-0015](ADR-0015-research-data-policy.md) | Research data policy: comply with the YouTube 'Data Aggregation' rule | Proposed |
| [ADR-0016](ADR-0016-publishing-safety.md) | Publishing safety after the 2 Nov 2026 change: explicit privacy, private by default | Proposed |
| [ADR-0017](ADR-0017-testing-ci.md) | Testing and CI: pytest, Vitest, Playwright, GitHub Actions | Proposed |
| [ADR-0018](ADR-0018-repo-tooling.md) | Monorepo layout and tooling | Proposed |
