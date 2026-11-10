"""Provider registry rules and the owner's API keys (COST_CONTROL_SPEC §1, SYSTEM_ARCHITECTURE §4-H).

A provider code is ``family:model`` (``gemini:gemini-2.5-flash``, ``groq:openai/gpt-oss-20b``,
``ollama:qwen2.5:1.5b``). One API key serves every model of a family; it is stored encrypted on
each registry row of that family and never returned by the API.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from tubeforge.db.models import Channel, ProviderCredential, ProviderRegistry
from tubeforge.secrets import SecretBox, aad

KEYLESS_FAMILIES = frozenset({"ollama"})  # local runtime: no key


def family(code: str) -> str:
    return code.split(":", 1)[0]


def model(code: str) -> str:
    return code.split(":", 1)[1]


def policy_block(provider: ProviderRegistry, channel: Channel | None, capability: str = "LLM") -> str | None:
    """Why this provider may not be used for this call, or None (registry policy, pipeline step 2)."""
    if provider.capability != capability:
        return f"{provider.code} is not a {capability} provider"
    if provider.tier == "P" and provider.paid_activation_step < 2:
        return f"{provider.code} is a paid provider and is not activated (two steps needed)"
    if not provider.enabled:
        return f"{provider.code} is disabled"
    if (
        channel is not None
        and channel.local_only
        and provider.tier != "L"
        and provider.data_use_training is not False
    ):
        return f"{provider.code} may use content to improve its products; this channel is local-only"
    if channel is not None and channel.is_monetised:
        if provider.commercial_use == "NO":
            return f"{provider.code}'s licence does not allow commercial use (monetised channel)"
        if provider.commercial_use == "REVIEW":
            return f"{provider.code}'s licence needs your review before use on a monetised channel"
    return None


def _aad(code: str) -> bytes:
    return aad("provider_credentials", "secret_enc", code)


def set_family_key(db: Session, box: SecretBox, fam: str, secret: str, label: str | None = None) -> int:
    """Store (or replace) the owner's key for every registry row of a family. Returns rows written."""
    codes = db.scalars(select(ProviderRegistry.code).where(ProviderRegistry.code.like(f"{fam}:%"))).all()
    for code in codes:
        sealed = box.seal(secret.encode(), purpose="provider-key", associated=_aad(code))
        row = db.get(ProviderCredential, code)
        if row is None:
            db.add(
                ProviderCredential(
                    provider_code=code, secret_enc=sealed.ciphertext, key_id=sealed.key_id, label=label
                )
            )
        else:
            row.secret_enc, row.key_id, row.label = sealed.ciphertext, sealed.key_id, label
    db.flush()
    return len(codes)


def delete_family_key(db: Session, fam: str) -> None:
    for row in db.scalars(
        select(ProviderCredential).where(ProviderCredential.provider_code.like(f"{fam}:%"))
    ):
        db.delete(row)
    db.flush()


def api_key(db: Session, box: SecretBox, code: str) -> str | None:
    row = db.get(ProviderCredential, code)
    if row is None:
        return None
    return box.open(row.secret_enc, key_id=row.key_id, purpose="provider-key", associated=_aad(code)).decode()


def has_key(db: Session, code: str) -> bool:
    return family(code) in KEYLESS_FAMILIES or db.get(ProviderCredential, code) is not None
