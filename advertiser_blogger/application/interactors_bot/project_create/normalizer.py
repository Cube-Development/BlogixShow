from __future__ import annotations

import re


_SPACE_RE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    text = value.strip().lower().replace("ё", "е")
    text = _SPACE_RE.sub(" ", text)
    return text


def normalize_label(value: str) -> str:
    text = normalize_text(value)
    return text.rstrip(":").strip()
