"""Detect creative kinds for project-create posts (media / text / button / repost)."""

from __future__ import annotations

import re
from enum import Enum

from advertiser_blogger.domain.common.telegram_post_url import is_telegram_post_url_only

# Whitelist of bots that produce "post with button" creatives: @BotName <token>
BUTTON_POST_BOTS: tuple[str, ...] = (
    "postbot",
    "padsbot",
    "blogix_uz",
)

_BUTTON_BOTS_ALT = "|".join(re.escape(b) for b in BUTTON_POST_BOTS)
# Match @BotToken anywhere in the message (e.g. "2 @PostBot 40599y1mrs0fpc3").
_BUTTON_POST_RE = re.compile(
    rf"(?:^|\s)@({_BUTTON_BOTS_ALT})\s+(\S+)",
    re.IGNORECASE,
)


class CreativeKind(str, Enum):
    media = "media"
    text = "text"
    button = "button"
    repost = "repost"
    empty = "empty"


def is_button_bot_post(text: str | None) -> bool:
    if not text or not str(text).strip():
        return False
    return _BUTTON_POST_RE.search(str(text).strip()) is not None


def is_repost_post_url(text: str | None) -> bool:
    return is_telegram_post_url_only(text or "")


def detect_text_creative_kind(text: str | None) -> CreativeKind | None:
    """
    Classify a non-media message body as a creative kind.
    Returns None if the text is empty (caller decides metadata vs ignore).
    """
    raw = (text or "").strip()
    if not raw:
        return None
    if is_repost_post_url(raw):
        return CreativeKind.repost
    if is_button_bot_post(raw):
        return CreativeKind.button
    return CreativeKind.text


def skips_tz_channel_publish(kind: CreativeKind | str | None) -> bool:
    """Button / repost / empty creatives must not be copied into the Blogix TZ channel."""
    if kind is None:
        return False
    value = kind.value if isinstance(kind, CreativeKind) else str(kind)
    return value in {
        CreativeKind.button.value,
        CreativeKind.repost.value,
        CreativeKind.empty.value,
    }
