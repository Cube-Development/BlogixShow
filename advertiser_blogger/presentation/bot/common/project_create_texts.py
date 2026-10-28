from __future__ import annotations

from uuid import UUID

from advertiser_blogger.application.interactors_bot.project_create.creative_kinds import CreativeKind
from advertiser_blogger.application.interactors_bot.project_create.models import (
    BotChannelRef,
    BotProjectDraft,
    ChannelRefStatus,
    ScheduleSource,
)
from advertiser_blogger.domain.read.constants import Language


_TEXTS = {
    Language.ru: {
        "entry_choose_mode": (
            "Выберите, как выложить пост в канал ТЗ.\n\n"
            "Копирование — бот публикует пост в канал как обычное сообщение. "
            "Пост можно редактировать. Премиум-эмодзи могут пропасть.\n\n"
            "Форвард — бот копирует пост себе в этот чат и пересылает своё сообщение в канал. "
            "Эмодзи сохраняются, пост в канале — форвард, править его нельзя."
        ),
        "mode_copy": "Создать копированием",
        "mode_forward": "Создать форвардом",
        "entry": (
            "Создаём РК.\n\n"
            "Пришлите креатив, затем каналы (@name / t.me).\n"
            "Можно несколько пар пост + каналы подряд.\n\n"
            "Пример канала:\n"
            "https://t.me/ru2ch | дата: завтра 14:00 | комментарий: срочно\n"
            "Креатив — отдельным сообщением.\n\n"
            "Проект, комментарий и время — необязательно\n"
            "(время без указания подставим автоматически)."
        ),
        "ask_project_tz_header": "Каналы приняты. Укажите недостающие данные:",
        "ask_project_tz_project": "Проект: …",
        "ask_project_tz_project_done": "Проект уже: {name}",
        "ask_project_tz_time": "Время: …",
        "ask_project_tz": (
            "Каналы приняты. Укажите данные проекта:\n"
            "Проект: …\nКомментарий: …\nВремя: …"
        ),
        "awaiting_reply": "Пришлите каналы (@name / ссылки) или данные проекта (проект / комментарий / время).",
        "need_post_and_data": (
            "Сначала пришлите креатив (пост), затем каналы или данные:\n"
            "Проект: …\nКомментарий: …\nВремя: …\nКаналы:\n@name"
        ),
        "preview_title": "Превью проекта",
        "preview_project": "Проект: {name}",
        "preview_found": "✅ Найдено: {n}",
        "preview_not_found": "⚠ Не найдено: {m}",
        "preview_empty_channels": "Пустые каналы: {n}",
        "preview_page": "Стр. {page}/{total}",
        "preview_channels": "Каналы:",
        "preview_no_channels": "—",
        "preview_posts": "Постов: {n}",
        "preview_post_filled": "Пост: Есть",
        "preview_post_empty": "Пост: 🔹Пусто",
        "auto": "(автоматически)",
        "confirm_blocked_unknown": "Есть неизвестные или невалидные каналы. Замените или удалите их.",
        "confirm_error": "Не удалось сохранить проект. Попробуйте снова или отмените создание.",
        "confirm_ok": "Проект сохранён.\n\n{project_url}",
        "confirm_partial": "Проект частично создан. Дозаполните в кабинете:\n\n{project_url}",
        "confirm_progress_cart": "Добавляем в корзину: {total}",
        "confirm_progress_orders": "Генерация ордеров: {total}",
        "confirm_progress_posts": "Привязываем посты: {total}",
        "past_schedule": "Указанное время уже в прошлом. Укажите будущее время.",
        "add_post": "Пришлите следующий креатив (пост).",
        "cancel": "Создание РК отменено.",
        "channel_menu": "Канал #{n}\n{label}",
        "channel_detail_title": "Канал #{n}",
        "channel_detail_name": "Название: {name}",
        "channel_detail_url": "Ссылка: {url}",
        "channel_detail_date": "Дата: {date}",
        "channel_detail_time": "Время: {time}",
        "channel_detail_comment": "Коммент: {comment}",
        "channel_detail_instead": "Вместо: {instead}",
        "edit_schedule_prompt": (
            "Пришлите новую дату и время для канала.\n"
            "Примеры: 21.07.2026 18:00–20:00\n"
            "завтра 14:00\n"
            "18:00 - 20:00"
        ),
        "edit_comment_prompt": "Пришлите новый комментарий для канала.",
        "edit_schedule_invalid": "Не удалось разобрать дату/время. Попробуйте ещё раз.",
        "replace_prompt": "Пришлите новый @username или ссылку на канал.",
        "replace_post_prompt": "Пришлите новый креатив для этого канала (одно фото/видео/документ или текст).",
        "replace_post_no_album": "Альбом пока не поддерживается при замене. Пришлите один файл или текст.",
        "show_post_empty": "У этого канала нет сохранённого поста.",
        "show_post_failed": "Не удалось показать пост (сообщение могло быть удалено).",
        "reset_schedule_ok": "Дата/время сброшены.",
        "reset_comment_ok": "Комментарий сброшен.",
        "duplicate_channel": "⚠ Вы дублируете канал: {label}",
        "no_posts": "Сначала добавьте хотя бы один пост.",
        "processing": "⏳ Обрабатываем сообщения…",
        "waiting_creative": "Каналы сохранены. Ждём креатив…",
        "orphan_need_channels": (
            "У поста нет канала.\n"
            "Пришлите ссылку / @канал\n"
            "или нажмите «Оставить пустым» — подставим канал на замену."
        ),
        "orphan_need_creative": (
            "Каналы сохранены, креатива нет.\n"
            "Пришлите пост\n"
            "или нажмите «Оставить пустым» — пост будет EMPTY."
        ),
        "orphan_leave_empty": "Оставить пустым",
        "orphan_leave_empty_ok": "Пустые слоты заполнены.",
        "orphan_leave_empty_failed": "Не удалось заполнить пустые слоты. Попробуйте ещё раз.",
        "channel_mode_prompt": (
            "К этим каналам не указан пост:\n"
            "{channels}\n\n"
            "Привязать к посту выше, прислать свой креатив "
            "или оставить пустым?"
        ),
        "channel_mode_to_above": "К посту выше",
        "channel_mode_own_creative": "Свой креатив",
        "channel_mode_leave_empty": "Оставить пустым",
        "channel_mode_ask_creative": (
            "Пришлите креатив для этой пачки каналов:\n"
            "{channels}"
        ),
        "channel_mode_ok_above": "Каналы добавлены к посту выше.",
        "channel_mode_ok_creative": "Креатив привязан к каналам пачки.",
        "channel_mode_ok_empty": "Созданы пустые посты для каналов.",
        "channel_mode_failed": "Не удалось применить каналы. Попробуйте ещё раз.",
    },
    Language.uz: {
        "entry_choose_mode": (
            "TZ kanaliga postni qanday joylashni tanlang.\n\n"
            "Nusxa — bot postni kanalga oddiy xabar sifatida joylaydi. "
            "Postni tahrirlash mumkin. Premium emoji yo‘qolishi mumkin.\n\n"
            "Forward — bot postni shu chatga o‘ziga nusxalaydi va o‘z xabarini kanalga yuboradi. "
            "Emoji saqlanadi, kanalda post forward bo‘ladi, tahrirlab bo‘lmaydi."
        ),
        "mode_copy": "Nusxa bilan yaratish",
        "mode_forward": "Forward bilan yaratish",
        "entry": (
            "RK yaratamiz.\n\n"
            "Kreativ yuboring, keyin kanallar (@name / t.me).\n"
            "Bir nechta post + kanallar juftligini ketma-ket yuborish mumkin.\n\n"
            "Kanal namunasi:\n"
            "https://t.me/ru2ch | sana: ertaga 14:00 | izoh: shoshilinch\n"
            "Kreativ — alohida xabar.\n\n"
            "Loyiha, izoh va vaqt — ixtiyoriy\n"
            "(vaqt ko‘rsatilmasa, avtomatik qo‘yamiz)."
        ),
        "ask_project_tz_header": "Kanallar qabul qilindi. Yetishmayotgan ma'lumotlarni yuboring:",
        "ask_project_tz_project": "Loyiha: …",
        "ask_project_tz_project_done": "Loyiha allaqachon: {name}",
        "ask_project_tz_time": "Vaqt: …",
        "ask_project_tz": (
            "Kanallar qabul qilindi. Loyiha ma'lumotlarini yuboring:\n"
            "Loyiha: …\nIzoh: …\nVaqt: …"
        ),
        "awaiting_reply": "Kanallar (@name / havola) yoki loyiha ma'lumotlarini (loyiha / izoh / vaqt) yuboring.",
        "need_post_and_data": (
            "Avval kreativ (post) yuboring, keyin kanallar yoki ma'lumot:\n"
            "Loyiha: …\nIzoh: …\nVaqt: …\nKanallar:\n@name"
        ),
        "preview_title": "Loyiha prevyusi",
        "preview_project": "Loyiha: {name}",
        "preview_found": "✅ Topildi: {n}",
        "preview_not_found": "⚠ Topilmadi: {m}",
        "preview_empty_channels": "Bo'sh kanallar: {n}",
        "preview_page": "Sahifa {page}/{total}",
        "preview_channels": "Kanallar:",
        "preview_no_channels": "—",
        "preview_posts": "Postlar: {n}",
        "preview_post_filled": "Post: Bor",
        "preview_post_empty": "Post: 🔹Bo'sh",
        "auto": "(avtomatik)",
        "confirm_blocked_unknown": "Noma'lum yoki noto'g'ri kanallar bor. Almashtiring yoki o'chiring.",
        "confirm_error": "Loyihani saqlab bo'lmadi. Qayta urinib ko'ring yoki bekor qiling.",
        "confirm_ok": "Loyiha saqlandi.\n\n{project_url}",
        "confirm_partial": "Loyiha qisman yaratildi. Kabinetda to'ldiring:\n\n{project_url}",
        "confirm_progress_cart": "Savatga qo'shilmoqda: {total}",
        "confirm_progress_orders": "Buyurtmalar yaratilmoqda: {total}",
        "confirm_progress_posts": "Postlar biriktirilmoqda: {total}",
        "past_schedule": "Vaqt o'tib ketgan. Kelajakdagi vaqtni kiriting.",
        "add_post": "Keyingi kreativni (post) yuboring.",
        "cancel": "Loyiha yaratish bekor qilindi.",
        "channel_menu": "Kanal #{n}\n{label}",
        "channel_detail_title": "Kanal #{n}",
        "channel_detail_name": "Nomi: {name}",
        "channel_detail_url": "Havola: {url}",
        "channel_detail_date": "Sana: {date}",
        "channel_detail_time": "Vaqt: {time}",
        "channel_detail_comment": "Izoh: {comment}",
        "channel_detail_instead": "O'rniga: {instead}",
        "edit_schedule_prompt": (
            "Kanal uchun yangi sana va vaqtni yuboring.\n"
            "Namuna: 21.07.2026 18:00–20:00\n"
            "ertaga 14:00\n"
            "18:00 - 20:00"
        ),
        "edit_comment_prompt": "Kanal uchun yangi izohni yuboring.",
        "edit_schedule_invalid": "Sana/vaqtni o'qib bo'lmadi. Qayta yuboring.",
        "replace_prompt": "Yangi @username yoki kanal havolasini yuboring.",
        "replace_post_prompt": "Shu kanal uchun yangi kreativ yuboring (bitta foto/video/hujjat yoki matn).",
        "replace_post_no_album": "Albom almashtirishda hali qo'llab-quvvatlanmaydi. Bitta fayl yoki matn yuboring.",
        "show_post_empty": "Bu kanalda saqlangan post yo'q.",
        "show_post_failed": "Postni ko'rsatib bo'lmadi (xabar o'chirilgan bo'lishi mumkin).",
        "reset_schedule_ok": "Sana/vaqt tozalandi.",
        "reset_comment_ok": "Izoh tozalandi.",
        "duplicate_channel": "⚠ Kanal takrorlanmoqda: {label}",
        "no_posts": "Avval kamida bitta post qo'shing.",
        "processing": "⏳ Xabarlar qayta ishlanmoqda…",
        "waiting_creative": "Kanallar saqlandi. Kreativ kutilyapti…",
        "orphan_need_channels": (
            "Postda kanal yo'q.\n"
            "Havola / @kanal yuboring\n"
            "yoki «Bo'sh qoldirish» ni bosing — o'rniga swap kanal qo'yamiz."
        ),
        "orphan_need_creative": (
            "Kanallar saqlandi, kreativ yo'q.\n"
            "Post yuboring\n"
            "yoki «Bo'sh qoldirish» ni bosing — post EMPTY bo'ladi."
        ),
        "orphan_leave_empty": "Bo'sh qoldirish",
        "orphan_leave_empty_ok": "Bo'sh joylar to'ldirildi.",
        "orphan_leave_empty_failed": "Bo'sh joylarni to'ldirib bo'lmadi. Qayta urinib ko'ring.",
        "channel_mode_prompt": (
            "Bu kanallarga post ko'rsatilmagan:\n"
            "{channels}\n\n"
            "Yuqoridagi postga bog'lansinmi, o'z kreativni yuborilsinmi "
            "yoki bo'sh qoldirilsinmi?"
        ),
        "channel_mode_to_above": "Yuqoridagi postga",
        "channel_mode_own_creative": "O'z kreativ",
        "channel_mode_leave_empty": "Bo'sh qoldirish",
        "channel_mode_ask_creative": (
            "Bu kanallar to'plami uchun kreativ yuboring:\n"
            "{channels}"
        ),
        "channel_mode_ok_above": "Kanallar yuqoridagi postga qo'shildi.",
        "channel_mode_ok_creative": "Kreativ kanallar to'plamiga bog'landi.",
        "channel_mode_ok_empty": "Kanallar uchun bo'sh postlar yaratildi.",
        "channel_mode_failed": "Kanallarni qo'llab bo'lmadi. Qayta urinib ko'ring.",
    },
    Language.en: {
        "entry_choose_mode": (
            "Choose how to publish the post to the TZ channel.\n\n"
            "Copy — the bot posts it as a regular channel message. "
            "The post can be edited. Premium emoji may be lost.\n\n"
            "Forward — the bot copies the post into this chat and forwards its own message to the channel. "
            "Emoji are preserved; the channel post is a forward and cannot be edited."
        ),
        "mode_copy": "Create by copying",
        "mode_forward": "Create by forwarding",
        "entry": (
            "Creating an ad campaign.\n\n"
            "Send a creative, then channels (@name / t.me).\n"
            "You can send several post + channels pairs in a row.\n\n"
            "Channel example:\n"
            "https://t.me/ru2ch | date: tomorrow 14:00 | comment: urgent\n"
            "Creative — as a separate message.\n\n"
            "Project name, comment, and time are optional\n"
            "(if time is omitted, we’ll set it automatically)."
        ),
        "ask_project_tz_header": "Channels saved. Send the missing details:",
        "ask_project_tz_project": "Project: …",
        "ask_project_tz_project_done": "Project already: {name}",
        "ask_project_tz_time": "Time: …",
        "ask_project_tz": (
            "Channels saved. Send project details:\n"
            "Project: …\nComment: …\nTime: …"
        ),
        "awaiting_reply": "Send channels (@name / links) or project details (project / comment / time).",
        "need_post_and_data": (
            "Send a creative (post) first, then channels or data:\n"
            "Project: …\nComment: …\nTime: …\nChannels:\n@name"
        ),
        "preview_title": "Project preview",
        "preview_project": "Project: {name}",
        "preview_found": "✅ Found: {n}",
        "preview_not_found": "⚠ Not found: {m}",
        "preview_empty_channels": "Empty channels: {n}",
        "preview_page": "Page {page}/{total}",
        "preview_channels": "Channels:",
        "preview_no_channels": "—",
        "preview_posts": "Posts: {n}",
        "preview_post_filled": "Post: Yes",
        "preview_post_empty": "Post: 🔹Empty",
        "auto": "(automatic)",
        "confirm_blocked_unknown": "Unknown or invalid channels remain. Replace or delete them.",
        "confirm_error": "Could not save the project. Try again or cancel.",
        "confirm_ok": "Project saved.\n\n{project_url}",
        "confirm_partial": "Project partially created. Finish in the cabinet:\n\n{project_url}",
        "confirm_progress_cart": "Adding to cart: {total}",
        "confirm_progress_orders": "Generating orders: {total}",
        "confirm_progress_posts": "Attaching posts: {total}",
        "past_schedule": "The selected time is in the past. Provide a future time.",
        "add_post": "Send the next creative (post).",
        "cancel": "Project creation cancelled.",
        "channel_menu": "Channel #{n}\n{label}",
        "channel_detail_title": "Channel #{n}",
        "channel_detail_name": "Name: {name}",
        "channel_detail_url": "Link: {url}",
        "channel_detail_date": "Date: {date}",
        "channel_detail_time": "Time: {time}",
        "channel_detail_comment": "Comment: {comment}",
        "channel_detail_instead": "Instead of: {instead}",
        "edit_schedule_prompt": (
            "Send a new date and time for the channel.\n"
            "Examples: 21.07.2026 18:00–20:00\n"
            "tomorrow 14:00\n"
            "18:00 - 20:00"
        ),
        "edit_comment_prompt": "Send a new comment for the channel.",
        "edit_schedule_invalid": "Could not parse date/time. Try again.",
        "replace_prompt": "Send a new @username or channel link.",
        "replace_post_prompt": "Send a new creative for this channel (one photo/video/document or text).",
        "replace_post_no_album": "Albums are not supported for replace yet. Send one file or text.",
        "show_post_empty": "This channel has no saved post.",
        "show_post_failed": "Could not show the post (it may have been deleted).",
        "reset_schedule_ok": "Date/time cleared.",
        "reset_comment_ok": "Comment cleared.",
        "duplicate_channel": "⚠ Duplicate channel: {label}",
        "no_posts": "Add at least one post first.",
        "processing": "⏳ Processing messages…",
        "waiting_creative": "Channels saved. Waiting for a creative…",
        "orphan_need_channels": (
            "A post has no channel.\n"
            "Send a link / @channel\n"
            "or tap “Leave empty” — we will assign a swap channel."
        ),
        "orphan_need_creative": (
            "Channels are saved, but there is no creative.\n"
            "Send a post\n"
            "or tap “Leave empty” — the post will be EMPTY."
        ),
        "orphan_leave_empty": "Leave empty",
        "orphan_leave_empty_ok": "Empty slots filled.",
        "orphan_leave_empty_failed": "Could not fill empty slots. Try again.",
        "channel_mode_prompt": (
            "No post specified for these channels:\n"
            "{channels}\n\n"
            "Attach to the post above, send your own creative, "
            "or leave empty?"
        ),
        "channel_mode_to_above": "To post above",
        "channel_mode_own_creative": "Own creative",
        "channel_mode_leave_empty": "Leave empty",
        "channel_mode_ask_creative": (
            "Send a creative for this channel batch:\n"
            "{channels}"
        ),
        "channel_mode_ok_above": "Channels added to the post above.",
        "channel_mode_ok_creative": "Creative linked to the channel batch.",
        "channel_mode_ok_empty": "Empty posts created for the channels.",
        "channel_mode_failed": "Could not apply channels. Try again.",
    },
}


