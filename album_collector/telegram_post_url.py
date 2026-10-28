import re

_TELEGRAM_POST_URL_RE = re.compile(
    r"https?://(?:t\.me|telegram\.me)/(?P<key>(?:c/\d+/\d+|[\w]+/\d+))(?:\?[^\s]*)?",
    re.I,
)


def is_telegram_post_url_only(text: str) -> bool:
    if not text:
        return False
    stripped = text.strip()
    match = _TELEGRAM_POST_URL_RE.fullmatch(stripped)
    return match is not None
