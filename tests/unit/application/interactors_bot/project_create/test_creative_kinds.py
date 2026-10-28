from types import SimpleNamespace

from advertiser_blogger.application.interactors_bot.project_create.creative_kinds import (
    BUTTON_POST_BOTS,
    CreativeKind,
    detect_text_creative_kind,
    is_button_bot_post,
    is_repost_post_url,
    skips_tz_channel_publish,
)
from advertiser_blogger.presentation.bot.message_batch.pairing_fsm import (
    PairingEvent,
    classify_message,
    is_text_creative_message,
)


def test_button_bots_whitelist() -> None:
    assert "postbot" in BUTTON_POST_BOTS
    assert "padsbot" in BUTTON_POST_BOTS
    assert "blogix_uz" in BUTTON_POST_BOTS


def test_is_button_bot_post() -> None:
    assert is_button_bot_post("@PostBot 40599y1mrs0fpc3")
    assert is_button_bot_post("@padsbot 37usw73:")
    assert is_button_bot_post("@blogix_uz 2727")
    assert is_button_bot_post("  @POSTBOT token123  ")
    assert is_button_bot_post("2 @PostBot 40599y1mrs0fpc3")
    assert is_button_bot_post("prefix\n@padsbot abc:")
    assert not is_button_bot_post("@Jonli_Bolta")
    assert not is_button_bot_post("@SomeBot abc")
    assert not is_button_bot_post("@PostBot")
    assert not is_button_bot_post("https://t.me/PostBot/1")


def test_is_repost_post_url() -> None:
    assert is_repost_post_url("https://t.me/channel_name/2828")
    assert is_repost_post_url("https://telegram.me/channel_name/2882")
    assert is_repost_post_url("https://t.me/c/1234567890/2727")
    assert is_repost_post_url("https://telegram.me/c/1234567890/2727")
    assert not is_repost_post_url("https://t.me/channel_name")
    assert not is_repost_post_url("@channel_name")


def test_detect_text_creative_kind() -> None:
    assert detect_text_creative_kind("@PostBot abc") is CreativeKind.button
    assert detect_text_creative_kind("2 @PostBot 40599y1mrs0fpc3") is CreativeKind.button
    assert detect_text_creative_kind("https://t.me/x/1") is CreativeKind.repost
    assert detect_text_creative_kind("просто текст рекламы") is CreativeKind.text
    assert detect_text_creative_kind("  ") is None


def test_skips_tz_channel_publish() -> None:
    assert skips_tz_channel_publish(CreativeKind.button) is True
    assert skips_tz_channel_publish(CreativeKind.repost) is True
    assert skips_tz_channel_publish(CreativeKind.empty) is True
    assert skips_tz_channel_publish(CreativeKind.text) is False
    assert skips_tz_channel_publish(CreativeKind.media) is False


def test_is_text_creative_message_vs_metadata() -> None:
    assert is_text_creative_message("@PostBot token") is True
    assert is_text_creative_message("2 @PostBot 40599y1mrs0fpc3") is True
    assert is_text_creative_message("https://t.me/foo/12") is True
    assert is_text_creative_message("Рекламный текст без каналов") is True
    assert is_text_creative_message("@Jonli_Bolta") is False
    assert is_text_creative_message("https://t.me/Jonli_Bolta") is False
    assert is_text_creative_message(
        "Проект: Test\nhttps://t.me/Jonli_Bolta 18:10",
    ) is False


def _msg(**kwargs):
    defaults = {
        "text": None,
        "caption": None,
        "video": None,
        "photo": None,
        "document": None,
        "animation": None,
        "message_id": 1,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_classify_message_creatives() -> None:
    assert classify_message(_msg(text="@PostBot abc")) is PairingEvent.MEDIA
    assert classify_message(_msg(text="2 @PostBot 40599y1mrs0fpc3")) is PairingEvent.MEDIA
    assert classify_message(_msg(text="https://t.me/c/1/2")) is PairingEvent.MEDIA
    assert classify_message(_msg(text="просто текст")) is PairingEvent.MEDIA
    assert classify_message(_msg(text="@Jonli_Bolta")) is PairingEvent.CHANNEL_ONLY
    assert classify_message(_msg(photo=[object()])) is PairingEvent.MEDIA
