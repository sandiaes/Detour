"""Anonymous installation tokens (app plan D5).

A token is ``dt1.<installation id as 32 hex digits>.<signature>`` where the signature is an
HMAC-SHA256 over the first two parts, keyed with ``DETOUR_TOKEN_SECRET``. Checking a token needs
no database. There are no accounts: the token only tells the backend that the caller is the same
installation that registered.

Phase 4 adds ``app.installation`` for the rows that trips will refer to; tokens issued now stay
valid because they carry the installation id (ADR 010).
"""

import base64
import hashlib
import hmac
import re
import uuid

PREFIX = "dt1"
_TOKEN_RE = re.compile(rf"^{PREFIX}\.([0-9a-f]{{32}})\.([A-Za-z0-9_-]{{43}})$")


def _signature(secret: bytes, installation_hex: str) -> str:
    digest = hmac.new(secret, f"{PREFIX}.{installation_hex}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def sign_token(secret: bytes, installation_id: uuid.UUID) -> str:
    """The token of a known installation (used by the seed command; registration uses issue)."""
    return f"{PREFIX}.{installation_id.hex}.{_signature(secret, installation_id.hex)}"


def issue_token(secret: bytes) -> tuple[uuid.UUID, str]:
    installation_id = uuid.uuid4()
    return installation_id, sign_token(secret, installation_id)


def verify_token(secret: bytes, token: str) -> uuid.UUID | None:
    """Return the installation id if the token is genuine, otherwise ``None``."""
    match = _TOKEN_RE.match(token)
    if match is None:
        return None
    installation_hex, signature = match.groups()
    if not hmac.compare_digest(signature, _signature(secret, installation_hex)):
        return None
    return uuid.UUID(hex=installation_hex)
