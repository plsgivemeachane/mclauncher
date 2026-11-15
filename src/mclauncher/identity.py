"""Offline-session player identity, shared by the GUI and headless control."""

from __future__ import annotations

import hashlib
import re
import uuid

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")


def local_identity(username: str) -> str:
    """Return the stable offline-session identity for a saved username."""
    digest = hashlib.sha256(username.encode("utf-8")).hexdigest()
    return str(uuid.UUID(digest[:32]))
