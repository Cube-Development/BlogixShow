from aiogram.types import Chat, Message

from advertiser_blogger.presentation.bot.common.extract_channel_post_submission import (
    extract_channel_post_submission,
)

TZ_TEXT = "blogix рекламная биржа в узбекистане"


def test_extract_channel_post_submission_public_channel() -> None:
    message = Message(
        message_id=42,
        date=0,
        chat=Chat(id=-1001234567890, type="channel", username="testblogix"),
        text=TZ_TEXT,
    )
    submission = extract_channel_post_submission(message=message)
    assert submission.channel_ident == 3992737086
    assert submission.channel_username == "testblogix"
    assert submission.post_url == "https://t.me/testblogix/42"
    assert submission.text == TZ_TEXT
