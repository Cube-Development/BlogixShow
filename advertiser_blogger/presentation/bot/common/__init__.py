from enum import Enum


class InlineMessageType(str, Enum):
    photo = "photo"
    video = "video"
    gif = "gif"
    document = "document"