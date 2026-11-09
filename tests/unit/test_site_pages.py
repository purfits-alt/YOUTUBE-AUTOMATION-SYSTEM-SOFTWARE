"""DP-5: the privacy policy and terms contain what the YouTube Developer Policies require.

See OAUTH_SECURITY §8.
"""

from __future__ import annotations

from pathlib import Path

SITE = Path(__file__).resolve().parents[2] / "site"


def test_privacy_policy_has_the_required_parts() -> None:
    html = (SITE / "privacy.html").read_text(encoding="utf-8")
    for needed in (
        "http://www.google.com/policies/privacy",  # link to the Google Privacy Policy
        "https://security.google.com/settings/security/permissions",  # how to revoke
        "youtube.upload",  # what is accessed and why
        "locally on my computer",  # where it is stored
        "AI providers",  # sharing
        "tf_session",  # cookies
        "within 7 days",  # deletion process
        "<h2>7. Contact</h2>",  # contact e-mail (filled in by the owner before publishing)
        "YouTube API Services Developer Policies",
    ):
        assert needed in html, needed


def test_terms_bind_users_to_youtube_terms() -> None:
    html = (SITE / "terms.html").read_text(encoding="utf-8")
    assert "https://www.youtube.com/t/terms" in html
    assert "agree to be bound by the" in html