def build_orphan_prompt_text(
        language: Language,
        *,
        need_channels: bool,
        need_creative: bool,
) -> str | None:
    parts: list[str] = []
    if need_channels:
        parts.append(t(language, "orphan_need_channels"))
    if need_creative:
        parts.append(t(language, "orphan_need_creative"))
    if not parts:
        return None
    return "\n\n".join(parts)


CONFIRM_PROGRESS_BAR_WIDTH = 10
_PROGRESS_FILLED = "🟩"
_PROGRESS_EMPTY = "⬜️"


def confirm_progress_bar(
        current: int,
        total: int,
        *,
        width: int = CONFIRM_PROGRESS_BAR_WIDTH,
) -> str:
    """Fixed-width bar: each cube is ceil(total / width) items."""
    if total <= 0:
        return _PROGRESS_EMPTY * width
    if current >= total:
        filled = width
    elif current <= 0:
        filled = 0
    else:
        filled = min(width - 1, (width * current) // total)
    return _PROGRESS_FILLED * filled + _PROGRESS_EMPTY * (width - filled)


def build_confirm_progress_text(
        language: Language,
        phase: str,
        current: int,
        total: int,
) -> str:
    if phase == "cart":
        key = "confirm_progress_cart"
    elif phase == "posts":
        key = "confirm_progress_posts"
    else:
        key = "confirm_progress_orders"
    return (
        f"{confirm_progress_bar(current, total)}\n"
        f"{t(language, key, total=total)}"
    )


def t(language: Language, key: str, **kwargs) -> str:
    pack = _TEXTS.get(language) or _TEXTS[Language.ru]
    text = pack.get(key) or _TEXTS[Language.ru][key]
    return text.format(**kwargs) if kwargs else text


def build_channel_mode_prompt_text(language: Language, raw_text: str) -> str:
    """Prompt body is the original channel-only message (HTML-escaped)."""
    return t(language, "channel_mode_prompt", channels=_escape_channel_mode_body(raw_text))


def build_channel_mode_ask_creative_text(language: Language, raw_text: str) -> str:
    return t(language, "channel_mode_ask_creative", channels=_escape_channel_mode_body(raw_text))


def _escape_channel_mode_body(raw_text: str) -> str:
    import html

    body = html.escape((raw_text or "").strip() or "—")
    return body.replace("{", "&#123;").replace("}", "&#125;")


def draft_missing_project_tz_fields(draft: BotProjectDraft) -> bool:
    return not (draft.project_name and draft.project_name.strip()) or draft.start_at is None


def build_ask_project_tz(draft: BotProjectDraft, language: Language) -> str | None:
    """Prompt only for missing project name / schedule. None if nothing to ask."""
    need_project = not (draft.project_name and draft.project_name.strip())
    need_time = draft.start_at is None
    if not need_project and not need_time:
        return None

    lines = [t(language, "ask_project_tz_header")]
    if need_project:
        lines.append(t(language, "ask_project_tz_project"))
    else:
        lines.append(t(language, "ask_project_tz_project_done", name=draft.project_name))
    if need_time:
        lines.append(t(language, "ask_project_tz_time"))
    return "\n".join(lines)


def build_create_order_url(frontend_domain: str, project_id: UUID) -> str:
    base = frontend_domain.rstrip("/")
    return f"{base}/createorder?project_id={project_id}"


def draft_can_confirm(draft: BotProjectDraft) -> bool:
    if not draft.posts:
        return False
    if draft.start_at is None or draft.end_at is None:
        return False
    for post in draft.posts:
        if not post.channels:
            return False
        for ch in post.channels:
            if ch.status != ChannelRefStatus.found or ch.format is None or ch.channel_id is None:
                return False
    return True


def _preview_channel_label(ch: BotChannelRef) -> str:
    name = (ch.display_name or "").strip()
    url = (ch.url or "").strip()
    if name and url:
        label = f"{name} ({url})"
    else:
        label = name or url or ch.query_raw
    if ch.is_swap:
        label = f"{label} (вместо {ch.query_raw})"
    return label


def channel_comment_for_display(ch: BotChannelRef, draft: BotProjectDraft) -> str:
    """
    None → inherit project comment; '' → explicitly empty; non-empty → channel comment.
    """
    if ch.comment == "":
        return "—"
    if ch.comment is not None and str(ch.comment).strip():
        return str(ch.comment).strip()
    project = (draft.comment or "").strip()
    return project or "—"


def channel_comment_for_order(ch: BotChannelRef, draft: BotProjectDraft) -> str | None:
    if ch.comment == "":
        return None
    if ch.comment is not None and str(ch.comment).strip():
        return str(ch.comment).strip()
    project = (draft.comment or "").strip()
    return project or None


def build_channel_detail_text(
        ch: BotChannelRef,
        channel_index: int,
        draft: BotProjectDraft,
        language: Language,
) -> str:
    auto = t(language, "auto")
    name = (ch.display_name or "").strip() or "—"
    url = (ch.url or "").strip() or "—"

    start_at = ch.start_at or draft.start_at
    end_at = ch.end_at or draft.end_at
    schedule_source = ch.schedule_source
    if ch.start_at is None and ch.end_at is None:
        schedule_source = draft.schedule_source

    if start_at and end_at:
        date_s = start_at.strftime("%d.%m.%Y")
        time_s = f"{start_at.strftime('%H:%M')}–{end_at.strftime('%H:%M')}"
        if schedule_source == ScheduleSource.default_generated:
            time_s = f"{time_s} {auto}"
    else:
        date_s = "—"
        time_s = "—"

    comment = channel_comment_for_display(ch, draft)
    lines = [
        t(language, "channel_detail_title", n=channel_index),
        t(language, "channel_detail_name", name=name),
        t(language, "channel_detail_url", url=url),
        t(language, "channel_detail_date", date=date_s),
        t(language, "channel_detail_time", time=time_s),
        t(language, "channel_detail_comment", comment=comment),
    ]
    if ch.is_swap:
        lines.append(t(language, "channel_detail_instead", instead=ch.query_raw))
    return "\n".join(lines)


def _iter_preview_channels(draft: BotProjectDraft):
    for post in draft.posts:
        for ch in post.channels:
            yield post, ch


def _channel_is_found(ch: BotChannelRef) -> bool:
    return ch.status == ChannelRefStatus.found and not ch.is_swap and ch.format is not None


def _post_is_empty(post) -> bool:
    return post.kind is CreativeKind.empty


def build_preview_text(
        draft: BotProjectDraft,
        language: Language,
        *,
        banner: str | None = None,
        page: int = 1,
        page_size: int = 10,
) -> str:
    auto = t(language, "auto")
    channels = list(_iter_preview_channels(draft))
    found_n = sum(1 for _, ch in channels if _channel_is_found(ch))
    not_found_m = len(channels) - found_n
    empty_n = sum(1 for post, _ in channels if _post_is_empty(post))

    page_size = max(1, int(page_size))
    total_pages = max(1, (len(channels) + page_size - 1) // page_size) if channels else 1
    page = max(1, min(int(page), total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    page_channels = channels[start:end]

    if draft.start_at and draft.end_at:
        auto_mark = f" {auto}" if draft.schedule_source == ScheduleSource.default_generated else ""
        schedule_line = (
            f"{draft.start_at.strftime('%d.%m.%Y')} · "
            f"{draft.start_at.strftime('%H:%M')}–{draft.end_at.strftime('%H:%M')}{auto_mark}"
        )
    else:
        schedule_line = "—"

    lines: list[str] = []
    if banner:
        lines.extend([f"⚠ {banner}", ""])
    lines.append(t(language, "preview_title"))
    lines.append(t(language, "preview_project", name=draft.project_name or "—"))
    lines.append("")
    lines.append(t(language, "preview_found", n=found_n))
    lines.append(t(language, "preview_not_found", m=not_found_m))
    lines.append(t(language, "preview_empty_channels", n=empty_n))
    if total_pages > 1:
        lines.append(t(language, "preview_page", page=page, total=total_pages))
    lines.append("")
    lines.append(t(language, "preview_channels"))

    if not page_channels:
        lines.append(t(language, "preview_no_channels"))
    else:
        for offset, (post, ch) in enumerate(page_channels):
            idx = start + offset + 1
            if ch.is_swap:
                mark = "⚠"
                label = _preview_channel_label(ch)
            elif ch.status == ChannelRefStatus.found:
                mark = "✅"
                label = _preview_channel_label(ch)
            elif ch.status == ChannelRefStatus.invalid:
                mark = "⛔"
                label = f"{ch.query_raw} (no format)"
            else:
                mark = "⚠"
                label = ch.query_raw

            if ch.start_at and ch.end_at:
                ch_auto = (
                    f" {auto}"
                    if ch.schedule_source == ScheduleSource.default_generated
                    else ""
                )
                ch_schedule = (
                    f"{ch.start_at.strftime('%d.%m.%Y')} · "
                    f"{ch.start_at.strftime('%H:%M')}–{ch.end_at.strftime('%H:%M')}{ch_auto}"
                )
            else:
                ch_schedule = schedule_line
            ch_comment = f"Коммент: {channel_comment_for_display(ch, draft)}"
            post_line = t(
                language,
                "preview_post_empty" if _post_is_empty(post) else "preview_post_filled",
            )

            lines.append(f"{mark} [{idx}] {label}")
            lines.append(f"   {ch_schedule}")
            lines.append(f"   {ch_comment}")
            lines.append(f"   {post_line}")

    lines.append("")
    lines.append(t(language, "preview_posts", n=len(draft.posts)))
    return "\n".join(lines)
