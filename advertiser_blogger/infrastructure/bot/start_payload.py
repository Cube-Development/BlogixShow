"""Reusable Telegram /start compact payload: CBOR → Base64URL (no padding)."""

from __future__ import annotations

import base64
import binascii
import re
from typing import Any

import cbor2

TELEGRAM_START_MAX_ENCODED_LEN = 64
TELEGRAM_START_MAX_DECODED_BYTES = 48

_URLSAFE_ALPHABET = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_",
)

_UUID_UTF8_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class StartPayloadTooLarge(Exception):
    """Encoded start parameter exceeds Telegram limit or decoded CBOR is too large."""


class StartPayloadMalformed(Exception):
    """Invalid alphabet, CBOR, or structure."""


def _reject_cbor_tag(_tag: cbor2.CBORTag) -> None:
    raise StartPayloadMalformed("CBOR tags are not allowed")


def _validate_encoded_alphabet_and_length(value: str) -> None:
    if not value:
        raise StartPayloadMalformed("empty start payload")
    if len(value) > TELEGRAM_START_MAX_ENCODED_LEN:
        raise StartPayloadTooLarge(
            f"encoded payload length {len(value)} exceeds {TELEGRAM_START_MAX_ENCODED_LEN}",
        )
    if any(ch not in _URLSAFE_ALPHABET for ch in value):
        raise StartPayloadMalformed("invalid Base64URL alphabet")


def urlsafe_b64decode_start(value: str) -> bytes:
    _validate_encoded_alphabet_and_length(value)
    padding = "=" * (-len(value) % 4)
    try:
        raw = base64.urlsafe_b64decode(value + padding)
    except (ValueError, binascii.Error) as exc:
        raise StartPayloadMalformed("invalid Base64URL payload") from exc
    if len(raw) > TELEGRAM_START_MAX_DECODED_BYTES:
        raise StartPayloadMalformed("decoded payload too large")
    return raw


def encode_start_payload(data: Any) -> str:
    """Canonical definite-length CBOR → Base64URL without '='."""
    encoded = cbor2.dumps(data, canonical=True)
    if len(encoded) > TELEGRAM_START_MAX_DECODED_BYTES:
        raise StartPayloadTooLarge(
            f"CBOR size {len(encoded)} exceeds {TELEGRAM_START_MAX_DECODED_BYTES} bytes",
        )
    b64 = base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")
    _validate_encoded_alphabet_and_length(b64)
    return b64


def _validate_cbor_structure(obj: Any, depth: int = 0) -> None:
    if depth > 4:
        raise StartPayloadMalformed("CBOR structure too deep")
    if isinstance(obj, list):
        if len(obj) > 16:
            raise StartPayloadMalformed("CBOR array too large")
        for item in obj:
            _validate_cbor_structure(item, depth + 1)
    elif isinstance(obj, dict):
        raise StartPayloadMalformed("CBOR maps are not allowed in start payload")
    elif isinstance(obj, bytes):
        if len(obj) > 32:
            raise StartPayloadMalformed("CBOR byte string too large")
    elif isinstance(obj, str):
        if len(obj) > 64:
            raise StartPayloadMalformed("CBOR text too large")


def decode_start_payload(value: str) -> Any:
    raw = urlsafe_b64decode_start(value)
    try:
        obj = cbor2.loads(
            raw,
            tag_hook=_reject_cbor_tag,
        )
    except StartPayloadMalformed:
        raise
    except Exception as exc:
        raise StartPayloadMalformed("invalid CBOR") from exc
    _validate_cbor_structure(obj)
    return obj


def looks_like_utf8_uuid_bytes(raw: bytes) -> bool:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return _UUID_UTF8_RE.fullmatch(text) is not None


def looks_like_compact_cbor_bytes(raw: bytes) -> bool:
    """True if raw bytes plausibly start a definite CBOR array (v1 collect layout)."""
    if not raw or len(raw) > TELEGRAM_START_MAX_DECODED_BYTES:
        return False
    first = raw[0]
    if 0x80 <= first <= 0x97:
        return True
    if first == 0x98 and len(raw) >= 2:
        return True
    return False


def is_legacy_redis_start_args(args: str) -> bool:
    """After Base64URL decode, legacy deeplink is a UTF-8 UUID string."""
    try:
        raw = urlsafe_b64decode_start(args)
    except (StartPayloadMalformed, StartPayloadTooLarge):
        return False
    return looks_like_utf8_uuid_bytes(raw)


def is_compact_start_args(args: str) -> bool:
    try:
        raw = urlsafe_b64decode_start(args)
    except (StartPayloadMalformed, StartPayloadTooLarge):
        return False
    if looks_like_utf8_uuid_bytes(raw):
        return False
    return looks_like_compact_cbor_bytes(raw)
