import json
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

from aiogram.types import Message

from advertiser_blogger.domain.common.telegram_post_url import is_telegram_post_url_only
from advertiser_blogger.presentation.bot.common.forward_message import (
    extract_telegram_url_from_body,
    get_forward_source,
    get_forward_source_from_album_part,
    get_message_body,
    is_any_forward,
)
from advertiser_blogger.presentation.bot.album.models import AggregatedAlbum


@dataclass(frozen=True)
class AlbumMediaItem:
    message_id: int
    file_id: str
    file_unique_id: str | None
    media_type: str


@dataclass(frozen=True)
class PostSubmissionInput:
    channel_ident: int | None
    channel_username: str | None
    post_url: str
    text: str | None
    media_group_id: str | None = None
    media: tuple[AlbumMediaItem, ...] = ()
    primary_message_id: int | None = None
    is_album: bool = False

def parse_telegram_post_url(post_url: str) -> tuple[int | None, str | None]:
    path_parts = [part for part in urlparse(post_url).path.strip("/").split("/") if part]
    if len(path_parts) >= 2 and path_parts[0] == "c":
        try:
            return int(path_parts[1]), None
        except ValueError:
            return None, None
    if len(path_parts) >= 2 and path_parts[0] != "s":
        return None, path_parts[0]
    if len(path_parts) >= 3 and path_parts[0] == "s" and path_parts[1] == "c":
        try:
            return int(path_parts[2]), None
        except ValueError:
            return None, None
    return None, None


def extract_post_submission(message: Message) -> PostSubmissionInput:
    body = get_message_body(message=message)
    source = get_forward_source(message=message)

    if source is not None:
        channel_ident = source.channel_ident
        channel_username = source.channel_username
        post_url = source.post_url or extract_telegram_url_from_body(body=body) or ""
        text = body
    else:
        post_url = extract_telegram_url_from_body(body=body) or (message.text or "")
        channel_ident, channel_username = parse_telegram_post_url(post_url=post_url)
        text = None

    if channel_ident is None and post_url:
        parsed_ident, parsed_username = parse_telegram_post_url(post_url=post_url)
        channel_ident = parsed_ident
        if channel_username is None:
            channel_username = parsed_username

    if not is_any_forward(message) and extract_telegram_url_from_body(body=body) == post_url:
        text = None
    if text is not None and is_telegram_post_url_only(text):
        text = None
    return PostSubmissionInput(
        channel_ident=channel_ident,
        channel_username=channel_username,
        post_url=post_url,
        text=text,
    )


def _album_media_items(aggregated: AggregatedAlbum) -> tuple[AlbumMediaItem, ...]:
    return tuple(
        AlbumMediaItem(
            message_id=part.message_id,
            file_id=part.file_id,
            file_unique_id=part.file_unique_id,
            media_type=part.media_type,
        )
        for part in sorted(aggregated.parts, key=lambda item: item.message_id)
    )


def _post_submission_from_album(
        aggregated: AggregatedAlbum,
        *,
        channel_ident: int | None,
        channel_username: str | None,
        post_url: str,
        text: str | None,
) -> PostSubmissionInput:
    return PostSubmissionInput(
        channel_ident=channel_ident,
        channel_username=channel_username,
        post_url=post_url,
        text=text,
        media_group_id=aggregated.media_group_id,
        media=_album_media_items(aggregated),
        primary_message_id=aggregated.primary_message_id,
        is_album=True,
    )


def extract_post_submission_from_album(
        aggregated: AggregatedAlbum,
        source_message: Message | None = None,
) -> PostSubmissionInput:
    forward_part = aggregated.forward_part
    if forward_part is not None:
        source = get_forward_source_from_album_part(forward_part)
        body = aggregated.caption
        if source is not None:
            channel_ident = source.channel_ident
            channel_username = source.channel_username
            post_url = source.post_url or extract_telegram_url_from_body(body=body) or ""
            text = body
        else:
            post_url = extract_telegram_url_from_body(body=body) or ""
            channel_ident, channel_username = parse_telegram_post_url(post_url=post_url)
            text = None

        if channel_ident is None and post_url:
            parsed_ident, parsed_username = parse_telegram_post_url(post_url=post_url)
            channel_ident = parsed_ident
            if channel_username is None:
                channel_username = parsed_username

        if text is not None and is_telegram_post_url_only(text):
            text = None

        return _post_submission_from_album(
            aggregated,
            channel_ident=channel_ident,
            channel_username=channel_username,
            post_url=post_url,
            text=text,
        )

    caption = aggregated.caption or ""
    post_url = extract_telegram_url_from_body(body=caption) or ""
    channel_ident, channel_username = parse_telegram_post_url(post_url=post_url)
    text = caption if caption and not is_telegram_post_url_only(caption) else None
    if text is not None and is_telegram_post_url_only(text):
        text = None

    return _post_submission_from_album(
        aggregated,
        channel_ident=channel_ident,
        channel_username=channel_username,
        post_url=post_url,
        text=text,
    )


def submission_to_json(submission: PostSubmissionInput) -> str:
    return json.dumps(asdict(submission))


def submission_from_json(payload: str) -> PostSubmissionInput:
    data = json.loads(payload)
    media = tuple(
        AlbumMediaItem(
            message_id=item["message_id"],
            file_id=item["file_id"],
            file_unique_id=item.get("file_unique_id"),
            media_type=item["media_type"],
        )
        for item in data.get("media", [])
    )
    return PostSubmissionInput(
        channel_ident=data.get("channel_ident"),
        channel_username=data.get("channel_username"),
        post_url=data["post_url"],
        text=data.get("text"),
        media_group_id=data.get("media_group_id"),
        media=media,
        primary_message_id=data.get("primary_message_id"),
        is_album=data.get("is_album", False),
    )
