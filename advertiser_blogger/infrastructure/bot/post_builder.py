from dataclasses import dataclass
from enum import Enum
from typing import Optional
from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pydantic import BaseModel
from typing_extensions import Self

from advertiser_blogger.infrastructure.bot.adaptive_html_to_telegram import (
    normalize_html_for_telegram,
)


class BotError(Exception):
    pass


class PostBuildError(BotError):
    pass


class MessageType(str, Enum):
    TEXT = 1
    PHOTO = 2
    VIDEO = 3
    DOCUMENT = 4
    GIF = 5
    PHOTO_WITH_CAPTION = 6
    VIDEO_WITH_CAPTION = 7
    GIF_WITH_CAPTION = 8
    DOCUMENT_WITH_CAPTION = 9
    MEDIA_GROUP = 10
    MEDIA_GROUP_CAPTION = 11
    COMMENT = 12


class ContentType(int, Enum):
    text = 1
    photo = 2
    video = 3
    file = 4
    button = 5
    gif = 6


class FileViewWithUrl(BaseModel):
    content_type: ContentType
    content: str
    name: Optional[str] = None
    url: Optional[str] = None


class PostResponse(BaseModel):
    id: UUID
    platform: int
    post_type: int
    comment: Optional[str] = None
    files: list[FileViewWithUrl]


@dataclass
class PostButton:
    name: str
    url: str


ALLOWED_TAGS = {
    "b",
    "strong",
    "i",
    "em",
    "u",
    "ins",
    "s",
    "strike",
    "del",
    "a",
    "code",
    "pre",
    "blockquote",
}


@dataclass
class TelegramMessage:
    text: Optional[str]
    photo: list[str]
    video: list[str]
    gif: list[str]
    documents: list[str]
    buttons: list[PostButton]
    comment: Optional[str]
    type: MessageType = MessageType.TEXT

    def build(self) -> Self:
        if self.text is not None:
            self.text = normalize_html_for_telegram(html=self.text)
        if (
            self.text is not None
            and len(self.photo) == 0
            and len(self.video) == 0
            and len(self.gif) == 0
        ):
            return self
        elif self.text is None and len(self.photo) == 1 and len(self.video) == 0:
            self.type = MessageType.PHOTO
            return self
        elif self.text is None and len(self.photo) == 0 and len(self.video) == 1:
            self.type = MessageType.VIDEO
            return self
        elif (
            self.text is None
            and len(self.photo) == 0
            and len(self.video) == 0
            and len(self.documents) == 1
        ):
            self.type = MessageType.DOCUMENT
            return self
        elif self.text is not None and len(self.photo) == 1 and len(self.video) == 0:
            self.type = MessageType.PHOTO_WITH_CAPTION
            return self
        elif self.text is not None and len(self.photo) == 0 and len(self.video) == 1:
            self.type = MessageType.VIDEO_WITH_CAPTION
            return self
        elif (
            self.text is not None
            and len(self.photo) == 0
            and len(self.video) == 0
            and len(self.documents) == 1
        ):
            self.type = MessageType.DOCUMENT_WITH_CAPTION
            return self
        elif self.text is None and (len(self.photo) > 1 or len(self.video) > 1):
            self.type = MessageType.MEDIA_GROUP
            return self
        elif self.text is not None and (len(self.photo) > 1 or len(self.video) > 1):
            self.type = MessageType.MEDIA_GROUP_CAPTION
            return self
        elif self.text is None and len(self.gif) == 1:
            self.type = MessageType.GIF
            return self
        elif self.text is not None and len(self.gif) == 1:
            self.type = MessageType.GIF_WITH_CAPTION
            return self
        elif (
            self.text is None
            and len(self.photo) == 0
            and len(self.video) == 0
            and len(self.gif) == 0
            and len(self.documents) == 0
            and self.comment is not None
        ):
            self.type = MessageType.COMMENT
            return self
        raise PostBuildError()


class PostBuilder:
    def __init__(self, post: PostResponse):
        self.post = post

    def execute(self) -> TelegramMessage:
        message = TelegramMessage(
            text=None,
            photo=[],
            video=[],
            gif=[],
            documents=[],
            buttons=[],
            comment=None,
        )
        for file in self.post.files:
            if file.content_type == ContentType.text:
                message.text = file.content
            elif file.content_type == ContentType.photo:
                message.photo.append(file.content)
            elif file.content_type == ContentType.video:
                message.video.append(file.content)
            elif file.content_type == ContentType.gif:
                message.gif.append(file.content)
            elif file.content_type == ContentType.file:
                message.documents.append(file.content)
            elif file.content_type == ContentType.button:
                message.buttons.append(PostButton(name=file.content, url=file.url))
        if self.post.comment is not None:
            message.comment = self.post.comment
        message.build()
        return message


def post_markup(buttons: list[PostButton]) -> InlineKeyboardMarkup:
    keyboard = []
    for i in buttons:
        keyboard.append([InlineKeyboardButton(text=i.name, url=i.url)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
