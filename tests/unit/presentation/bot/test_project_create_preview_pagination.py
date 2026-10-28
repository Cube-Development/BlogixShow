from advertiser_blogger.presentation.bot.keyboards.inline import InlineKeyboard


def test_preview_no_pagination_under_10():
    kb = InlineKeyboard().project_create_preview(channel_count=8, page=1, page_size=10)
    flat = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "pc_page_noop" not in flat
    assert any(c and c.startswith("pc_ch:") for c in flat)


def test_preview_pagination_over_10():
    kb = InlineKeyboard().project_create_preview(channel_count=23, page=2, page_size=10)
    flat = [btn for row in kb.inline_keyboard for btn in row]
    channel_buttons = [b for b in flat if b.callback_data and b.callback_data.startswith("pc_ch:")]
    assert [b.text for b in channel_buttons] == [str(i) for i in range(11, 21)]
    beacon = next(b for b in flat if b.callback_data == "pc_page_noop")
    assert beacon.text == "2/3"
    assert any(b.callback_data == "pc_page:1" for b in flat)
    assert any(b.callback_data == "pc_page:3" for b in flat)


def test_preview_page_clamped():
    kb = InlineKeyboard().project_create_preview(channel_count=11, page=99, page_size=10)
    beacon = next(
        b for row in kb.inline_keyboard for b in row if b.callback_data == "pc_page_noop"
    )
    assert beacon.text == "2/2"
