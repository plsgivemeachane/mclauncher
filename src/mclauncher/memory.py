"""Memory allocation policy for the launcher.

The initial allocation is one quarter of total physical RAM, rounded down to
whole GiB, with a minimum of 1 GiB and a maximum of 8 GiB.  This leaves most
RAM available to Ubuntu and other applications while providing a useful
default for larger machines.  The setting may be adjusted between 1 GiB and
the machine's whole-GiB physical RAM amount.
"""

from __future__ import annotations

import os

GIB = 1024**3
MIN_MEMORY_GIB = 1
MAX_DEFAULT_MEMORY_GIB = 8


def physical_memory_bytes() -> int:
    """Return total physical memory using the POSIX standard library API."""
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, OSError, ValueError):
        return GIB
    return max(0, int(pages) * int(page_size))


def whole_physical_memory_gib(total_bytes: int | None = None) -> int:
    total_bytes = physical_memory_bytes() if total_bytes is None else total_bytes
    return max(MIN_MEMORY_GIB, int(total_bytes) // GIB)


def default_memory_gib(total_bytes: int | None = None) -> int:
    whole_gib = whole_physical_memory_gib(total_bytes)
    return max(MIN_MEMORY_GIB, min(MAX_DEFAULT_MEMORY_GIB, whole_gib // 4))


def validate_memory_gib(value: str | int, total_bytes: int | None = None) -> tuple[int | None, str | None]:
    """Parse and validate a user setting before a game process is started."""
    try:
        text = str(value).strip()
        if not text or (text.startswith("+") and not text[1:].isdigit()) or not text.lstrip("+").isdigit():
            raise ValueError
        memory_gib = int(text)
    except (TypeError, ValueError):
        return None, "Memory allocation must be a whole number of GiB"
    if memory_gib < MIN_MEMORY_GIB:
        return None, "Memory allocation must be at least 1 GiB"
    maximum = whole_physical_memory_gib(total_bytes)
    if memory_gib > maximum:
        return None, f"Memory allocation cannot exceed {maximum} GiB on this computer"
    return memory_gib, None
