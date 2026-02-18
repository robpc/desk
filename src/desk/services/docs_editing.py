"""Shared utilities for Google Docs editing operations.

Provides text normalization and UTF-16 length calculation needed
by both the markdown converter and any future editing modules.
"""

from __future__ import annotations

import unicodedata


def normalize_text(text: str) -> str:
    """Normalize text for insertion into Google Docs.

    Applies NFC unicode normalization and normalizes line endings to \\n.

    Args:
        text: Raw text input

    Returns:
        Normalized text string
    """
    # Normalize unicode to NFC (composed form)
    text = unicodedata.normalize("NFC", text)
    # Normalize line endings: \r\n -> \n, lone \r -> \n
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def utf16_len(text: str) -> int:
    """Return the UTF-16 code unit length of a string.

    Google Docs API uses UTF-16 offsets for indexing. Characters in the
    Basic Multilingual Plane (U+0000 to U+FFFF) take 1 code unit;
    supplementary characters (emoji, etc.) take 2 code units.

    Args:
        text: Input string

    Returns:
        Number of UTF-16 code units
    """
    return len(text.encode("utf-16-le")) // 2


def utf16_offset(text: str, char_index: int) -> int:
    """Convert a Python string index to a UTF-16 code unit offset.

    Given a Python character index into ``text``, returns the corresponding
    UTF-16 code unit offset.  Useful when the Google Docs API requires a
    position expressed in UTF-16 units but you have a Python ``str`` index.

    Args:
        text: The full string (only the slice up to *char_index* is measured).
        char_index: A valid Python index into *text* (0-based).

    Returns:
        The UTF-16 code unit offset corresponding to *char_index*.
    """
    return utf16_len(text[:char_index])
